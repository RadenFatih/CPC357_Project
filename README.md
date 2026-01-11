# Nexus Safety System - IoT Fire and Gas (LPG) Hazard Monitoring

## Project Description
The **Nexus Safety System** is an advanced IoT-based environmental monitoring solution designed to detect fire and gas hazards in real-time. Built on a Raspberry Pi, it integrates multi-sensor data fusion with computer vision to provide immediate alerts and automated hazard mitigation.

The system features a futuristic "City Command" web dashboard for real-time surveillance, historical data analysis, and manual control of safety actuators.

### Key Features
* **Multi-Hazard Detection:** Real-time monitoring of:
    * **Fire:** Infrared Flame Sensor detection.
    * **Gas Leaks:** LPG/Smoke detection via MQ2 sensor (Analog & Digital).
    * **Environment:** Temperature and Humidity tracking via DHT11.
* **Automated Response:** Automatically triggers a water pump and alarm buzzer upon detecting danger.
* **Visual Surveillance:** Live video feed streaming from a connected Logitech webcam.
* **Remote Alerts:** Sends immediate email notifications containing a snapshot of the hazard to authorized personnel.
* **Cloud Data Logging:** securely stores hazard history and sensor readings in Google Cloud Firestore.
* **Interactive Dashboard:** A responsive, neon-themed Flask web interface for monitoring status, viewing charts, and overriding controls.

---

## Hardware Requirements
* **Controller:** Raspberry Pi 3B+ or above
* **Visual Sensor:** Logitech C270 Webcam (or compatible USB camera)
* **Sensors:**
    * MQ2 Gas/Smoke Sensor
    * KY-026 Flame Sensor
    * DHT11 Temperature & Humidity Sensor
    * MCP3008 ADC (for Analog Gas reading)
* **Actuators:**
    * Cytron Maker Drive (Motor Driver) & Mini Water Pump (5V)
    * Active Buzzer
* **Power:** 5V 2.5A Power Supply for Raspberry Pi, separate power source for Pump recommended.

---

## Wiring Configuration
| Device | Raspberry Pi GPIO / Pin |
| :--- | :--- |
| **Flame Sensor (DO)** | GPIO 16 |
| **MQ2 Sensor (DO)** | GPIO 26 |
| **MQ2 Sensor (AO)** | MCP3008 CH0 (SPI) |
| **DHT11 Data** | GPIO 4 |
| **Water Pump (Cytron Maker Drive)**| GPIO 17 |
| **Buzzer** | GPIO 22 |

---

## 💻 Software Prerequisites
* Python 3.7 or higher
* PIP (Python Package Installer)
* Google Cloud Platform Account (for Firestore)
* Gmail Account (for SMTP Alerts)

---

## Installation & Setup

### 1. Clone the Repository
Open your terminal on the Raspberry Pi and clone this repository:

git clone [https://github.com/YOUR_USERNAME/nexus-safety-system.git](https://github.com/YOUR_USERNAME/nexus-safety-system.git)
cd nexus-safety-system

### 2. Set-Up Virtual Environment

It is best practice to use a virtual environment to manage dependencies:

Bash

python3 -m venv venv
source venv/bin/activate

### 3. Install Dependencies
Install all required Python libraries using the provided requirements file:

Bash

pip install -r requirements.txt

### 4. Configuration

A. Google Cloud Firestore
Go to the Google Cloud Console.

Create a new project and enable Cloud Firestore.

Create a Service Account and download the JSON key.

Rename this file to credentials.json and place it in the root directory of the project.

B. Email Alerts
Open app.py in a text editor.

Locate the email configuration section:

Python

SMTP_SENDER_EMAIL = "your_email@gmail.com"
SMTP_SENDER_PASSWORD = "your_app_password"
Replace the placeholders with your actual Gmail address and App Password (not your login password).

### ▶️ Usage
Start the Application: Run the main Python script with sudo permissions (required for GPIO access):

Bash

sudo python3 app.py
Access the Dashboard:

Open a web browser on any device connected to the same network.

Navigate to: http://<RASPBERRY_PI_IP>:5000

Login:

Use the authorized email configured in the system to log in.

### Project Structure

nexus-safety-system/
├── app.py                 # Main Flask application & Logic
├── credentials.json       # GCP Firestore Key (IGNORED in Git)
├── requirements.txt       # Python dependencies
├── .gitignore             # Security rules for Git
└── templates/
    ├── index.html         # Main Dashboard UI
    └── logs.html          # Hazard History Logs UI


