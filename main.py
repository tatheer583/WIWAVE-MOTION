"""
WiWave Motion - Main Entry Point
================================
How to run:
1. Ensure you are on a Windows laptop with Wi-Fi connected.
2. Install requirements: pip install matplotlib numpy
3. Run this file: python main.py

This script integrates the reader, logger, detector, and visualizer
to create a real-time Wi-Fi motion sensing dashboard.
"""

import time
import csv
import os
from datetime import datetime

# Import our custom modules
from wifi_reader import get_wifi_signal
from motion_detector import MotionDetector
from visualizer import WifiVisualizer

# --- CONFIGURATION ---
UPDATE_INTERVAL = 0.5  # Seconds between readings
LOG_FILE = "logs/wiwave_main_log.csv"
# ---------------------

def main():
    print("--- WiWave Motion Starting ---")
    
    # 1. Setup Logging
    if not os.path.exists("logs"):
        os.makedirs("logs")
    
    # Write header if file is new
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Signal", "Status", "Variance"])

    # 2. Initialize Components
    detector = MotionDetector(window_size=20, threshold=1.5)
    visualizer = WifiVisualizer(window_size=60) # Show 30 seconds of history
    
    print(f"Logging to: {LOG_FILE}")
    print("Close the graph window or press Ctrl+C to exit.")

    try:
        # Open log file in append mode
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            
            while not visualizer.is_closed():
                # A. Read Signal
                signal = get_wifi_signal()
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                if signal is not None:
                    # B. Detect Motion
                    detector.add_reading(signal)
                    status, variance = detector.get_motion_status()
                    
                    # C. Update Graph
                    visualizer.update(signal, status)
                    
                    # D. Log to CSV
                    writer.writerow([timestamp, signal, status, f"{variance:.2f}"])
                    f.flush()
                    
                    # E. Console Output
                    print(f"[{timestamp}] Signal: {signal}% | Var: {variance:.2f} | {status}")
                else:
                    print(f"[{timestamp}] WARNING: Wi-Fi signal lost! Check connection.")
                    visualizer.update(None, "DISCONNECTED")
                
                # Wait for next update
                time.sleep(UPDATE_INTERVAL)
                
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
    finally:
        print("--- WiWave Motion Stopped ---")

if __name__ == "__main__":
    main()
