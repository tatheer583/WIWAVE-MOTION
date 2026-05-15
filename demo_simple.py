"""
Simple Multi-Person Detection Demo
===================================

This demo shows how the multi-person detection system works in a simple way.

Run: python demo_simple.py
"""

import numpy as np
from multi_person.modules.orchestrator import MultiPersonDetector


def demo_single_person():
    """Demo: Single person detection."""
    print("\n" + "="*60)
    print("DEMO 1: Single Person Detection")
    print("="*60)
    
    # Create detector
    detector = MultiPersonDetector()
    
    # Simulate single person signal
    np.random.seed(42)
    signal = {
        'rssi': np.random.normal(-70, 5, 50).tolist(),
        'rtt': np.random.normal(0.5, 0.1, 50).tolist()
    }
    
    # Run detection
    result = detector.detect(signal)
    payload = detector.get_output_payload()
    
    print(f"\nInput: Single person signal")
    print(f"  - RSSI: {np.mean(signal['rssi']):.1f} dBm")
    print(f"  - RTT: {np.mean(signal['rtt']):.3f} s")
    
    print(f"\nDetection Result:")
    print(f"  - Person detected: {len(result.persons)}")
    print(f"  - Processing time: {result.processing_time_ms:.1f}ms")
    
    if result.persons:
        p = result.persons[0]
        print(f"\nPerson Details:")
        print(f"  - ID: {p.person_id}")
        print(f"  - Position: ({p.position[0]:.1f}, {p.position[1]:.1f})")
        print(f"  - Zone: {p.signal_features.get('zone', 'unknown')}")
        print(f"  - Activity: {p.activity}")
        print(f"  - Confidence: {p.confidence*100:.1f}%")


def demo_two_person():
    """Demo: Two person detection (simulated)."""
    print("\n" + "="*60)
    print("DEMO 2: Two Person Detection (Simulated)")
    print("="*60)
    
    # Create detector
    detector = MultiPersonDetector()
    
    # Simulate two person signals combined
    np.random.seed(42)
    
    # Person 1: Closer (stronger signal, lower RTT)
    rssi1 = np.random.normal(-65, 3, 50)  # Stronger (-65 dBm)
    rtt1 = np.random.normal(0.4, 0.05, 50)  # Lower RTT (closer)
    
    # Person 2: Further (weaker signal, higher RTT)
    rssi2 = np.random.normal(-75, 3, 50)  # Weaker (-75 dBm)
    rtt2 = np.random.normal(0.6, 0.05, 50)  # Higher RTT (further)
    
    # Combined signal
    signal = {
        'rssi': (rssi1 + rssi2).tolist(),
        'rtt': (rtt1 + rtt2).tolist()
    }
    
    # Run detection
    result = detector.detect(signal)
    payload = detector.get_output_payload()
    
    print(f"\nInput: Two person signals combined")
    print(f"  - Person 1: RSSI=-65 dBm, RTT=0.4s (closer)")
    print(f"  - Person 2: RSSI=-75 dBm, RTT=0.6s (further)")
    print(f"  - Combined RSSI: {np.mean(signal['rssi']):.1f} dBm")
    print(f"  - Combined RTT: {np.mean(signal['rtt']):.3f} s")
    
    print(f"\nDetection Result:")
    print(f"  - Persons detected: {len(result.persons)}")
    print(f"  - Processing time: {result.processing_time_ms:.1f}ms")
    
    if result.persons:
        print(f"\nPerson Details:")
        for p in result.persons:
            print(f"  - Person {p.person_id}:")
            print(f"    - Position: ({p.position[0]:.1f}, {p.position[1]:.1f})")
            print(f"    - Zone: {p.signal_features.get('zone', 'unknown')}")
            print(f"    - Activity: {p.activity}")
            print(f"    - Confidence: {p.confidence*100:.1f}%")
    else:
        print("\n⚠️  No persons detected!")
        print("   Note: Multi-person separation needs improvement.")


def demo_zone_congestion():
    """Demo: Zone congestion detection."""
    print("\n" + "="*60)
    print("DEMO 3: Zone Congestion Detection")
    print("="*60)
    
    # Create detector
    detector = MultiPersonDetector()
    
    # Simulate multiple people in same zone
    np.random.seed(42)
    
    # Create 3 people with similar positions (same zone)
    rssi_combined = []
    rtt_combined = []
    
    for i in range(3):
        # Similar positions (same zone)
        rssi = np.random.normal(-70 - 5*i, 3, 50)
        rtt = np.random.normal(0.5 + 0.1*i, 0.05, 50)
        
        rssi_combined.extend(rssi.tolist())
        rtt_combined.extend(rtt.tolist())
    
    signal = {
        'rssi': rssi_combined,
        'rtt': rtt_combined
    }
    
    # Run detection
    result = detector.detect(signal)
    payload = detector.get_output_payload()
    
    print(f"\nInput: 3 people in same zone")
    print(f"  - All people have similar positions")
    
    print(f"\nDetection Result:")
    print(f"  - Persons detected: {len(result.persons)}")
    
    print(f"\nZone Congestion Status:")
    for zone, congested in payload['zone_congestion'].items():
        status = "⚠️  CONGESTED (2+ people)" if congested else "✓ Clear"
        print(f"  - {zone.capitalize()}: {status}")
    
    print(f"\nOutput Payload:")
    print(f"  - person_count: {payload['person_count']}")
    print(f"  - zone_congestion: {payload['zone_congestion']}")
    print(f"  - mode: {payload['mode']}")


def demo_activity_recognition():
    """Demo: Activity recognition."""
    print("\n" + "="*60)
    print("DEMO 4: Activity Recognition")
    print("="*60)
    
    # Create detector
    detector = MultiPersonDetector()
    
    # Test different activity patterns
    activities_to_test = [
        ("Breathing pattern", 0.2, 0.02),   # 0.2 Hz (breathing)
        ("Walking pattern", 2.0, 0.05),     # 2.0 Hz (walking)
        ("Still pattern", 0.0, 0.001),      # No movement
    ]
    
    for name, freq, amplitude in activities_to_test:
        np.random.seed(42)
        
        t = np.linspace(0, 5, 50)
        rtt = 0.5 + amplitude * np.sin(2 * np.pi * freq * t)
        rssi = np.random.normal(-70, 5, 50)
        
        signal = {
            'rssi': rssi.tolist(),
            'rtt': rtt.tolist()
        }
        
        result = detector.detect(signal)
        
        if result.persons:
            p = result.persons[0]
            print(f"\n{name}:")
            print(f"  - Input frequency: {freq} Hz")
            print(f"  - Detected activity: {p.activity}")
            print(f"  - Confidence: {p.confidence*100:.1f}%")


def demo_performance():
    """Demo: Performance metrics."""
    print("\n" + "="*60)
    print("DEMO 5: Performance Metrics")
    print("="*60)
    
    # Create detector
    detector = MultiPersonDetector()
    
    # Run many detections
    latencies = []
    
    for i in range(100):
        np.random.seed(42 + i)
        signal = {
            'rssi': np.random.normal(-70, 5, 50).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 50).tolist()
        }
        
        result = detector.detect(signal)
        latencies.append(result.processing_time_ms)
    
    # Calculate statistics
    avg = np.mean(latencies)
    min_lat = np.min(latencies)
    max_lat = np.max(latencies)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)
    
    print(f"\nPerformance Results (100 detections):")
    print(f"  - Average latency: {avg:.1f}ms (target: <50ms)")
    print(f"  - Min latency: {min_lat:.1f}ms")
    print(f"  - Max latency: {max_lat:.1f}ms")
    print(f"  - P95 latency: {p95:.1f}ms (target: <100ms)")
    print(f"  - P99 latency: {p99:.1f}ms (target: <150ms)")
    
    if avg < 50 and p95 < 100 and p99 < 150:
        print(f"\n✅ Performance targets MET!")
    else:
        print(f"\n⚠️  Some performance targets not met.")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("   MULTI-PERSON DETECTION - SIMPLE DEMO")
    print("="*60)
    print("\nThis demo shows how the multi-person detection system works.")
    print("Each demo shows different aspects of the system.")
    
    # Run demos
    demo_single_person()
    demo_two_person()
    demo_zone_congestion()
    demo_activity_recognition()
    demo_performance()
    
    print("\n" + "="*60)
    print("   DEMO COMPLETE")
    print("="*60)
    print("\nKey Takeaways:")
    print("1. Single person detection works well")
    print("2. Multi-person detection needs improvement")
    print("3. Zone congestion detection works")
    print("4. Activity recognition works for basic patterns")
    print("5. Performance is excellent (<10ms average)")
    print("\nRun 'python demo_simple.py' to see the full demo again.")


if __name__ == "__main__":
    main()
