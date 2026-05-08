# WiWave v4: Intelligent Wi-Fi Radar 📡

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/tatheer583/WIWAVE-MOTION)

WiWave is an advanced, privacy-first motion detection system that transforms standard Wi-Fi signals into a high-resolution sensing fabric. Inspired by professional RF sensing systems, WiWave uses **Dual-Sensor Fusion** and **Frequency Domain Analysis** to detect human presence, walking, and even subtle breathing patterns—**no cameras, no wearables, no privacy intrusion.**

## 🚀 Key Features
*   **Intelligence Engine v4:** Utilizes Fast Fourier Transforms (FFT) to distinguish between rhythmic walking (1.0-4.0 Hz) and subtle breathing (0.1-0.5 Hz).
*   **Dual-Sensor Fusion:** Combines **Macro-sensing** (RSSI) for long-term environment baselining and **Micro-sensing** (RTT Jitter) for high-precision motion tracking.
*   **Adaptive Environment Learning:** Uses Exponential Moving Averages (EMA) to automatically "learn" the room's RF signature.
*   **3D Radar Dashboard:** A professional React-based visualization built with Three.js (R3F) for real-time spatial data representation.
*   **Simulation Mode:** Built-in engine to test the dashboard and DSP logic without specific hardware.

## 🛠️ Tech Stack
*   **Core:** Python 3.10+, NumPy, SciPy (Signal Processing).
*   **Backend:** FastAPI, WebSockets, Uvicorn.
*   **Frontend:** React, Vite, Three.js (React Three Fiber), Tailwind CSS.
*   **Hardware:** Standard Windows Wi-Fi adapter (utilizes `netsh` and ICMP).

## 📦 Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/tatheer583/WIWAVE-MOTION.git
    cd WIWAVE-MOTION
    ```

2.  **Setup Python Environment:**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Setup Frontend (Optional for Unified Mode):**
    ```bash
    cd frontend
    npm install
    npm run build
    cd ..
    ```

## 🏃 How to Run

### Option 1: Unified Dashboard (Recommended)
This runs the backend and serves the frontend on the same port.
1.  **Build the frontend** (see above).
2.  **Start the server:**
    ```bash
    python server.py
    ```
3.  **Open:** `http://localhost:8000`

### Option 2: Development Mode
1.  **Backend:** `python server.py`
2.  **Frontend:** `cd frontend && npm run dev`
3.  **Open:** `http://localhost:5173`

### Option 3: Simulation Mode
To test without a Windows Wi-Fi adapter:
```bash
$env:SIMULATION_MODE="true"; python server.py
```

## 🌐 Deployment (Workable Link)
To deploy this project to a service like **Render** or **Railway**:
1.  **Build Command:** `pip install -r requirements.txt && cd frontend && npm install && npm run build`
2.  **Start Command:** `python server.py`
3.  **Environment Variable:** Set `SIMULATION_MODE=true` for cloud hosting (since cloud servers don't have Wi-Fi cards).

## 🧪 How it Works
WiWave monitors the fluctuations in Wi-Fi signal timing (RTT) and strength (RSSI). When a human (mostly water) moves through the RF field, they cause multi-path interference. By analyzing these disturbances in the frequency domain, WiWave extracts signatures for different activities, allowing for precise detection without visual surveillance.

---
*Developed as an experimental project for intelligent Wi-Fi sensing.*

**Last Updated:** May 8, 2026
