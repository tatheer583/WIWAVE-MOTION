# WiWave v3: Intelligent Wi-Fi Radar

WiWave is an advanced, privacy-first motion detection system that transforms standard Wi-Fi signals into a high-resolution sensing fabric. Inspired by professional systems like RuView, WiWave uses **Dual-Sensor Fusion** and **Frequency Analysis** to detect human presence, walking, and even subtle breathing patterns without cameras or wearables.

## 🚀 Features

- **Intelligence Engine v4:** Uses Fast Fourier Transforms (FFT) to distinguish between rhythmic walking (1.0-4.0 Hz) and breathing (0.1-0.5 Hz).
- **Adaptive Room Learning:** Automatically "learns" the environment's RF signature (furniture, walls) using Exponential Moving Averages (EMA).
- **Dual-Sensor Fusion:** Combines Macro-sensing (RSSI) for distance estimation and Micro-sensing (RTT Jitter) for precise motion tracking.
- **3D Radar Dashboard:** A professional React-based visualization built with Three.js/React Three Fiber.
- **Privacy First:** No cameras, no microphones. Only signal metadata is analyzed.

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, NumPy, SciPy (FFT Analysis).
- **Frontend:** React, Vite, Three.js (R3F), Framer Motion, Tailwind CSS.
- **Sensors:** Windows `netsh` (RSSI) and High-frequency ICMP (RTT).

## 📥 Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-link>
   cd WiWave-2
   ```

2. **Setup Python Environment:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Setup Frontend:**
   ```bash
   cd frontend
   npm install
   ```

## 🏃 How to Run

1. **Start the Backend:**
   ```bash
   python server.py
   ```

2. **Start the Frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open the Dashboard:**
   Navigate to `http://localhost:5173`.

## 🧪 How it Works

WiWave monitors the fluctuations in Wi-Fi signal timing and strength. When a human (who is mostly water) moves between a laptop and a router, they disturb the RF environment. By analyzing these disturbances in the frequency domain, we can extract signatures for different activities.

---
*Developed as an experimental project for intelligent Wi-Fi sensing.*
