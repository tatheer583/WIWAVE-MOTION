# WiWave Motion Design Document

## Overview
WiWave Motion is a experimental Python tool designed to detect human motion using nothing but the Wi-Fi signal strength (RSSI) already present in your Windows laptop. 

## How It Works
Wi-Fi signals travel from your router to your laptop. When an object (like a human body, which is mostly water) enters the path or moves near the devices, it absorbs or reflects some of the radio frequency (RF) energy. 

By monitoring the **Signal Strength Percentage** (RSSI) provided by Windows, we can see small fluctuations. While a stationary environment results in a relatively steady signal, movement causes the signal to "flicker" or vary rapidly.

## Limitations (RSSI vs CSI)
It is important to understand that this method is "rough" detection:
1. **RSSI (Signal Strength):** This is a single number representing the total power received. It is very noisy and can be affected by many factors (other electronics, neighbors' Wi-Fi, etc.).
2. **CSI (Channel State Information):** Professional Wi-Fi sensing uses CSI, which provides data on how the signal behaves across many different frequencies and paths. RSSI is like looking at a single flickering lightbulb; CSI is like having a high-definition camera.
3. **No Directionality:** We can't tell *where* the motion is, only that the signal environment is changing.

## Project Structure

- `wifi_reader.py`: The "Sensor". It talks to Windows to get the current signal strength.
- `data_logger.py`: The "Recorder". It saves the signal data to a CSV file for later analysis.
- `motion_detector.py`: The "Brain". It looks at the last few seconds of data and decides if it looks like "Motion" or "Calm".
- `visualizer.py`: The "Eyes". It draws a live graph so you can see the signal changes in real-time.
- `main.py`: The "Manager". It connects all the pieces together into one running program.

## Motion Detection Logic
We use a **Sliding Window Variance** approach:
- We keep track of the last 20-30 readings.
- We calculate the **Variance** (how much the numbers spread out from the average).

## How to Experiment

### 1. Run the Program
Open your terminal in the project folder and run:
```powershell
python main.py
```

### 2. Establish a Baseline (Calm)
- Set your laptop on a stable table.
- Move away from the laptop and router (or stay very still).
- Let the program run for 1-2 minutes.
- Look at the "Variance" value in the console. This is your "noise floor."

### 3. Test for Motion
- Walk slowly between your laptop and your Wi-Fi router.
- Watch the graph. You should see the signal line start to "flicker" up and down.
- The status should change to **MOTION LIKELY**.

### 4. Tuning
If the detector is not working correctly, open `main.py` (or `motion_detector.py`) and adjust these:
- **MOTION_THRESHOLD**: If it says "Motion" when you are still, increase this (e.g., to 3.0). If it never detects you, decrease it (e.g., to 0.5).
- **WINDOW_SIZE**: A larger window makes the detector more stable but slower to react.

**Note:** This is a rough demo. It may be affected by neighbors' Wi-Fi, other 2.4GHz devices (like microwaves), or even the internal power management of your Wi-Fi card.
