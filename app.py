import time
import threading
import board
import adafruit_dht
import spidev
import cv2
import smtplib
import ssl
import datetime
import os
from email.message import EmailMessage
from flask import Flask, render_template, jsonify, Response, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# --- IMPORTS ---
from gpiozero import InputDevice, OutputDevice, TonalBuzzer

# --- CONFIGURATION ---
GAS_THRESHOLD = 700       
TEMP_THRESHOLD = 40 
ALERT_COOLDOWN = 15 

# *** EMAIL CONFIGURATION ***
SMTP_SENDER_EMAIL = "EMAIL"
SMTP_SENDER_PASSWORD = "PASSWORD" 
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# --- GCP SETUP ---
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("credentials.json")
        firebase_admin.initialize_app(cred)
        print(f"[GCP] Connected to Project ID: {cred.project_id}") 
        print("[GCP] Connected to Firestore successfully.")
    except Exception as e:
        print(f"[GCP] Error connecting: {e}")

try:
    db = firestore.client()
except:
    db = None

# --- HARDWARE SETUP ---
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1350000
except Exception as e:
    print(f"[HARDWARE ERROR] SPI Failed: {e}")

def read_gas():
    try:
        adc = spi.xfer2([1, (8 + 0) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]
    except:
        return 0

# NOTE: Using GPIO 16 (Pin 36) for Flame Sensor
flame_sensor = InputDevice(16, pull_up=False) 
mq2_digital = InputDevice(26, pull_up=False) 
dht = adafruit_dht.DHT11(board.D4)
pump = OutputDevice(17)

try:
    buzzer = TonalBuzzer(22)
except Exception:
    buzzer = None

# --- GLOBAL VARIABLES ---
global_frame = None
lock = threading.Lock()
current_monitoring_email = None 

state = {
    "pump_manual": False,
    "buzzer_manual": False,
    "email_alert_enabled": True, 
    "last_email_time": 0,
    "pump_off_time": 0 
}

latest_data = {
    'gas': 0, 'temp': 0, 'hum': 0,
    'flame_sensor': "SAFE",
    'mq2_status': "SAFE",
    'pump_status': "OFF", 'buzzer_status': "OFF"
}

# --- FLASK & AUTH SETUP ---
app = Flask(__name__)
app.secret_key = "super_secret_key_hardcoded" 

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, email):
        self.id = email
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# --- EMAIL FUNCTION ---
def send_alert_email(recipient_email, data, image_bytes):
    if not recipient_email: return

    def _send():
        msg = EmailMessage()
        
        # --- LOGIC: Determine Primary Hazard for Color Coding ---
        header_color = "#d9534f" 
        alert_title = "HAZARD DETECTED"
        
        if data['flame_sensor'] == "FIRE DETECTED":
            header_color = "#ff9800" # Orange for Fire
            alert_title = "FIRE DETECTED"
        elif data['mq2_status'] == "GAS DETECTED" or data['gas'] > GAS_THRESHOLD:
            header_color = "#9c27b0" # Purple for Gas
            alert_title = "GAS LEAK DETECTED"

        msg['Subject'] = f"🚨 NEXUS ALERT: {alert_title}"
        msg['From'] = f"Nexus System <{SMTP_SENDER_EMAIL}>"
        msg['To'] = recipient_email
        
        # UTC+8 Timestamp
        now_utc = datetime.datetime.utcnow()
        now_my = now_utc + datetime.timedelta(hours=8)
        time_str = now_my.strftime('%Y-%m-%d %H:%M:%S')

        msg.set_content(f"NEXUS SYSTEM ALERT - {alert_title}") 
        msg.add_alternative(f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background: {header_color}; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">🚨 {alert_title}</h2>
                    <p style="margin: 5px 0 0 0;">Immediate Action Required</p>
                </div>
                <div style="padding: 20px;">
                    <p><strong>Time:</strong> {time_str}</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background: #f9f9f9; border-bottom: 1px solid #eee;">
                            <td style="padding: 10px; font-weight: bold;">Flame Sensor</td>
                            <td style="padding: 10px; color: #ff9800; font-weight: bold;">{data['flame_sensor']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #eee;">
                            <td style="padding: 10px; font-weight: bold;">Gas Status</td>
                            <td style="padding: 10px; color: #9c27b0; font-weight: bold;">{data['mq2_status']}</td>
                        </tr>
                        <tr style="background: #f9f9f9; border-bottom: 1px solid #eee;">
                            <td style="padding: 10px; font-weight: bold;">Gas Level (Analog)</td>
                            <td style="padding: 10px;">{data['gas']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #eee;">
                            <td style="padding: 10px; font-weight: bold;">Temperature</td>
                            <td style="padding: 10px;">{data['temp']}°C</td>
                        </tr>
                    </table>
                </div>
                <div style="background: #f4f4f4; padding: 10px; text-align: center; font-size: 12px; color: #777;">
                    Nexus System Bot | Automated Alert
                </div>
            </div>
          </body>
        </html>
        """, subtype='html')

        if image_bytes:
            msg.add_attachment(image_bytes, maintype='image', subtype='jpeg', filename='alert_capture.jpg')

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as smtp:
                smtp.login(SMTP_SENDER_EMAIL, SMTP_SENDER_PASSWORD)
                smtp.send_message(msg)
            print(f"[EMAIL] Sent to {recipient_email}")
        except Exception as e:
            print(f"[EMAIL] Failed: {e}")

    threading.Thread(target=_send).start()

# --- SYSTEM THREAD ---
def system_loop():
    global global_frame
    print("--- SYSTEM THREAD STARTED ---")
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    last_upload_time = 0
    
    # --- DEBOUNCING VARIABLES ---
    # We will only trigger if we see danger for 3 consecutive loops (approx 1.5 seconds)
    fire_confirm_count = 0 
    
    fire_latched = False
    gas_latched = False
    
    while True:
        current_jpeg = None
        if cap.isOpened():
            success, frame = cap.read()
            if success:
                with lock:
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        current_jpeg = buffer.tobytes()
                        global_frame = current_jpeg

        try: gas = read_gas()
        except: gas = 0
        
        # --- RAW SENSOR READING ---
        try: raw_flame_val = flame_sensor.value # 0 = Fire, 1 = Safe
        except: raw_flame_val = 1 

        try: mq2_state = "GAS DETECTED" if mq2_digital.value == 0 else "SAFE"
        except: mq2_state = "ERROR"

        try:
            temp = dht.temperature
            hum = dht.humidity
        except:
            temp = latest_data['temp']
            hum = latest_data['hum']
        
        if temp is None: temp = 0
        if hum is None: hum = 0

        # --- DEBOUNCING LOGIC ---
        # If raw sensor says fire, increase confidence. 
        # If it flickers back to safe, reset confidence immediately.
        if raw_flame_val == 0:
            fire_confirm_count += 1
        else:
            fire_confirm_count = 0
        
        # Only set TRUE fire if we are confident (3 checks in a row)
        if fire_confirm_count >= 3:
            hw_flame = "FIRE DETECTED"
            # Cap the counter so it doesn't grow forever
            fire_confirm_count = 10 
        else:
            hw_flame = "SAFE"

        danger_gas = (gas > GAS_THRESHOLD) or (mq2_state == "GAS DETECTED")
        high_temp = (temp > TEMP_THRESHOLD)
        fire_detected = (hw_flame == "FIRE DETECTED")

        # --- PUMP LOGIC ---
        if fire_detected:
            state["pump_off_time"] = time.time() + 5.0
        
        if fire_detected: fire_latched = True
        if danger_gas: gas_latched = True

        if state["pump_manual"] or time.time() < state["pump_off_time"]:
            pump.on()
            pump_state = "ON"
        else:
            pump.off()
            pump_state = "OFF"

        should_buzz = fire_detected or danger_gas or high_temp or state["buzzer_manual"]
        if should_buzz:
            if latest_data['buzzer_status'] != "ON":
                if buzzer: buzzer.play(440)
            buzzer_state = "ON"
        else:
            if buzzer: buzzer.stop()
            buzzer_state = "OFF"

        is_danger = fire_detected or danger_gas or high_temp
        time_since_last = time.time() - state["last_email_time"]
        
        if (fire_latched or gas_latched) and state["email_alert_enabled"]:
            if time_since_last > ALERT_COOLDOWN:
                if current_monitoring_email:
                    print(f"[SYSTEM] Triggering Alert to {current_monitoring_email}...")
                    
                    snap_flame = "FIRE DETECTED" if fire_latched else "SAFE"
                    snap_gas = "GAS DETECTED" if gas_latched else mq2_state
                    
                    data_snapshot = {
                        'gas': gas, 
                        'temp': temp, 
                        'hum': hum, 
                        'flame_sensor': snap_flame, 
                        'mq2_status': snap_gas
                    }
                    send_alert_email(current_monitoring_email, data_snapshot, current_jpeg)
                    state["last_email_time"] = time.time()
                    
                    fire_latched = False
                    gas_latched = False
                else:
                    print("[SYSTEM] Danger detected, but no user is logged in.")

        latest_data['gas'] = gas
        latest_data['flame_sensor'] = hw_flame
        latest_data['mq2_status'] = mq2_state
        latest_data['temp'] = temp
        latest_data['hum'] = hum
        latest_data['pump_status'] = pump_state
        latest_data['buzzer_status'] = buzzer_state

        if (time.time() - last_upload_time) >= 5:
            if db:
                try:
                    final_status = "DANGER" if (is_danger or fire_latched or gas_latched) else "SAFE"
                    
                    db.collection('sensor_history').document().set({
                        'gas': gas, 'temp': temp, 'humidity': hum,
                        'flame': hw_flame, 'gas_status': mq2_state,
                        'pump': pump_state, 'buzzer': buzzer_state,
                        'status': final_status, 'timestamp': firestore.SERVER_TIMESTAMP
                    })
                    last_upload_time = time.time()
                except Exception as e:
                    print(f"[GCP] Error: {e}")

        time.sleep(0.5)

thread = threading.Thread(target=system_loop)
thread.daemon = True
thread.start()

# --- ROUTES ---
@app.route('/')
def index():
    global current_monitoring_email
    
    if current_user.is_authenticated:
        if current_monitoring_email is None:
            current_monitoring_email = current_user.email
            print(f"[SYSTEM] Restored monitoring email to: {current_monitoring_email}")
            
        return render_template('index.html', user=current_user, alert_status=state["email_alert_enabled"])
    return redirect(url_for('login'))

@app.route('/logs')
@login_required
def logs():
    return render_template('logs.html', user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    global current_monitoring_email
    if request.method == 'POST':
        email = request.form.get('email')
        if email:
            user = User(email)
            login_user(user)
            current_monitoring_email = email 
            print(f"[AUTH] User {email} logged in. Alerts directed to them.")
            return redirect(url_for('index'))
    return render_template('index.html', login_mode=True)

@app.route('/logout')
@login_required
def logout():
    global current_monitoring_email
    logout_user()
    current_monitoring_email = None 
    return redirect(url_for('login'))

@app.route('/data')
@login_required
def get_data():
    d = latest_data.copy()
    d['email_alert'] = state["email_alert_enabled"]
    return jsonify(d)

@app.route('/history')
@login_required
def get_history():
    if not db: return jsonify([])
    docs = db.collection('sensor_history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(20).stream()
    data = []
    for doc in docs:
        r = doc.to_dict()
        if r.get('timestamp'):
            data.append({
                'time_iso': r['timestamp'].isoformat(),
                'gas': r.get('gas', 0),
                'temp': r.get('temp', 0),
                'humidity': r.get('humidity', 0)
            })
    return jsonify(data[::-1])

@app.route('/alert_history')
@login_required
def get_alert_history():
    if not db: return jsonify([])
    docs = db.collection('sensor_history')\
             .where('status', '==', 'DANGER')\
             .order_by('timestamp', direction=firestore.Query.DESCENDING)\
             .limit(15)\
             .stream()
    
    data = []
    for doc in docs:
        r = doc.to_dict()
        if r.get('timestamp'):
            dt_utc = r['timestamp']
            dt_my = dt_utc + datetime.timedelta(hours=8)
            time_str = dt_my.strftime('%Y-%m-%d %H:%M:%S')

            alert_type = "GAS LEAK"
            alert_color = "#9c27b0" 

            if r.get('flame') == "FIRE DETECTED": 
                alert_type = "FIRE"
                alert_color = "#ff9800" 
            
            data.append({
                'time': time_str,
                'type': alert_type,
                'color': alert_color, 
                'gas': r.get('gas', 0),
                'temp': r.get('temp', 0),
                'humidity': r.get('humidity', 0)
            })
    return jsonify(data)

@app.route('/control/<device>/<action>', methods=['POST'])
@login_required
def control(device, action):
    is_on = (action == "on")
    if device == "pump": state["pump_manual"] = is_on
    elif device == "buzzer": state["buzzer_manual"] = is_on
    elif device == "email": state["email_alert_enabled"] = is_on
    return jsonify({"status": "ok", "state": action})

def generate_feed():
    while True:
        with lock:
            if global_frame is None: continue
            frame = global_frame
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(generate_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)