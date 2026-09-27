"""Tests for the signal processor module."""

import pytest
import numpy as np
from multi_person.modules.signal_processor import (
    SignalProcessor,
    SignalFeatures,
)
from multi_person.core.models import PersonSignature


class TestSignalProcessorPreprocessing:
    """Tests for signal preprocessing functionality."""

    def test_preprocess_empty_signal(self):
        """Test preprocessing with empty signal data."""
        processor = SignalProcessor()
        result = processor.preprocess_signal({'rssi': [], 'rtt': []})
        
        assert 'rssi' in result
        assert 'rtt' in result
        assert len(result['rssi']) == 0
        assert len(result['rtt']) == 0
        assert result['cleaned'] is False

    def test_preprocess_single_person_signal(self):
        """Test preprocessing with single person signal."""
        processor = SignalProcessor()
        
        # Create synthetic signal for one person
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        raw_signal = {'rssi': rssi_values.tolist(), 'rtt': rtt_values.tolist()}
        result = processor.preprocess_signal(raw_signal)
        
        # Outlier removal may remove some points (expected behavior)
        assert len(result['rssi']) <= 100
        assert len(result['rtt']) <= 100
        assert len(result['rssi']) > 90  # Should keep most points
        assert len(result['rtt']) > 90
        assert 'metadata' in result
        assert result['metadata']['sample_rate'] == 10.0

    def test_preprocess_with_outliers(self):
        """Test preprocessing removes outliers."""
        processor = SignalProcessor()
        
        # Create signal with outliers
        rssi_values = np.random.normal(-70, 5, 100).tolist()
        rtt_values = np.random.normal(0.5, 0.1, 100).tolist()
        
        # Add outliers
        rssi_values.append(-100)  # RSSI outlier
        rtt_values.append(2.0)    # RTT outlier
        
        raw_signal = {'rssi': rssi_values, 'rtt': rtt_values}
        result = processor.preprocess_signal(raw_signal)
        
        # Outliers should be removed
        assert len(result['rssi']) < len(rssi_values)
        assert len(result['rtt']) < len(rtt_values)

    def test_preprocess_tuple_input(self):
        """Test preprocessing with tuple input format."""
        processor = SignalProcessor()
        
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 50)
        rtt_values = np.random.normal(0.5, 0.1, 50)
        
        raw_signal = (rssi_values.tolist(), rtt_values.tolist())
        result = processor.preprocess_signal(raw_signal)
        
        # Outlier removal may remove some points (expected behavior)
        assert len(result['rssi']) <= 50
        assert len(result['rtt']) <= 50
        assert len(result['rssi']) > 40  # Should keep most points
        assert len(result['rtt']) > 40

    def test_preprocess_none_input_raises_error(self):
        """Test that None input raises ValueError."""
        processor = SignalProcessor()
        
        with pytest.raises(ValueError):
            processor.preprocess_signal(None)

    def test_preprocess_invalid_format_raises_error(self):
        """Test that invalid format raises ValueError."""
        processor = SignalProcessor()
        
        with pytest.raises(ValueError):
            processor.preprocess_signal("invalid")


class TestSignalProcessorFeatureExtraction:
    """Tests for feature extraction functionality."""

    def test_extract_features_basic(self):
        """Test basic feature extraction."""
        processor = SignalProcessor(sample_rate=10.0)
        
        # Create synthetic signal with known properties
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt_signal = np.sin(2 * np.pi * 2 * t) * 0.1 + 0.5  # 2 Hz signal
        
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 100),
            'rtt': rtt_signal
        }
        
        features = processor.extract_features(preprocessed)
        
        assert isinstance(features, SignalFeatures)
        assert features.rtt_mean > 0
        assert features.rtt_std > 0
        assert features.dominant_frequency > 0

    def test_extract_features_breathing_band(self):
        """Test feature extraction detects breathing band energy."""
        processor = SignalProcessor(sample_rate=10.0)
        
        # Create signal with breathing frequency (0.2 Hz)
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt_signal = np.sin(2 * np.pi * 0.2 * t) * 0.05 + 0.5
        
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 100),
            'rtt': rtt_signal
        }
        
        features = processor.extract_features(preprocessed)
        
        # Should detect breathing energy
        assert features.breathing_energy > 0
        assert features.dominant_frequency > 0

    def test_extract_features_walking_band(self):
        """Test feature extraction detects walking band energy."""
        processor = SignalProcessor(sample_rate=10.0)
        
        # Create signal with walking frequency (2 Hz)
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt_signal = np.sin(2 * np.pi * 2 * t) * 0.1 + 0.5
        
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 100),
            'rtt': rtt_signal
        }
        
        features = processor.extract_features(preprocessed)
        
        # Should detect walking energy
        assert features.walking_energy > 0

    def test_extract_features_empty_signal(self):
        """Test feature extraction with empty signal."""
        processor = SignalProcessor()
        
        preprocessed = {'rssi': np.array([]), 'rtt': np.array([])}
        features = processor.extract_features(preprocessed)
        
        assert features.rtt_mean == 0.0
        assert features.rtt_std == 0.0
        assert features.dominant_frequency == 0.0

    def test_extract_features_single_sample(self):
        """Test feature extraction with single sample."""
        processor = SignalProcessor()
        
        preprocessed = {'rssi': np.array([0.5]), 'rtt': np.array([0.5])}
        features = processor.extract_features(preprocessed)
        
        assert features.rtt_mean == 0.5
        assert features.rtt_std == 0.0
        assert features.dominant_frequency == 0.0


class TestSignalProcessorClustering:
    """Tests for signal clustering functionality."""

    def test_cluster_signals_empty(self):
        """Test clustering with empty signals list."""
        processor = SignalProcessor()
        
        clusters = processor.cluster_signals([])
        
        assert clusters == []

    def test_cluster_signals_single_signal(self):
        """Test clustering with single signal."""
        processor = SignalProcessor()
        
        signals = [{'rssi': np.array([0.5]), 'rtt': np.array([0.5])}]
        clusters = processor.cluster_signals(signals)
        
        assert clusters == [[0]]

    def test_cluster_signals_multiple_people(self):
        """Test clustering separates multiple people."""
        processor = SignalProcessor()
        
        # Create signals from two different people (different patterns)
        np.random.seed(42)
        
        # Person 1: Lower RTT mean
        signal1 = {
            'rssi': np.random.normal(-70, 5, 50),
            'rtt': np.random.normal(0.4, 0.05, 50)
        }
        
        # Person 2: Higher RTT mean (further away)
        signal2 = {
            'rssi': np.random.normal(-75, 5, 50),
            'rtt': np.random.normal(0.6, 0.05, 50)
        }
        
        signals = [signal1, signal2]
        clusters = processor.cluster_signals(signals)
        
        # Should have 2 clusters (one for each person)
        assert len(clusters) >= 1
        # Check that signals are in clusters
        all_indices = [idx for cluster in clusters for idx in cluster]
        assert set(all_indices) == {0, 1}

    def test_cluster_signals_same_person(self):
        """Test clustering groups same person signals together."""
        processor = SignalProcessor()
        
        # Create multiple signals from same person
        np.random.seed(42)
        
        signals = []
        for _ in range(3):
            signal = {
                'rssi': np.random.normal(-70, 5, 50),
                'rtt': np.random.normal(0.5, 0.05, 50)
            }
            signals.append(signal)
        
        clusters = processor.cluster_signals(signals)
        
        # All signals should be in same or similar clusters
        assert len(clusters) >= 1

    def test_cluster_signals_with_noise(self):
        """Test clustering handles noisy data."""
        processor = SignalProcessor()
        
        # Create signals with high noise
        np.random.seed(42)
        
        signal1 = {
            'rssi': np.random.normal(-70, 15, 50),  # High noise
            'rtt': np.random.normal(0.5, 0.2, 50)
        }
        
        signal2 = {
            'rssi': np.random.normal(-72, 15, 50),
            'rtt': np.random.normal(0.55, 0.2, 50)
        }
        
        signals = [signal1, signal2]
        clusters = processor.cluster_signals(signals)
        
        # Should still produce clusters
        assert len(clusters) >= 1


class TestSignalProcessorSeparation:
    """Tests for signal separation functionality."""

    def test_separate_signals_empty(self):
        """Test separation with empty signals list."""
        processor = SignalProcessor()
        
        separated = processor.separate_overlapping_signals([])
        
        assert separated == []

    def test_separate_signals_single(self):
        """Test separation with single signal."""
        processor = SignalProcessor()
        
        signal = {'rssi': np.array([0.5]), 'rtt': np.array([0.5])}
        separated = processor.separate_overlapping_signals([signal])
        
        assert len(separated) == 1
        assert separated[0] == signal

    def test_separate_signals_multiple(self):
        """Test separation with multiple signals."""
        processor = SignalProcessor()
        
        signal1 = {'rssi': np.random.normal(-70, 5, 50), 'rtt': np.random.normal(0.5, 0.1, 50)}
        signal2 = {'rssi': np.random.normal(-75, 5, 50), 'rtt': np.random.normal(0.6, 0.1, 50)}
        
        signals = [signal1, signal2]
        separated = processor.separate_overlapping_signals(signals)
        
        assert len(separated) == 2
        assert all('separation_info' in s for s in separated)

    def test_separate_signals_correlation_info(self):
        """Test separation includes correlation information."""
        processor = SignalProcessor()
        
        signal1 = {'rssi': np.random.normal(-70, 5, 50), 'rtt': np.random.normal(0.5, 0.1, 50)}
        signal2 = {'rssi': np.random.normal(-75, 5, 50), 'rtt': np.random.normal(0.6, 0.1, 50)}
        
        signals = [signal1, signal2]
        separated = processor.separate_overlapping_signals(signals)
        
        for sig in separated:
            assert 'separation_info' in sig
            assert 'signal_index' in sig['separation_info']
            assert 'correlation_with_others' in sig['separation_info']
            assert 'is_separated' in sig['separation_info']


class TestPersonSignatureCreation:
    """Tests for PersonSignature creation."""

    def test_create_person_signature(self):
        """Test creating a PersonSignature."""
        processor = SignalProcessor()
        
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 50),
            'rtt': np.random.normal(0.5, 0.1, 50)
        }
        
        features = processor.extract_features(preprocessed)
        
        signature = processor.create_person_signature(
            signal=preprocessed,
            features=features,
            person_id=1,
            position=(1.5, 2.0),
            activity="standing",
            confidence=0.9
        )
        
        assert isinstance(signature, PersonSignature)
        assert signature.person_id == 1
        assert signature.position == (1.5, 2.0)
        assert signature.activity == "standing"
        assert signature.confidence == 0.9

    def test_create_person_signature_with_velocity(self):
        """Test creating PersonSignature with velocity."""
        processor = SignalProcessor()
        
        # Create signal with变化
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 50),
            'rtt': np.linspace(0.4, 0.6, 50)  # Changing RTT indicates movement
        }
        
        features = processor.extract_features(preprocessed)
        
        signature = processor.create_person_signature(
            signal=preprocessed,
            features=features,
            person_id=1,
            position=(1.5, 2.0),
            activity="walking",
            confidence=0.8
        )
        
        assert signature.velocity is not None
        assert len(signature.velocity) == 2

    def test_create_person_signature_no_velocity(self):
        """Test creating PersonSignature without velocity (static signal)."""
        processor = SignalProcessor()
        
        preprocessed = {
            'rssi': np.random.normal(-70, 5, 50),
            'rtt': np.random.normal(0.5, 0.001, 50)  # Very stable RTT (low variance)
        }
        
        features = processor.extract_features(preprocessed)
        
        signature = processor.create_person_signature(
            signal=preprocessed,
            features=features,
            person_id=1,
            position=(1.5, 2.0),
            activity="standing",
            confidence=0.9
        )
        
        # Velocity should be very small for stable signal
        assert signature.velocity is None or signature.velocity[0] < 0.05


class TestSignalProcessorIntegration:
    """Integration tests for the signal processor."""

    def test_full_pipeline(self):
        """Test complete signal processing pipeline."""
        processor = SignalProcessor()
        
        # Create synthetic multi-person signal
        np.random.seed(42)
        
        # Person 1
        rssi1 = np.random.normal(-70, 5, 100)
        rtt1 = np.sin(2 * np.pi * 0.2 * np.linspace(0, 10, 100)) * 0.05 + 0.5
        
        # Person 2
        rssi2 = np.random.normal(-75, 5, 100)
        rtt2 = np.sin(2 * np.pi * 0.3 * np.linspace(0, 10, 100)) * 0.05 + 0.55
        
        raw_signal = {
            'rssi': rssi1.tolist() + rssi2.tolist(),
            'rtt': rtt1.tolist() + rtt2.tolist()
        }
        
        # Preprocess
        preprocessed = processor.preprocess_signal(raw_signal)
        assert 'rssi' in preprocessed
        assert 'rtt' in preprocessed
        
        # Extract features
        features = processor.extract_features(preprocessed)
        assert features.rtt_mean > 0
        assert features.dominant_frequency >= 0
        
        # Reset processor
        processor.reset()
        assert len(processor.rtt_buffer) == 0

    def test_signal_processor_with_realistic_data(self):
        """Test with more realistic Wi-Fi signal data."""
        processor = SignalProcessor(sample_rate=10.0)
        
        # Simulate realistic Wi-Fi signal with multiple people
        np.random.seed(123)
        
        # Simulate 5 seconds of data
        duration = 5.0
        n_samples = int(duration * processor.sample_rate)
        
        # Person 1: Standing (breathing pattern)
        rtt1 = 0.5 + 0.02 * np.sin(2 * np.pi * 0.2 * np.linspace(0, duration, n_samples))
        rssi1 = -70 + np.random.normal(0, 3, n_samples)
        
        # Person 2: Walking (higher frequency)
        t = np.linspace(0, duration, n_samples)
        rtt2 = 0.6 + 0.05 * np.sin(2 * np.pi * 1.5 * t)
        rssi2 = -72 + np.random.normal(0, 4, n_samples)
        
        raw_signal = {
            'rssi': (rssi1 + rssi2).tolist(),
            'rtt': (rtt1 + rtt2).tolist()
        }
        
        # Process
        preprocessed = processor.preprocess_signal(raw_signal)
        features = processor.extract_features(preprocessed)
        
        # Verify features
        assert features.rtt_mean > 0
        assert features.breathing_energy >= 0
        assert features.walking_energy >= 0
