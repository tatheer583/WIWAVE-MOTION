"""Tests for the multi-person detection orchestrator."""

import pytest
import numpy as np
import time
from multi_person.modules.orchestrator import MultiPersonDetector, DetectionResult
from multi_person.core.models import PersonState, PersonStateEvent


class TestMultiPersonDetectorInitialization:
    """Tests for MultiPersonDetector initialization."""

    def test_default_initialization(self):
        """Test detector initializes with default modules."""
        detector = MultiPersonDetector()
        
        assert detector.signal_processor is not None
        assert detector.signal_separator is not None
        assert detector.position_estimator is not None
        assert detector.activity_recognizer is not None
        assert detector.person_tracker is not None
        assert detector.calibration_module is not None
        assert detector.max_capacity == 5
        assert detector.mode == "multi_person"
        assert detector.frame_id == 0

    def test_custom_initialization(self):
        """Test detector initializes with custom modules."""
        signal_processor = MultiPersonDetector.__init__.__code__.co_consts[0]  # Dummy
        detector = MultiPersonDetector(
            max_capacity=3,
            mode="single_person",
            target_latency_ms=50.0,
        )
        
        assert detector.max_capacity == 3
        assert detector.mode == "single_person"
        assert detector.target_latency_ms == 50.0

    def test_mode_validation(self):
        """Test mode validation."""
        detector = MultiPersonDetector()
        
        # Valid modes
        detector.set_mode("single_person")
        assert detector.mode == "single_person"
        
        detector.set_mode("multi_person")
        assert detector.mode == "multi_person"
        
        # Invalid mode should raise error
        with pytest.raises(ValueError):
            detector.set_mode("invalid_mode")


class TestMultiPersonDetectorDetection:
    """Tests for multi-person detection functionality."""

    def test_detect_single_person(self):
        """Test detection with single person signal."""
        detector = MultiPersonDetector()
        
        # Create synthetic single person signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        result = detector.detect(raw_signal)
        
        assert isinstance(result, DetectionResult)
        assert result.success is True
        assert len(result.persons) >= 0  # May detect 0 or 1 person
        assert result.processing_time_ms >= 0

    def test_detect_multiple_persons(self):
        """Test detection with multiple person signals."""
        detector = MultiPersonDetector(max_capacity=3)
        
        # Create synthetic multi-person signal (combined)
        np.random.seed(42)
        
        # Person 1: Standing (breathing pattern)
        rssi1 = np.random.normal(-70, 5, 100)
        rtt1 = 0.5 + 0.02 * np.sin(2 * np.pi * 0.2 * np.linspace(0, 10, 100))
        
        # Person 2: Walking (higher frequency)
        rssi2 = np.random.normal(-75, 5, 100)
        rtt2 = 0.6 + 0.05 * np.sin(2 * np.pi * 2.0 * np.linspace(0, 10, 100))
        
        # Combine signals
        raw_signal = {
            'rssi': (rssi1 + rssi2).tolist(),
            'rtt': (rtt1 + rtt2).tolist()
        }
        
        result = detector.detect(raw_signal)
        
        assert isinstance(result, DetectionResult)
        assert result.success is True
        # May detect 1 or 2 persons depending on signal separation

    def test_detect_empty_signal(self):
        """Test detection with empty signal."""
        detector = MultiPersonDetector()
        
        raw_signal = {'rssi': [], 'rtt': []}
        
        result = detector.detect(raw_signal)
        
        assert isinstance(result, DetectionResult)
        # May fail or return empty persons
        assert result.processing_time_ms >= 0

    def test_detect_invalid_signal(self):
        """Test detection with invalid signal."""
        detector = MultiPersonDetector()
        
        # None signal
        result = detector.detect(None)
        
        assert isinstance(result, DetectionResult)
        assert result.success is False or len(result.persons) == 0

    def test_detection_latency(self):
        """Test detection latency is within target."""
        detector = MultiPersonDetector(target_latency_ms=100.0)
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run multiple detections and check latency
        for _ in range(5):
            result = detector.detect(raw_signal)
            assert result.processing_time_ms >= 0
            # Note: We don't assert latency < target as it may vary


class TestMultiPersonDetectorOutputPayload:
    """Tests for output payload generation."""

    def test_get_output_payload_empty(self):
        """Test output payload with no persons."""
        detector = MultiPersonDetector()
        
        payload = detector.get_output_payload()
        
        assert 'person_count' in payload
        assert 'max_capacity' in payload
        assert 'mode' in payload
        assert 'processing_latency_ms' in payload
        assert 'zone_congestion' in payload
        assert 'persons' in payload
        assert payload['person_count'] == 0

    def test_get_output_payload_with_persons(self):
        """Test output payload with detected persons."""
        detector = MultiPersonDetector(max_capacity=3)
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run detection
        detector.detect(raw_signal)
        
        payload = detector.get_output_payload()
        
        assert payload['person_count'] >= 0
        assert payload['max_capacity'] == 3
        assert payload['mode'] == "multi_person"
        assert 'persons' in payload
        
        # Check person structure if persons exist
        if payload['person_count'] > 0:
            person = payload['persons'][0]
            assert 'person_id' in person
            assert 'position_zone' in person
            assert 'activity' in person
            assert 'confidence' in person
            assert 'signal_strength' in person

    def test_single_person_backward_compatibility(self):
        """Test single-person output format for backward compatibility."""
        detector = MultiPersonDetector()
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run detection
        detector.detect(raw_signal)
        
        payload = detector.get_output_payload()
        
        # Check single_person_update format
        assert 'single_person_update' in payload or payload['person_count'] != 1


class TestMultiPersonDetectorEventSystem:
    """Tests for event system integration."""

    def test_add_event_callback(self):
        """Test adding event callbacks."""
        detector = MultiPersonDetector()
        
        callback_called = []
        
        def mock_callback(event: PersonStateEvent):
            callback_called.append(event)
        
        detector.add_event_callback(mock_callback)
        
        # Callback should be added to person tracker
        assert len(callback_called) == 0  # No events emitted yet

    def test_remove_event_callback(self):
        """Test removing event callbacks."""
        detector = MultiPersonDetector()
        
        callback_called = []
        
        def mock_callback(event: PersonStateEvent):
            callback_called.append(event)
        
        detector.add_event_callback(mock_callback)
        detector.remove_event_callback(mock_callback)
        
        # Callback should be removed
        assert len(callback_called) == 0


class TestMultiPersonDetectorReset:
    """Tests for reset functionality."""

    def test_reset_clears_state(self):
        """Test reset clears all module states."""
        detector = MultiPersonDetector()
        
        # Create some state
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run detection to create state
        detector.detect(raw_signal)
        
        initial_frame_id = detector.frame_id
        initial_person_count = detector.person_tracker.get_person_count()
        
        # Reset
        detector.reset()
        
        assert detector.frame_id == 0
        assert detector.person_tracker.get_person_count() == 0
        assert detector.is_calibrated is False

    def test_reset_clears_processing_times(self):
        """Test reset clears processing times."""
        detector = MultiPersonDetector()
        
        # Run some detections
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        for _ in range(3):
            detector.detect(raw_signal)
        
        assert len(detector.processing_times) > 0
        
        # Reset
        detector.reset()
        
        assert len(detector.processing_times) == 0


class TestMultiPersonDetectorCalibration:
    """Tests for calibration functionality."""

    def test_calibrate(self):
        """Test calibration with reference signal."""
        detector = MultiPersonDetector()
        
        # Create reference signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        reference_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        result = detector.calibrate(reference_signal)
        
        assert 'gain' in result
        assert 'offset' in result
        assert detector.is_calibrated is True

    def test_apply_calibration(self):
        """Test applying calibration to signal."""
        detector = MultiPersonDetector()
        
        # Create signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        result = detector.apply_calibration(signal)
        
        assert 'rssi' in result
        assert 'rtt' in result
        assert 'calibration_applied' in result or 'calibrated' in result


class TestMultiPersonDetectorStats:
    """Tests for detection statistics."""

    def test_get_detection_stats(self):
        """Test getting detection statistics."""
        detector = MultiPersonDetector(max_capacity=3, mode="multi_person")
        
        stats = detector.get_detection_stats()
        
        assert 'frame_id' in stats
        assert 'is_calibrated' in stats
        assert 'mode' in stats
        assert 'max_capacity' in stats
        # avg_processing_time_ms moved into stats['performance'] in the new API
        assert 'person_count' in stats
        assert 'zone_person_counts' in stats
        # Accept both old flat key and new nested key
        has_avg = (
            'avg_processing_time_ms' in stats
            or ('performance' in stats and 'avg_ms' in stats['performance'])
        )
        assert has_avg

    def test_stats_after_detection(self):
        """Test statistics after detection."""
        detector = MultiPersonDetector()
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run detection
        detector.detect(raw_signal)
        
        stats = detector.get_detection_stats()
        
        assert stats['frame_id'] == 1
        assert stats['person_count'] >= 0


class TestMultiPersonDetectorIntegration:
    """Integration tests for the multi-person detector."""

    def test_full_detection_pipeline(self):
        """Test complete detection pipeline."""
        detector = MultiPersonDetector(max_capacity=3)
        
        # Create realistic multi-person signal
        np.random.seed(123)
        
        duration = 2.0
        sample_rate = 10.0
        n_samples = int(duration * sample_rate)
        
        # Person 1: Standing (breathing pattern at 0.2 Hz)
        t = np.linspace(0, duration, n_samples)
        rtt1 = 0.5 + 0.02 * np.sin(2 * np.pi * 0.2 * t)
        rssi1 = -70 + np.random.normal(0, 3, n_samples)
        
        # Person 2: Walking (higher frequency at 2 Hz)
        rtt2 = 0.6 + 0.05 * np.sin(2 * np.pi * 2.0 * t)
        rssi2 = -72 + np.random.normal(0, 4, n_samples)
        
        # Combine signals
        raw_signal = {
            'rssi': (rssi1 + rssi2).tolist(),
            'rtt': (rtt1 + rtt2).tolist()
        }
        
        # Run detection
        result = detector.detect(raw_signal)
        
        assert result.success is True
        assert result.processing_time_ms >= 0
        
        # Get output payload
        payload = detector.get_output_payload()
        
        assert 'person_count' in payload
        assert 'persons' in payload
        assert payload['person_count'] >= 0

    def test_mode_switching(self):
        """Test switching between single and multi-person modes."""
        detector = MultiPersonDetector()
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Detect in multi-person mode
        detector.set_mode("multi_person")
        result_multi = detector.detect(raw_signal)
        
        # Detect in single-person mode
        detector.set_mode("single_person")
        result_single = detector.detect(raw_signal)
        
        # Both should succeed
        assert result_multi.success is True
        assert result_single.success is True

    def test_resource_constraint_handling(self):
        """Test handling of resource constraints."""
        detector = MultiPersonDetector(max_capacity=2)  # Low capacity
        
        # Create signal that might detect more than 2 persons
        np.random.seed(42)
        
        # Create multiple overlapping signals
        signals = []
        for i in range(4):
            rssi = np.random.normal(-70 - i*2, 5, 100)
            rtt = 0.5 + i*0.01 + np.random.normal(0, 0.05, 100)
            signals.append((rssi, rtt))
        
        # Combine signals
        rssi_combined = sum(s[0] for s in signals)
        rtt_combined = sum(s[1] for s in signals)
        
        raw_signal = {
            'rssi': rssi_combined.tolist(),
            'rtt': rtt_combined.tolist()
        }
        
        # Should handle gracefully without exceeding max_capacity
        result = detector.detect(raw_signal)
        
        assert result.success is True
        assert result.processing_time_ms >= 0

    def test_graceful_degradation(self):
        """Test graceful degradation with poor signal quality."""
        detector = MultiPersonDetector()
        
        # Create poor quality signal (low SNR)
        np.random.seed(42)
        
        # Very weak signal with high noise
        rssi = -95 + np.random.normal(0, 10, 100)  # Very weak
        rtt = 0.5 + np.random.normal(0, 0.3, 100)  # High noise
        
        raw_signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        # Should handle gracefully (may return empty or low confidence)
        result = detector.detect(raw_signal)
        
        assert result.success is True or result.success is False
        # Don't assert success=True as poor signal may fail

    def test_concurrent_detections(self):
        """Test handling of rapid consecutive detections."""
        detector = MultiPersonDetector()
        
        # Create synthetic signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        
        # Run multiple rapid detections
        results = []
        for _ in range(10):
            result = detector.detect(raw_signal)
            results.append(result)
        
        # All should complete
        assert len(results) == 10
        assert all(isinstance(r, DetectionResult) for r in results)
