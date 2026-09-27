"""
Real WiFi Human Detection Demo
================================

This demo shows the system working with REAL WiFi signals from your hardware.

Run: python demo_real_wifi.py
"""

import time
import asyncio
import numpy as np
from wifi_reader import create_wifi_reader
from motion_detector import MotionDetector
from multi_person.modules.orchestrator import MultiPersonDetector


def demo_real_wifi_detection():
    """Demo: Real WiFi human detection using actual hardware."""
    print("\n" + "="*60)
    print("REAL WiFi Human Detection Demo")
    print("="*60)
    
    # Initialize WiFi reader (real hardware)
    print("\n[*] Initializing WiFi hardware...")
    try:
        reader = create_wifi_reader()
        print(f"[✓] WiFi hardware initialized")
        print(f"    Connected AP: {reader.get_rssi()}% signal strength")
    except Exception as e:
        print(f"[!] WiFi hardware error: {e}")
        return
    
    # Initialize detectors
    print("\n[*] Initializing motion detectors...")
    detector = MotionDetector()
    multi_detector = MultiPersonDetector()
    print("[✓] Detectors initialized")
    
    # Run real-time detection loop
    print("\n[*] Starting real-time detection (Ctrl+C to stop)...")
    print("-"*60)
    
    try:
        frame_count = 0
        while True:
            frame_count += 1
            
            # Get REAL WiFi data from hardware
            rssi = reader.get_rssi()
            rtt = asyncio.run(reader.get_rtt())
            
            if rssi is None:
                print(f"[{frame_count}] No WiFi signal detected")
                time.sleep(0.5)
                continue
            
            # Convert RSSI % to dBm for processing
            rssi_dbm = -100 + (rssi * 0.7)  # Map 0-100% to -100 to -30 dBm
            
            # Process with single-person detector
            detector.add_rssi(rssi_dbm)
            detector.add_rtt(rtt if rtt else 50)
            
            status, jitter, fall, learn, gesture, bpm, b_hz, w_energy = detector.get_motion_status()
            distance = detector.get_estimated_distance()
            
            # Process with multi-person detector
            raw_signal = {"rssi": rssi_dbm, "rtt": rtt if rtt else 50}
            mp_result = multi_detector.detect(raw_signal)
            mp_payload = multi_detector.get_output_payload()
            
            # Display results
            print(f"\n[{frame_count}] Real WiFi Data:")
            print(f"    RSSI: {rssi}% ({rssi_dbm:.1f} dBm)")
            print(f"    RTT: {rtt if rtt else 50:.1f}ms")
            
            print(f"\n    Single-Person Detection:")
            print(f"    - Status: {status}")
            print(f"    - Jitter: {jitter:.2f}")
            print(f"    - Distance: {distance:.1f}m")
            if bpm:
                print(f"    - Heart Rate: {bpm:.0f} BPM")
            
            print(f"\n    Multi-Person Detection:")
            print(f"    - Persons detected: {mp_payload['person_count']}")
            print(f"    - Mode: {mp_payload['mode']}")
            print(f"    - Zone congestion: {mp_payload['zone_congestion']}")
            
            if mp_payload['person_count'] > 0 and mp_payload['persons']:
                p = mp_payload['persons'][0]
                print(f"    - Person 1:")
                print(f"      - Activity: {p['activity']}")
                print(f"      - Zone: {p['position_zone']}")
                print(f"      - Confidence: {p['confidence']}%")
            
            # Small delay
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n[!] Detection stopped by user")
    finally:
        print("\n[!] Cleanup complete")


def demo_wifi_signal_analysis():
    """Demo: Analyze WiFi signal characteristics."""
    print("\n" + "="*60)
    print("WiFi Signal Analysis Demo")
    print("="*60)
    
    try:
        reader = create_wifi_reader()
        print("\n[*] Scanning WiFi environment...")
        
        # Get RSSI
        rssi = reader.get_rssi()
        print(f"\n[*] Connected AP Signal: {rssi}%")
        
        # Get all visible APs
        aps = reader.get_all_aps()
        print(f"\n[*] Visible Access Points: {len(aps)}")
        for ap in aps:
            print(f"    - {ap['ssid']}")
            print(f"      BSSID: {ap['bssid']}")
            print(f"      Signal: {ap['signal']}%")
        
        # Test RTT
        print(f"\n[*] Testing RTT (ping latency)...")
        import asyncio
        rtt = asyncio.run(reader.get_rtt())
        print(f"    RTT to 1.1.1.1: {rtt:.1f}ms")
        
        print("\n[✓] WiFi signal analysis complete")
        
    except Exception as e:
        print(f"[!] Error: {e}")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("   REAL WiFi Human Detection System")
    print("="*60)
    print("\nThis demo uses REAL WiFi hardware to detect human motion.")
    print("It analyzes RSSI and RTT signals to detect people.")
    
    # Run demos
    demo_wifi_signal_analysis()
    demo_real_wifi_detection()
    
    print("\n" + "="*60)
    print("   DEMO COMPLETE")
    print("="*60)
    print("\nKey Points:")
    print("1. System uses REAL WiFi hardware (not simulation)")
    print("2. Analyzes RSSI (signal strength) and RTT (ping latency)")
    print("3. Detects human motion through signal variations")
    print("4. Multi-person detection is integrated")
    print("\nRun 'python demo_real_wifi.py' to see real WiFi detection!")


if __name__ == "__main__":
    main()
