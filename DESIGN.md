# WiWave Motion Design Document: Intelligence Engine v4

## Overview
WiWave Motion v3 is an experimental, privacy-first motion detection system. Unlike traditional security systems that rely on cameras or PIR sensors, WiWave utilizes **Dual-Sensor Fusion** of standard Wi-Fi signal metadata (RSSI and RTT) to detect human activity.

## How It Works: The Dual-Sensor Fusion
WiWave treats the Wi-Fi environment as a high-resolution sensing fabric. We analyze two primary metrics:

1.  **Macro-Sensing (RSSI - Signal Strength):**
    -   Used for **Long-term Environment Baselining** and **Distance Estimation**.
    -   RSSI fluctuates slowly but provides a good indication of the overall RF "shadow" cast by objects in the room.
2.  **Micro-Sensing (RTT - Ping Latency Jitter):**
    -   Used for **High-Frequency Motion Tracking**.
    -   Round-Trip Time (RTT) jitter is highly sensitive to the multi-path interference caused by human movement. Even subtle movements like breathing cause detectable phase shifts in the signal timing.

## Intelligence Engine v4: The Brain
The core of WiWave is the `MotionDetector` class, which uses advanced signal processing techniques:

### 1. Adaptive Baselining (EMA)
Instead of a static threshold, WiWave uses **Exponential Moving Averages (EMA)** to "learn" the environment. This allows the system to automatically adjust to:
-   Furniture being moved.
-   Doors being opened/closed.
-   Slow changes in the background RF noise from neighbors.

### 2. Frequency Analysis (FFT)
To distinguish between a human walking and a curtain blowing in the wind, we perform **Fast Fourier Transforms (FFT)** on the RTT jitter data.
-   **Breathing Band (0.1 - 0.5 Hz):** Detects the rhythmic chest movement of a stationary person.
-   **Walking Band (1.0 - 4.0 Hz):** Detects the high-energy, faster movement of a person walking through the RF field.

### 3. Probabilistic Classification
The system combines Jitter Variance and Band Energy to classify the environment into:
-   **CALM:** No significant activity.
-   **SCANNING:** Detecting non-human interference (e.g., electronic noise).
-   **HUMAN DETECTED (BREATHING):** Rhythmic low-frequency signature found.
-   **HUMAN DETECTED (WALKING):** High-energy high-frequency signature found.

## Project Structure
-   `wifi_reader.py`: The **Hardware Abstraction Layer**. Uses `netsh` and `ping` to gather raw signal metadata.
-   `motion_detector.py`: The **Intelligence Engine**. Handles FFT, EMA, and classification.
-   `server.py`: The **Orchestrator**. A FastAPI-based WebSocket server that broadcasts live data.
-   `frontend/`: The **3D Radar Dashboard**. Built with React and Three.js for real-time spatial visualization.

## Technical Limitations
-   **Windows-Specific:** Currently relies on `netsh` and `ping` commands native to Windows.
-   **RSSI Noise:** RSSI is a coarse metric; the engine relies more heavily on RTT jitter for precision.
-   **Interference:** High network traffic on the host machine can introduce "artificial" jitter.

---
*WiWave is an experimental project exploring the boundaries of device-free sensing.*
