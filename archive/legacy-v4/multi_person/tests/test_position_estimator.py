"""Tests for the position estimator module."""

import pytest
import numpy as np
import time
from multi_person.modules.position_estimator import (
    PositionEstimator,
    PositionZone,
    APData,
    PersonPosition,
)
from multi_person.modules.signal_processor import SignalProcessor
from multi_person.modules.signal_separator import SignalSeparator


class TestPositionEstimatorBasic:
    """Tests for basic position estimator functionality."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        estimator = PositionEstimator()
        
        assert estimator.signal_processor is not None
        assert estimator.signal_separator is not None
        assert estimator.detection_area_width == 20.0
        assert estimator.update_rate_hz == 5.0
        assert len(estimator.ap_positions) == 3
        assert len(estimator.person_positions) == 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        processor = SignalProcessor()
        separator = SignalSeparator()
        
        estimator = PositionEstimator(
            signal_processor=processor,
            signal_separator=separator,
            detection_area_width=30.0,
            update_rate_hz=10.0,
        )
        
        assert estimator.signal_processor == processor
        assert estimator.signal_separator == separator
        assert estimator.detection_area_width == 30.0
        assert estimator.update_rate_hz == 10.0

    def test_estimate_position_empty_signal(self):
        """Test position estimation with empty signal."""
        estimator = PositionEstimator()
        
        result = estimator.estimate_position(None)
        
        assert result == (0.0, 0.0)

    def test_estimate_position_single_person(self):
        """Test position estimation for single person."""
        estimator = PositionEstimator()
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        result = estimator.estimate_position(signal)
        
        # Should return a valid position
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_estimate_positions_multiple(self):
        """Test position estimation for multiple people."""
        estimator = PositionEstimator()
        
        # Create multiple signals
        signals = []
        for i in range(3):
            np.random.seed(42 + i)
            rssi = np.random.normal(-70 - i * 2, 5, 100)
            rtt = np.random.normal(0.5 + i * 0.05, 0.1, 100)
            signals.append({'rssi': rssi.tolist(), 'rtt': rtt.tolist()})
        
        results = estimator.estimate_positions(signals)
        
        assert len(results) == 3
        for pos in results:
            assert isinstance(pos, tuple)
            assert len(pos) == 2


class TestPositionZoneAssignment:
    """Tests for position zone assignment."""

    def test_get_position_zone_left(self):
        """Test zone assignment for left position."""
        estimator = PositionEstimator()
        
        zone = estimator.get_position_zone((-5.0, 2.0))
        
        assert zone == 'left'

    def test_get_position_zone_center(self):
        """Test zone assignment for center position."""
        estimator = PositionEstimator()
        
        zone = estimator.get_position_zone((0.0, 2.0))
        
        assert zone == 'center'

    def test_get_position_zone_right(self):
        """Test zone assignment for right position."""
        estimator = PositionEstimator()
        
        zone = estimator.get_position_zone((5.0, 2.0))
        
        assert zone == 'right'

    def test_get_position_zone_outside(self):
        """Test zone assignment for position outside zones."""
        estimator = PositionEstimator()
        
        # Far left (beyond left zone)
        zone_left = estimator.get_position_zone((-15.0, 2.0))
        assert zone_left == 'left'  # Still in left zone range
        
        # Far right (beyond right zone)
        zone_right = estimator.get_position_zone((15.0, 2.0))
        assert zone_right == 'right'  # Still in right zone range

    def test_zone_ranges(self):
        """Test zone x-coordinate ranges."""
        estimator = PositionEstimator()
        
        # Left zone: -10.0 to -3.0
        assert estimator.get_position_zone((-10.0, 0.0)) == 'left'
        assert estimator.get_position_zone((-3.1, 0.0)) == 'left'
        
        # Center zone: -3.0 to 3.0
        assert estimator.get_position_zone((-3.0, 0.0)) == 'center'
        assert estimator.get_position_zone((0.0, 0.0)) == 'center'
        assert estimator.get_position_zone((3.0, 0.0)) == 'center'
        
        # Right zone: 3.0 to 10.0
        assert estimator.get_position_zone((3.1, 0.0)) == 'right'
        assert estimator.get_position_zone((10.0, 0.0)) == 'right'


class TestCrossViewpointFusion:
    """Tests for cross-viewpoint fusion."""

    def test_fuse_cross_viewpoint_empty(self):
        """Test fusion with empty AP data."""
        estimator = PositionEstimator()
        
        result = estimator.fuse_cross_viewpoint({})
        
        assert result == (0.0, 0.0)

    def test_fuse_cross_viewpoint_single_ap(self):
        """Test fusion with single access point."""
        estimator = PositionEstimator()
        
        ap_data = {
            'ap1': {
                'rssi': -70.0,
                'rtt': 0.5,
                'timestamp': time.time(),
            }
        }
        
        result = estimator.fuse_cross_viewpoint(ap_data)
        
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_fuse_cross_viewpoint_multiple_aps(self):
        """Test fusion with multiple access points."""
        estimator = PositionEstimator()
        
        ap_data = {
            'ap1': {'rssi': -70.0, 'rtt': 0.5, 'timestamp': time.time()},
            'ap2': {'rssi': -68.0, 'rtt': 0.52, 'timestamp': time.time()},
            'ap3': {'rssi': -72.0, 'rtt': 0.48, 'timestamp': time.time()},
        }
        
        result = estimator.fuse_cross_viewpoint(ap_data)
        
        # Should return a valid position
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_fuse_cross_viewpoint_weighted_by_rssi(self):
        """Test that fusion weights by signal strength."""
        estimator = PositionEstimator()
        
        # Strong signal from center AP
        ap_data = {
            'ap1': {'rssi': -90.0, 'rtt': 0.8, 'timestamp': time.time()},  # Weak
            'ap2': {'rssi': -60.0, 'rtt': 0.5, 'timestamp': time.time()},  # Strong
            'ap3': {'rssi': -90.0, 'rtt': 0.8, 'timestamp': time.time()},  # Weak
        }
        
        result = estimator.fuse_cross_viewpoint(ap_data)
        
        # Result should be closer to center AP position (0, 0)
        x, y = result
        assert abs(x) < 5.0  # Should be near center
        assert y > 0  # Should be in front

    def test_fuse_cross_viewpoint_with_custom_ap_positions(self):
        """Test fusion with custom AP positions."""
        estimator = PositionEstimator(
            ap_positions={
                'ap1': (-10.0, 5.0),
                'ap2': (0.0, 5.0),
                'ap3': (10.0, 5.0),
            }
        )
        
        ap_data = {
            'ap1': {'rssi': -70.0, 'rtt': 0.5, 'timestamp': time.time()},
            'ap2': {'rssi': -68.0, 'rtt': 0.52, 'timestamp': time.time()},
        }
        
        result = estimator.fuse_cross_viewpoint(ap_data)
        
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestPositionUpdateRate:
    """Tests for position update rate limiting."""

    def test_update_position_rate_limit(self):
        """Test that position updates are rate-limited to 5 Hz."""
        estimator = PositionEstimator(update_rate_hz=5.0)
        
        # First update should succeed
        result1 = estimator.update_position(1, 'center')
        assert result1 is True
        
        # Immediate second update should be rate-limited
        result2 = estimator.update_position(1, 'left')
        assert result2 is False  # Rate limited

    def test_update_position_valid_after_interval(self):
        """Test that updates succeed after rate limit interval."""
        estimator = PositionEstimator(update_rate_hz=5.0)  # 200ms interval
        
        # First update
        result1 = estimator.update_position(1, 'center')
        assert result1 is True
        
        # Wait for interval
        time.sleep(0.25)
        
        # Second update should succeed
        result2 = estimator.update_position(1, 'left')
        assert result2 is True

    def test_update_position_different_persons(self):
        """Test that rate limiting is per-person."""
        estimator = PositionEstimator(update_rate_hz=5.0)
        
        # Person 1 updates
        result1 = estimator.update_position(1, 'center')
        assert result1 is True
        
        # Person 2 updates immediately (should succeed)
        result2 = estimator.update_position(2, 'left')
        assert result2 is True
        
        # Person 1 updates again immediately (should fail)
        result3 = estimator.update_position(1, 'right')
        assert result3 is False


class TestZoneCongestionDetection:
    """Tests for zone congestion detection."""

    def test_detect_zone_congestion_empty(self):
        """Test congestion detection for empty zone."""
        estimator = PositionEstimator()
        
        is_congested = estimator.detect_zone_congestion('center', threshold=2)
        
        assert is_congested is False

    def test_detect_zone_congestion_below_threshold(self):
        """Test congestion detection when below threshold."""
        estimator = PositionEstimator()
        
        # Add 1 person to zone
        estimator.update_position(1, 'center')
        
        is_congested = estimator.detect_zone_congestion('center', threshold=3)
        
        assert is_congested is False

    def test_detect_zone_congestion_at_threshold(self):
        """Test congestion detection at threshold."""
        estimator = PositionEstimator()
        
        # Add 2 people to zone (threshold = 2)
        estimator.update_position(1, 'center')
        estimator.update_position(2, 'center')
        
        is_congested = estimator.detect_zone_congestion('center', threshold=2)
        
        assert is_congested is True

    def test_detect_zone_congestion_above_threshold(self):
        """Test congestion detection above threshold."""
        estimator = PositionEstimator()
        
        # Add 3 people to zone (threshold = 2)
        estimator.update_position(1, 'center')
        estimator.update_position(2, 'center')
        estimator.update_position(3, 'center')
        
        is_congested = estimator.detect_zone_congestion('center', threshold=2)
        
        assert is_congested is True

    def test_get_all_zones_congestion(self):
        """Test getting congestion status for all zones."""
        estimator = PositionEstimator()
        
        # Add people to different zones
        estimator.update_position(1, 'left')
        estimator.update_position(2, 'left')
        estimator.update_position(3, 'center')
        
        congestion = estimator.get_all_zones_congestion()
        
        assert 'left' in congestion
        assert 'center' in congestion
        assert 'right' in congestion
        assert congestion['left'] is True  # 2 people, threshold 2
        assert congestion['center'] is False  # 1 person
        assert congestion['right'] is False  # 0 people

    def test_get_zone_persons(self):
        """Test getting list of persons in a zone."""
        estimator = PositionEstimator()
        
        # Add people to zones
        estimator.update_position(1, 'left')
        estimator.update_position(2, 'left')
        estimator.update_position(3, 'center')
        
        left_persons = estimator.get_zone_persons('left')
        center_persons = estimator.get_zone_persons('center')
        right_persons = estimator.get_zone_persons('right')
        
        assert len(left_persons) == 2
        assert 1 in left_persons
        assert 2 in left_persons
        assert len(center_persons) == 1
        assert 3 in center_persons
        assert len(right_persons) == 0


class TestPersonPositionTracking:
    """Tests for person position tracking."""

    def test_get_person_position(self):
        """Test getting person position."""
        estimator = PositionEstimator()
        
        estimator.update_position(1, 'center')
        
        position = estimator.get_person_position(1)
        
        assert position is not None
        assert position.person_id == 1
        assert position.zone == 'center'

    def test_get_person_position_not_found(self):
        """Test getting non-existent person position."""
        estimator = PositionEstimator()
        
        position = estimator.get_person_position(999)
        
        assert position is None

    def test_reset(self):
        """Test resetting the estimator."""
        estimator = PositionEstimator()
        
        # Add some data
        estimator.update_position(1, 'center')
        estimator.update_position(2, 'left')
        
        # Reset
        estimator.reset()
        
        assert len(estimator.person_positions) == 0
        assert len(estimator.last_update_times) == 0
        assert len(estimator.zone_persons) == 0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_estimate_position_with_outliers(self):
        """Test position estimation with outlier data."""
        estimator = PositionEstimator()
        
        # Signal with some outliers
        rssi_values = [-70] * 95 + [-100, -100, -100, -100, -100]  # 5 outliers
        rtt_values = [0.5] * 100
        
        signal = {'rssi': rssi_values, 'rtt': rtt_values}
        result = estimator.estimate_position(signal)
        
        # Should handle gracefully
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_estimate_position_with_single_sample(self):
        """Test position estimation with single sample."""
        estimator = PositionEstimator()
        
        signal = {'rssi': [-70.0], 'rtt': [0.5]}
        result = estimator.estimate_position(signal)
        
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_estimate_positions_empty_list(self):
        """Test position estimation with empty list."""
        estimator = PositionEstimator()
        
        results = estimator.estimate_positions([])
        
        assert results == []

    def test_fuse_cross_viewpoint_with_missing_data(self):
        """Test fusion with incomplete AP data."""
        estimator = PositionEstimator()
        
        ap_data = {
            'ap1': {'rssi': -70.0},  # Missing rtt
            'ap2': {'rtt': 0.5},      # Missing rssi
        }
        
        result = estimator.fuse_cross_viewpoint(ap_data)
        
        # Should handle gracefully with defaults
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_update_position_with_invalid_zone(self):
        """Test position update with invalid zone."""
        estimator = PositionEstimator()
        
        # Should handle invalid zone gracefully
        result = estimator.update_position(1, 'invalid_zone')
        
        # Should still return True (update succeeded)
        assert result is True

    def test_rssi_to_distance_conversion(self):
        """Test RSSI to distance conversion."""
        estimator = PositionEstimator()
        
        # Strong signal = close distance
        distance_strong = estimator._rssi_to_distance(-30.0)
        
        # Weak signal = far distance
        distance_weak = estimator._rssi_to_distance(-90.0)
        
        assert distance_strong < distance_weak
        assert distance_strong > 0
        assert distance_weak > distance_strong

    def test_position_zone_dataclass(self):
        """Test PositionZone dataclass."""
        zone = PositionZone(
            zone_id='test',
            x_range=(-5.0, 5.0),
            name='Test Zone',
        )
        
        assert zone.zone_id == 'test'
        assert zone.x_range == (-5.0, 5.0)
        assert zone.name == 'Test Zone'

    def test_ap_data_dataclass(self):
        """Test APData dataclass."""
        ap_data = APData(
            ap_id='ap1',
            position=(0.0, 0.0),
            rssi=-70.0,
            rtt=0.5,
        )
        
        assert ap_data.ap_id == 'ap1'
        assert ap_data.position == (0.0, 0.0)
        assert ap_data.rssi == -70.0
        assert ap_data.rtt == 0.5

    def test_person_position_dataclass(self):
        """Test PersonPosition dataclass."""
        person_pos = PersonPosition(
            person_id=1,
            position=(2.0, 3.0),
            zone='center',
            confidence=0.9,
        )
        
        assert person_pos.person_id == 1
        assert person_pos.position == (2.0, 3.0)
        assert person_pos.zone == 'center'
        assert person_pos.confidence == 0.9


class TestPositionEstimatorIntegration:
    """Integration tests for position estimator."""

    def test_full_pipeline(self):
        """Test complete position estimation pipeline."""
        estimator = PositionEstimator()
        
        # Create multi-person signals
        signals = []
        for i in range(3):
            np.random.seed(42 + i)
            rssi = np.random.normal(-70 - i * 2, 5, 100)
            rtt = np.random.normal(0.5 + i * 0.05, 0.1, 100)
            signals.append({'rssi': rssi.tolist(), 'rtt': rtt.tolist()})
        
        # Estimate positions
        positions = estimator.estimate_positions(signals)
        assert len(positions) == 3
        
        # Get zones for each position
        zones = [estimator.get_position_zone(pos) for pos in positions]
        assert len(zones) == 3
        
        # Update positions
        for i, (pos, zone) in enumerate(zip(positions, zones)):
            estimator.update_position(i + 1, zone)
        
        # Verify tracking
        for i in range(1, 4):
            person_pos = estimator.get_person_position(i)
            assert person_pos is not None
            assert person_pos.person_id == i

    def test_cross_viewpoint_with_realistic_data(self):
        """Test cross-viewpoint fusion with realistic data."""
        estimator = PositionEstimator()
        
        # Simulate signals from 3 APs for a person in center
        ap_data = {
            'ap1': {'rssi': -75.0, 'rtt': 0.55, 'timestamp': time.time()},  # Left AP
            'ap2': {'rssi': -68.0, 'rtt': 0.50, 'timestamp': time.time()},  # Center AP (stronger)
            'ap3': {'rssi': -75.0, 'rtt': 0.55, 'timestamp': time.time()},  # Right AP
        }
        
        # Fuse positions
        fused_position = estimator.fuse_cross_viewpoint(ap_data)
        
        # Should be near center (0, 0)
        x, y = fused_position
        assert abs(x) < 5.0
        assert y > 0

    def test_zone_congestion_workflow(self):
        """Test complete zone congestion detection workflow."""
        estimator = PositionEstimator()
        
        # Simulate 3 people entering center zone
        for i in range(1, 4):
            estimator.update_position(i, 'center')
        
        # Check congestion
        assert estimator.detect_zone_congestion('center', threshold=3) is True
        
        # Add more people
        for i in range(4, 6):
            estimator.update_position(i, 'center')
        
        # Should still be congested
        assert estimator.detect_zone_congestion('center', threshold=2) is True
        
        # Check all zones
        congestion = estimator.get_all_zones_congestion()
        assert congestion['center'] is True
        assert congestion['left'] is False
        assert congestion['right'] is False
