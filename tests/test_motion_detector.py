import unittest
import numpy as np
from motion_detector import MotionDetector, DetectorConfig

class TestMotionDetector(unittest.TestCase):
    def setUp(self):
        self.config = DetectorConfig(
            RSSI_WINDOW=10,
            RTT_WINDOW=20,
            ENERGY_THRESHOLD_WALKING=5.0
        )
        self.detector = MotionDetector(sample_rate=10.0, config=self.config)

    def test_initial_state(self):
        status, jitter = self.detector.get_motion_status()
        self.assertEqual(status, "LEARNING ENVIRONMENT...")
        self.assertEqual(jitter, 0.0)

    def test_calm_state(self):
        # Add 20 samples of steady RTT
        for _ in range(25):
            self.detector.add_rtt(10.0 + np.random.normal(0, 0.1))
        
        status, jitter = self.detector.get_motion_status()
        self.assertIn("CALM", status)
        self.assertLess(jitter, 1.0)

    def test_walking_detection(self):
        # Add 40 samples of high jitter RTT (simulating walking)
        for _ in range(40):
            self.detector.add_rtt(10.0 + np.random.normal(0, 5.0))
        
        status, jitter = self.detector.get_motion_status()
        self.assertIn("WALKING", status)
        self.assertGreater(jitter, 5.0)

    def test_distance_estimation(self):
        # Baseline at 90% signal
        for _ in range(15):
            self.detector.add_rssi(90.0)
        
        # Distance at baseline should be around d_ref (3.0m)
        dist = self.detector.get_estimated_distance()
        self.assertAlmostEqual(dist, 3.0, delta=0.5)
        
        # Signal drops (moving away)
        for _ in range(10):
            self.detector.add_rssi(70.0)
        
        dist_new = self.detector.get_estimated_distance()
        self.assertGreater(dist_new, 3.0)

if __name__ == "__main__":
    unittest.main()
