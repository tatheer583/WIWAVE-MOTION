# WiWave v3: Intelligent Wi-Fi Radar 📡

WiWave is an advanced, privacy-first motion detection system that transforms standard Wi-Fi signals into a high-resolution sensing fabric. Inspired by professional RF sensing systems, WiWave uses **Dual-Sensor Fusion** and **Frequency Domain Analysis** to detect human presence, walking, and even subtle breathing patterns—**no cameras, no wearables, no privacy intrusion.**

## 🚀 Key Features
*   **Intelligence Engine v4:** Utilizes Fast Fourier Transforms (FFT) to distinguish between rhythmic walking (1.0-4.0 Hz) and subtle breathing (0.1-0.5 Hz).
*   **Dual-Sensor Fusion:** Combines **Macro-sensing** (RSSI) for long-term environment baselining and **Micro-sensing** (RTT Jitter) for high-precision motion tracking.
*   **Adaptive Environment Learning:** Uses Exponential Moving Averages (EMA) to automatically "learn" the room's RF signature (furniture, walls, background noise).
*   **3D Radar Dashboard:** A professional React-based visualization built with Three.js (R3F) for real-time spatial data representation.
*   **Log-Distance Path Loss:** Improved distance estimation based on indoor RF propagation models.

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

3.  **Setup Frontend Dashboard:**
    ```bash
    cd frontend
    npm install
    ```

## 🏃 How to Run

### Option 1: Full 3D Dashboard (Recommended)
1.  **Start the Backend:**
    ```bash
    python server.py
    ```
2.  **Start the Frontend:**
    ```bash
    cd frontend
    npm run dev
    ```
3.  **Open Dashboard:** Navigate to `http://localhost:5173`

### Option 2: Lightweight CLI Mode
```bash
python main.py
```

## 🧪 How it Works
WiWave monitors the fluctuations in Wi-Fi signal timing (RTT) and strength (RSSI). When a human (mostly water) moves through the RF field, they cause multi-path interference. By analyzing these disturbances in the frequency domain, WiWave extracts signatures for different activities, allowing for precise detection without visual surveillance.

---
*Developed as an experimental project for intelligent Wi-Fi sensing.*

**Last Updated:** May 7, 2026
