"""
WiWave Motion - Main Entry Point (v3 Dual-Sensor)
================================================
How to run:
1. Ensure you are on a Windows laptop with Wi-Fi connected.
2. Install requirements: pip install -r requirements.txt
3. Run this file: python main.py

This script integrates the reader, logger, detector, and visualizer
to create a real-time Wi-Fi motion sensing dashboard.
"""

import time
import csv
import os
from datetime import datetime

# Import our custom modules
from wifi_reader import get_wifi_signal, get_ping_latency
from motion_detector import MotionDetector
from visualizer import WifiVisualizer

# --- CONFIGURATION ---
UPDATE_INTERVAL = 0.1  # Fast updates for micro-sensing (RTT)
LOG_FILE = "logs/wiwave_main_log.csv"
# ---------------------

def main():
    print("\n" + "="*40)
    print("   WiWave Motion: Intelligence Engine v4")
    print("="*40)
    
    # 1. Setup Logging
    if not os.path.exists("logs"):
        os.makedirs("logs")
    
    # Write header if file is new
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Signal", "RTT", "Status", "Variance", "Distance"])

    # 2. Initialize Components
    detector = MotionDetector(sample_rate=1.0/UPDATE_INTERVAL)
    visualizer = WifiVisualizer(window_size=100) 
    
    print(f"[*] Logging to: {LOG_FILE}")
    print("[*] Sensors: RSSI (Macro) + RTT (Micro)")
    print("[*] Close the graph window or press Ctrl+C to exit.")
    print("-" * 40)

    try:
        # Open log file in append mode
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            
            while not visualizer.is_closed():
                # A. Read Sensors
                signal = get_wifi_signal()
                rtt = get_ping_latency()
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                # B. Process Data
                detector.add_rssi(signal)
                detector.add_rtt(rtt)
                
                status, jitter, fall, progress, gesture, bpm = detector.get_motion_status()
                distance = detector.get_estimated_distance()
                
                # C. Update Graph (Using Signal for the main line)
                visualizer.update(signal, status)
                
                # D. Log to CSV
                writer.writerow([timestamp, signal, rtt, status, f"{jitter:.2f}", f"{distance:.2f}"])
                f.flush()
                
                # E. Console Output
                bpm_str = f"| BPM: {bpm:>3.0f}" if bpm else ""
                print(f"[{timestamp}] RTT: {rtt if rtt else '--':>4}ms | Var: {jitter:>5.2f} | Dist: {distance:>4.1f}m {bpm_str} | {status}")
                
                # Wait for next update
                time.sleep(UPDATE_INTERVAL)
                
    except KeyboardInterrupt:
        print("\n[!] Exiting gracefully...")
    finally:
        print("--- WiWave Motion Stopped ---")

if __name__ == "__main__":
    main()
