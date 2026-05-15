"""Tests for the calibration module."""

import pytest
import numpy as np
from multi_person.modules.calibration_module import (
    CalibrationModule,
    CalibrationParams,
)
from multi_person.modules.signal_processor import SignalProcessor


class TestCalibrationModuleBasic:
    """Tests for basic calibration module functionality."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        module = CalibrationModule()
        
        assert module.signal_processor is not None
        assert module.ema_decay == 0.1
        assert module.recalibration_threshold == 0.3
        assert module.baseline_rssi_mean == -70.0
        assert module.baseline_rtt_mean == 0.5
        assert len(module.calibration_history) == 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        processor = SignalProcessor()
        module = CalibrationModule(
            signal_processor=processor,
            ema_decay=0.2,
            recalibration_threshold=0.5,
        )
        
        assert module.signal_processor == processor
        assert module.ema_decay == 0.2
        assert module.recalibration_threshold == 0.5

    def test_calibrate_with_reference_signal(self):
        """Test calibration with reference signal."""
        module = CalibrationModule()
        
        # Create synthetic reference signal
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        reference_signal = {
            'rssi': rssi_values.tolist(),
            'rtt': rtt_values.tolist()
        }
        
        params = module.calibrate(reference_signal)
        
        assert 'gain' in params
        assert 'offset' in params
        assert 'baseline_rssi_mean' in params
        assert 'baseline_rtt_mean' in params
        assert params['gain'] > 0
        assert isinstance(params['offset'], float)

    def test_calibrate_none_raises_error(self):
        """Test that None reference signal raises ValueError."""
        module = CalibrationModule()
        
        with pytest.raises(ValueError):
            module.calibrate(None)

    def test_calibrate_empty_signal(self):
        """Test calibration with empty signal."""
        module = CalibrationModule()
        
        reference_signal = {'rssi': [], 'rtt': []}
        params = module.calibrate(reference_signal)
        
        assert 'gain' in params
        assert 'offset' in params


class TestApplyCalibration:
    """Tests for calibration application functionality."""

    def test_apply_calibration_basic(self):
        """Test applying calibration to signal."""
        module = CalibrationModule()
        
        # First calibrate
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        reference_signal = {
            'rssi': rssi_values.tolist(),
            'rtt': rtt_values.tolist()
        }
        module.calibrate(reference_signal)
        
        # Apply calibration to new signal
        test_signal = {
            'rssi': np.random.normal(-72, 4, 50).tolist(),
            'rtt': np.random.normal(0.55, 0.08, 50).tolist()
        }
        
        calibrated = module.apply_calibration(test_signal)
        
        assert 'rssi' in calibrated
        assert 'rtt' in calibrated
        assert 'calibration_applied' in calibrated
        assert calibrated['calibration_applied'] is True
        assert len(calibrated['rssi']) == 50
        assert len(calibrated['rtt']) == 50

    def test_apply_calibration_with_params(self):
        """Test applying calibration with custom parameters."""
        module = CalibrationModule()
        
        test_signal = {
            'rssi': np.random.normal(-70, 5, 50).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 50).tolist()
        }
        
        custom_params = {
            'gain': 1.2,
            'offset': 0.1
        }
        
        calibrated = module.apply_calibration(test_signal, custom_params)
        
        assert 'rssi' in calibrated
        assert 'rtt' in calibrated
        assert calibrated['calibration_applied'] is True

    def test_apply_calibration_none_raises_error(self):
        """Test that None signal raises ValueError."""
        module = CalibrationModule()
        
        with pytest.raises(ValueError):
            module.apply_calibration(None)

    def test_apply_calibration_clamps_values(self):
        """Test that calibration clamps values to [0, 1]."""
        module = CalibrationModule()
        
        # Create signal that would produce values outside [0, 1]
        test_signal = {
            'rssi': np.array([100, 200, 300]).tolist(),  # Very high values
            'rtt': np.array([10, 20, 30]).tolist()       # Very high values
        }
        
        # Use extreme params to force values outside range
        custom_params = {
            'gain': 1000,
            'offset': 1000
        }
        
        calibrated = module.apply_calibration(test_signal, custom_params)
        
        # Values should be clamped
        assert np.all(calibrated['rssi'] >= 0)
        assert np.all(calibrated['rssi'] <= 1)
        assert np.all(calibrated['rtt'] >= 0)
        assert np.all(calibrated['rtt'] <= 1)

    def test_apply_calibration_tuple_input(self):
        """Test applying calibration with tuple input."""
        module = CalibrationModule()
        
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 50)
        rtt_values = np.random.normal(0.5, 0.1, 50)
        
        test_signal = (rssi_values.tolist(), rtt_values.tolist())
        
        calibrated = module.apply_calibration(test_signal)
        
        assert 'rssi' in calibrated
        assert 'rtt' in calibrated


class TestBaselineLearning:
    """Tests for baseline learning functionality."""

    def test_learn_baseline_initializes_ema(self):
        """Test that learn_baseline initializes EMA values."""
        module = CalibrationModule()
        
        # Calibrate first to set baseline
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Learn baseline
        result = module.learn_baseline()
        
        assert 'baseline_rssi_mean' in result
        assert 'baseline_rtt_mean' in result
        assert 'baseline_rssi_std' in result
        assert 'baseline_rtt_std' in result
        assert 'person_signatures_count' in result
        assert result['person_signatures_count'] == 0

    def test_learn_baseline_updates_ema(self):
        """Test that learn_baseline updates EMA values."""
        module = CalibrationModule()
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Learn baseline
        module.learn_baseline()
        
        # EMA values should be initialized
        assert module.ema_rssi_mean is not None
        assert module.ema_rtt_mean is not None

    def test_learn_baseline_with_existing_baseline(self):
        """Test learn_baseline with existing baseline."""
        module = CalibrationModule()
        
        # Set initial baseline
        module.baseline_rssi_mean = -72.0
        module.baseline_rtt_mean = 0.55
        
        # Learn baseline again
        result = module.learn_baseline()
        
        # Should use existing baseline
        assert result['baseline_rssi_mean'] == -72.0
        assert result['baseline_rtt_mean'] == 0.55


class TestEMAAdaptation:
    """Tests for EMA-based environmental adaptation."""

    def test_adapt_to_environment_basic(self):
        """Test basic EMA adaptation."""
        module = CalibrationModule(ema_decay=0.2)
        
        # Initial EMA should be None
        assert module.ema_rssi_mean is None
        assert module.ema_rtt_mean is None
        
        # Adapt to environment
        features = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5
        }
        
        result = module.adapt_to_environment(features)
        
        assert 'ema_rssi_mean' in result
        assert 'ema_rtt_mean' in result
        assert result['adaptation_applied'] is True
        assert module.ema_rssi_mean is not None
        assert module.ema_rtt_mean is not None

    def test_adapt_to_environment_updates_ema(self):
        """Test that EMA is updated correctly."""
        module = CalibrationModule(ema_decay=0.5)
        
        # First adaptation
        features1 = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5
        }
        module.adapt_to_environment(features1)
        
        ema_rssi_1 = module.ema_rssi_mean
        
        # Second adaptation with different value
        features2 = {
            'rssi_mean': -68.0,  # Changed by 2 dB
            'rtt_mean': 0.5
        }
        module.adapt_to_environment(features2)
        
        ema_rssi_2 = module.ema_rssi_mean
        
        # EMA should have moved towards new value
        assert ema_rssi_2 > ema_rssi_1  # Moving towards -68

    def test_adapt_to_environment_with_person_signatures(self):
        """Test EMA adaptation with person signatures."""
        module = CalibrationModule(ema_decay=0.2)
        
        features = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5,
            'person_signatures': [
                {
                    'person_id': 1,
                    'position': (1.0, 2.0),
                    'activity': 'standing',
                    'signal_strength': -70.0,
                    'confidence': 0.9,
                }
            ]
        }
        
        result = module.adapt_to_environment(features)
        
        assert result['adaptation_applied'] is True
        assert 1 in module.person_signatures
        assert module.person_signatures[1]['ema_signal_strength'] == -70.0

    def test_adapt_to_environment_partial_features(self):
        """Test EMA adaptation with partial features."""
        module = CalibrationModule(ema_decay=0.2)
        
        # First adapt to set EMA
        features1 = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5
        }
        module.adapt_to_environment(features1)
        
        ema_rssi_1 = module.ema_rssi_mean
        
        # Second adapt with only RSSI
        features2 = {
            'rssi_mean': -68.0
            # rtt_mean not provided, should use EMA value
        }
        module.adapt_to_environment(features2)
        
        # EMA should still update
        assert module.ema_rssi_mean != ema_rssi_1

    def test_adapt_to_environment_empty_signatures(self):
        """Test EMA adaptation with empty person signatures."""
        module = CalibrationModule()
        
        features = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5,
            'person_signatures': []
        }
        
        result = module.adapt_to_environment(features)
        
        assert result['adaptation_applied'] is True
        assert len(module.person_signatures) == 0


class TestRecalibrationTrigger:
    """Tests for recalibration trigger functionality."""

    def test_trigger_recalibration_no_change(self):
        """Test trigger_recalibration with no environmental change."""
        module = CalibrationModule(recalibration_threshold=0.3)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # No change in environment
        features = {
            'rssi_mean': module.baseline_rssi_mean,
            'rtt_mean': module.baseline_rtt_mean,
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        assert should_recalibrate is False
        assert metadata['total_change'] < module.recalibration_threshold

    def test_trigger_recalibration_with_change(self):
        """Test trigger_recalibration with environmental change."""
        module = CalibrationModule(recalibration_threshold=0.3)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Large environmental change
        features = {
            'rssi_mean': module.baseline_rssi_mean + 20,  # 20 dB change
            'rtt_mean': module.baseline_rtt_mean,
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        assert should_recalibrate is True
        assert metadata['total_change'] > module.recalibration_threshold
        assert metadata['rssi_change'] > 0

    def test_trigger_recalibration_rssi_only_change(self):
        """Test trigger_recalibration with only RSSI change."""
        module = CalibrationModule(recalibration_threshold=0.3)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Only RSSI changes
        features = {
            'rssi_mean': module.baseline_rssi_mean + 15,
            'rtt_mean': module.baseline_rtt_mean,
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        assert should_recalibrate is True
        assert metadata['rssi_change'] > 0
        assert metadata['rtt_change'] == 0.0

    def test_trigger_recalibration_rtt_only_change(self):
        """Test trigger_recalibration with only RTT change."""
        module = CalibrationModule(recalibration_threshold=0.3)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Only RTT changes
        features = {
            'rssi_mean': module.baseline_rssi_mean,
            'rtt_mean': module.baseline_rtt_mean + 0.3,  # 0.3 second change
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        assert should_recalibrate is True
        assert metadata['rtt_change'] > 0
        assert metadata['rssi_change'] == 0.0

    def test_trigger_recalibration_threshold_boundary(self):
        """Test trigger_recalibration at threshold boundary."""
        module = CalibrationModule(recalibration_threshold=0.5)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        # Very small change in normalized space (should not trigger with threshold 0.5)
        # Use a tiny change in normalized values
        features = {
            'rssi_mean': module.baseline_rssi_mean + 0.05,  # Very small normalized change
            'rtt_mean': module.baseline_rtt_mean,
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        # Should not trigger with very small change
        assert should_recalibrate is False

    def test_trigger_recalibration_metadata(self):
        """Test trigger_recalibration returns correct metadata."""
        module = CalibrationModule(recalibration_threshold=0.3)
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        features = {
            'rssi_mean': module.baseline_rssi_mean + 10,
            'rtt_mean': module.baseline_rtt_mean,
            'rssi_std': module.baseline_rssi_std,
            'rtt_std': module.baseline_rtt_std,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        assert 'rssi_change' in metadata
        assert 'rtt_change' in metadata
        assert 'total_change' in metadata
        assert 'threshold' in metadata
        assert 'should_recalibrate' in metadata

    def test_trigger_recalibration_no_baseline(self):
        """Test trigger_recalibration without baseline."""
        module = CalibrationModule()
        
        # Don't calibrate, use defaults
        features = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5,
            'rssi_std': 5.0,
            'rtt_std': 0.1,
        }
        
        should_recalibrate, metadata = module.trigger_recalibration(features)
        
        # Should not trigger (same as default baseline)
        assert should_recalibrate is False


class TestPersonSignatureAdaptation:
    """Tests for person signature profile adaptation."""

    def test_update_person_signatures_new_person(self):
        """Test updating person signatures for new person."""
        module = CalibrationModule()
        
        signatures = [
            {
                'person_id': 1,
                'position': (1.0, 2.0),
                'activity': 'standing',
                'signal_strength': -70.0,
                'confidence': 0.9,
            }
        ]
        
        module._update_person_signatures(signatures)
        
        assert 1 in module.person_signatures
        assert module.person_signatures[1]['position'] == (1.0, 2.0)
        assert module.person_signatures[1]['activity'] == 'standing'
        assert module.person_signatures[1]['signal_strength'] == -70.0
        assert module.person_signatures[1]['confidence'] == 0.9
        assert module.person_signatures[1]['ema_signal_strength'] == -70.0

    def test_update_person_signatures_update_existing(self):
        """Test updating existing person signature."""
        module = CalibrationModule(ema_decay=0.5)
        
        # Add person first
        signatures1 = [
            {
                'person_id': 1,
                'position': (1.0, 2.0),
                'activity': 'standing',
                'signal_strength': -70.0,
                'confidence': 0.9,
            }
        ]
        module._update_person_signatures(signatures1)
        
        # Update with new signal strength
        signatures2 = [
            {
                'person_id': 1,
                'position': (1.1, 2.1),  # Slightly moved
                'activity': 'standing',
                'signal_strength': -68.0,  # Stronger signal
                'confidence': 0.95,
            }
        ]
        module._update_person_signatures(signatures2)
        
        # Check EMA updated
        assert module.person_signatures[1]['ema_signal_strength'] == -69.0  # EMA of -70 and -68

    def test_update_person_signatures_multiple_people(self):
        """Test updating signatures for multiple people."""
        module = CalibrationModule()
        
        signatures = [
            {
                'person_id': 1,
                'position': (1.0, 2.0),
                'activity': 'standing',
                'signal_strength': -70.0,
                'confidence': 0.9,
            },
            {
                'person_id': 2,
                'position': (3.0, 4.0),
                'activity': 'walking',
                'signal_strength': -75.0,
                'confidence': 0.8,
            }
        ]
        
        module._update_person_signatures(signatures)
        
        assert len(module.person_signatures) == 2
        assert 1 in module.person_signatures
        assert 2 in module.person_signatures

    def test_update_person_signatures_empty(self):
        """Test updating with empty signatures list."""
        module = CalibrationModule()
        
        module._update_person_signatures([])
        
        assert len(module.person_signatures) == 0


class TestGetCalibrationParams:
    """Tests for getting calibration parameters."""

    def test_get_calibration_params(self):
        """Test getting current calibration parameters."""
        module = CalibrationModule()
        
        # Calibrate first
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        params = module.get_calibration_params()
        
        assert 'gain' in params
        assert 'offset' in params
        assert 'ema_decay' in params
        assert 'recalibration_threshold' in params
        assert 'baseline_rssi_mean' in params
        assert 'baseline_rtt_mean' in params
        assert 'ema_rssi_mean' in params
        assert 'ema_rtt_mean' in params

    def test_get_calibration_params_before_calibration(self):
        """Test getting params before calibration."""
        module = CalibrationModule()
        
        params = module.get_calibration_params()
        
        assert params['gain'] == 1.0  # Default
        assert params['offset'] == 0.0  # Default
        assert params['ema_rssi_mean'] is None
        assert params['ema_rtt_mean'] is None


class TestReset:
    """Tests for reset functionality."""

    def test_reset_module(self):
        """Test resetting the calibration module."""
        module = CalibrationModule()
        
        # Calibrate and adapt
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        features = {
            'rssi_mean': -68.0,
            'rtt_mean': 0.52
        }
        module.adapt_to_environment(features)
        
        # Add person signatures
        module._update_person_signatures([
            {'person_id': 1, 'position': (1.0, 2.0), 'activity': 'standing',
             'signal_strength': -70.0, 'confidence': 0.9}
        ])
        
        # Reset
        module.reset()
        
        # Check reset state
        assert module.baseline_rssi_mean == -70.0
        assert module.baseline_rtt_mean == 0.5
        assert module.ema_rssi_mean is None
        assert module.ema_rtt_mean is None
        assert len(module.calibration_history) == 0
        assert len(module.person_signatures) == 0

    def test_reset_after_multiple_calibrations(self):
        """Test reset after multiple calibration events."""
        module = CalibrationModule()
        
        # Multiple calibrations
        for i in range(3):
            np.random.seed(42 + i)
            reference_signal = {
                'rssi': np.random.normal(-70 + i, 5, 100).tolist(),
                'rtt': np.random.normal(0.5, 0.1, 100).tolist()
            }
            module.calibrate(reference_signal)
        
        # Reset
        module.reset()
        
        assert len(module.calibration_history) == 0
        assert module.last_recalibration_frame == 0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_sample_signal(self):
        """Test with single sample signal."""
        module = CalibrationModule()
        
        reference_signal = {
            'rssi': [-70.0],
            'rtt': [0.5]
        }
        
        params = module.calibrate(reference_signal)
        
        assert 'gain' in params
        assert 'offset' in params

    def test_very_short_signal(self):
        """Test with very short signal."""
        module = CalibrationModule()
        
        # Very short signal
        reference_signal = {
            'rssi': [-70.0, -71.0, -72.0],
            'rtt': [0.5, 0.51, 0.52]
        }
        
        params = module.calibrate(reference_signal)
        
        assert 'gain' in params
        assert 'offset' in params

    def test_empty_signal_in_apply_calibration(self):
        """Test applying calibration to empty signal."""
        module = CalibrationModule()
        
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        module.calibrate(reference_signal)
        
        empty_signal = {'rssi': [], 'rtt': []}
        calibrated = module.apply_calibration(empty_signal)
        
        assert len(calibrated['rssi']) == 0
        assert len(calibrated['rtt']) == 0

    def test_invalid_signal_format(self):
        """Test with invalid signal format."""
        module = CalibrationModule()
        
        with pytest.raises(ValueError):
            module.apply_calibration("invalid")

    def test_calibrate_with_tuple_input(self):
        """Test calibration with tuple input."""
        module = CalibrationModule()
        
        np.random.seed(42)
        rssi_values = np.random.normal(-70, 5, 100)
        rtt_values = np.random.normal(0.5, 0.1, 100)
        
        reference_signal = (rssi_values.tolist(), rtt_values.tolist())
        
        params = module.calibrate(reference_signal)
        
        assert 'gain' in params
        assert 'offset' in params

    def test_adapt_to_environment_with_only_rssi(self):
        """Test adaptation with only RSSI feature."""
        module = CalibrationModule(ema_decay=0.5)
        
        # First adapt with both features
        features1 = {
            'rssi_mean': -70.0,
            'rtt_mean': 0.5
        }
        module.adapt_to_environment(features1)
        
        ema_rssi_1 = module.ema_rssi_mean
        ema_rtt_1 = module.ema_rtt_mean
        
        # Second adapt with only RSSI
        features2 = {
            'rssi_mean': -68.0
        }
        module.adapt_to_environment(features2)
        
        # RSSI should update, RTT should keep previous EMA
        assert module.ema_rssi_mean != ema_rssi_1
        assert module.ema_rtt_mean == ema_rtt_1


class TestCalibrationModuleIntegration:
    """Integration tests for calibration module."""

    def test_full_calibration_pipeline(self):
        """Test complete calibration pipeline."""
        module = CalibrationModule()
        
        # Step 1: Calibrate with reference signal
        np.random.seed(42)
        reference_signal = {
            'rssi': np.random.normal(-70, 5, 100).tolist(),
            'rtt': np.random.normal(0.5, 0.1, 100).tolist()
        }
        
        params = module.calibrate(reference_signal)
        assert params['gain'] > 0
        
        # Step 2: Apply calibration to test signal
        test_signal = {
            'rssi': np.random.normal(-72, 4, 50).tolist(),
            'rtt': np.random.normal(0.55, 0.08, 50).tolist()
        }
        
        calibrated = module.apply_calibration(test_signal)
        assert calibrated['calibration_applied'] is True
        
        # Step 3: Learn baseline
        baseline = module.learn_baseline()
        assert 'baseline_rssi_mean' in baseline
        
        # Step 4: Adapt to environment
        features = {
            'rssi_mean': -68.0,
            'rtt_mean': 0.52
        }
        adaptation = module.adapt_to_environment(features)
        assert adaptation['adaptation_applied'] is True
        
        # Step 5: Check if recalibration needed
        should_recalibrate, metadata = module.trigger_recalibration(features)
        assert isinstance(should_recalibrate, bool)
        assert 'total_change' in metadata

    def test_calibration_with_realistic_data(self):
        """Test with more realistic Wi-Fi signal data."""
        module = CalibrationModule()
        
        # Simulate realistic Wi-Fi signal
        np.random.seed(123)
        
        # Person 1: Standing (breathing pattern)
        rtt1 = 0.5 + 0.02 * np.sin(2 * np.pi * 0.2 * np.linspace(0, 10, 100))
        rssi1 = -70 + np.random.normal(0, 3, 100)
        
        # Person 2: Walking (higher frequency)
        t = np.linspace(0, 10, 100)
        rtt2 = 0.6 + 0.05 * np.sin(2 * np.pi * 1.5 * t)
        rssi2 = -72 + np.random.normal(0, 4, 100)
        
        mixed_signal = {
            'rssi': (rssi1 + rssi2).tolist(),
            'rtt': (rtt1 + rtt2).tolist()
        }
        
        # Calibrate
        params = module.calibrate(mixed_signal)
        assert params['gain'] > 0
        
        # Apply calibration
        calibrated = module.apply_calibration(mixed_signal)
        assert len(calibrated['rssi']) == 100
        
        # Adapt
        features = {
            'rssi_mean': float(np.mean(calibrated['rssi'])),
            'rtt_mean': float(np.mean(calibrated['rtt']))
        }
        adaptation = module.adapt_to_environment(features)
        assert adaptation['adaptation_applied'] is True
