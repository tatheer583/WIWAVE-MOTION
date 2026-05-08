import unittest
import numpy as np
from datetime import datetime, timedelta
from motion_detector import MotionDetector, DetectorConfig, fuse_distance_estimates

class TestMotionDetector(unittest.TestCase):
    def setUp(self):
        self.config = DetectorConfig(
            RSSI_WINDOW=10,
            RTT_WINDOW=50,
            MIN_BUFFER=20, # Lower for tests
            ENERGY_THRESHOLD_WALKING=5.0
        )
        self.detector = MotionDetector(sample_rate=10.0, config=self.config)
        self.start_time = datetime.now()

    def add_samples(self, count, base_value, noise_std):
        for i in range(count):
            val = base_value + np.random.normal(0, noise_std)
            ts = self.start_time + timedelta(seconds=i*0.1)
            self.detector.add_rtt(val, timestamp=ts)

    def test_initial_state(self):
        status, jitter, fall, progress, gesture = self.detector.get_motion_status()
        self.assertIn("LEARNING", status)
        self.assertEqual(jitter, 0.0)

    def test_calm_state(self):
        self.add_samples(25, 10.0, 0.1)
        status, jitter, fall, progress, gesture = self.detector.get_motion_status()
        self.assertIn("CALM", status)
        self.assertLess(jitter, 1.0)

    def test_walking_detection(self):
        self.add_samples(40, 10.0, 5.0)
        status, jitter, fall, progress, gesture = self.detector.get_motion_status()
        self.assertIn("WALKING", status)
        self.assertGreater(jitter, 5.0)

    def test_zero_variance_safety(self):
        self.add_samples(30, 10.0, 0.0)
        status, jitter, fall, progress, gesture = self.detector.get_motion_status()
        self.assertIn("CALM", status)
        self.assertEqual(jitter, 1e-9)

    def test_fusion_zero_sigma_safety(self):
        d, sigma = fuse_distance_estimates(5.0, 0.0, 5.0, 0.0)
        self.assertEqual(d, 5.0)
        self.assertGreater(sigma, 0.0)

    def test_distance_estimation(self):
        for _ in range(15):
            self.detector.add_rssi(90.0)
        
        dist = self.detector.get_estimated_distance()
        self.assertAlmostEqual(dist, 3.0, delta=1.0)
        
        for _ in range(10):
            self.detector.add_rssi(70.0)
        
        dist_new = self.detector.get_estimated_distance()
        self.assertGreater(dist_new, 3.0)

if __name__ == "__main__":
    unittest.main()
