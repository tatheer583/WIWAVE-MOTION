"""Calibration module for multi-person detection.

This module provides calibration capabilities for Wi-Fi signal processing,
including baseline learning, EMA-based environmental adaptation, and
threshold-based recalibration triggers.
"""

import numpy as np
from dataclasses import dataclass
from typing import Any, Optional
from multi_person.core.interfaces import CalibrationModuleInterface
from multi_person.modules.signal_processor import SignalProcessor


@dataclass
class CalibrationParams:
    """Calibration parameters for signal normalization."""
    gain: float = 1.0
    offset: float = 0.0
    ema_decay: float = 0.1
    recalibration_threshold: float = 0.3
    baseline_rssi_mean: float = -70.0
    baseline_rtt_mean: float = 0.5
    baseline_rssi_std: float = 5.0
    baseline_rtt_std: float = 0.1


class CalibrationModule(CalibrationModuleInterface):
    """Calibration module for multi-person detection.
    
    This class implements calibration algorithms for:
    - Baseline learning on system startup
    - EMA-based environmental adaptation
    - Threshold-based recalibration triggers
    - Signal signature profile refinement
    """

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        ema_decay: float = 0.1,
        recalibration_threshold: float = 0.3,
    ):
        """Initialize the calibration module.
        
        Args:
            signal_processor: Signal processor instance for signal operations
            ema_decay: Decay factor for EMA (0-1, higher = faster adaptation)
            recalibration_threshold: Threshold for triggering recalibration
        """
        self.signal_processor = signal_processor or SignalProcessor()
        self.ema_decay = ema_decay
        self.recalibration_threshold = recalibration_threshold
        
        # Calibration parameters
        self.calibration_params: CalibrationParams = CalibrationParams()
        
        # Baseline statistics
        self.baseline_rssi_mean: float = -70.0
        self.baseline_rtt_mean: float = 0.5
        self.baseline_rssi_std: float = 5.0
        self.baseline_rtt_std: float = 0.1
        
        # EMA state
        self.ema_rssi_mean: Optional[float] = None
        self.ema_rtt_mean: Optional[float] = None
        
        # Calibration history
        self.calibration_history: list[dict[str, Any]] = []
        self.last_recalibration_frame: int = 0
        
        # Person signature profiles (for adaptation)
        self.person_signatures: dict[int, dict[str, Any]] = {}

    def calibrate(self, reference_signal: Any) -> dict[str, Any]:
        """Perform calibration with reference signal.
        
        Analyzes the reference signal to determine optimal gain and offset
        values for signal normalization.
        
        Args:
            reference_signal: Calibration reference signal (RSSI and RTT data)
            
        Returns:
            Dictionary containing calibration parameters:
            - 'gain': Signal gain factor
            - 'offset': Signal offset factor
            - 'baseline_rssi_mean': Baseline RSSI mean
            - 'baseline_rtt_mean': Baseline RTT mean
        """
        if reference_signal is None:
            raise ValueError("Reference signal cannot be None")
        
        # Preprocess the reference signal
        preprocessed = self.signal_processor.preprocess_signal(reference_signal)
        
        rssi = preprocessed.get('rssi', np.array([]))
        rtt = preprocessed.get('rtt', np.array([]))
        
        # Calculate statistics
        rssi_mean = float(np.mean(rssi)) if len(rssi) > 0 else 0.0
        rtt_mean = float(np.mean(rtt)) if len(rtt) > 0 else 0.0
        rssi_std = float(np.std(rssi)) if len(rssi) > 0 else 1.0
        rtt_std = float(np.std(rtt)) if len(rtt) > 0 else 0.1
        
        # Calculate gain and offset for normalization
        # Target: RSSI mean around 0.5, RTT mean around 0.5
        target_rssi = 0.5
        target_rtt = 0.5
        
        # Avoid division by zero
        if rssi_mean > 1e-6:
            gain_rssi = target_rssi / rssi_mean
        else:
            gain_rssi = 1.0
            
        if rtt_mean > 1e-6:
            gain_rtt = target_rtt / rtt_mean
        else:
            gain_rtt = 1.0
        
        # Use average gain
        gain = (gain_rssi + gain_rtt) / 2.0
        offset = target_rssi - (rssi_mean * gain)
        
        # Update calibration parameters
        self.calibration_params = CalibrationParams(
            gain=gain,
            offset=offset,
            ema_decay=self.ema_decay,
            recalibration_threshold=self.recalibration_threshold,
            baseline_rssi_mean=rssi_mean,
            baseline_rtt_mean=rtt_mean,
        )
        
        # Update baseline statistics
        self.baseline_rssi_mean = rssi_mean
        self.baseline_rtt_mean = rtt_mean
        self.baseline_rssi_std = rssi_std
        self.baseline_rtt_std = rtt_std
        
        # Initialize EMA with current values
        self.ema_rssi_mean = rssi_mean
        self.ema_rtt_mean = rtt_mean
        
        # Record calibration event
        calibration_record = {
            'gain': gain,
            'offset': offset,
            'baseline_rssi_mean': rssi_mean,
            'baseline_rtt_mean': rtt_mean,
            'baseline_rssi_std': rssi_std,
            'baseline_rtt_std': rtt_std,
            'timestamp': len(self.calibration_history),
        }
        self.calibration_history.append(calibration_record)
        
        return {
            'gain': gain,
            'offset': offset,
            'baseline_rssi_mean': rssi_mean,
            'baseline_rtt_mean': rtt_mean,
            'baseline_rssi_std': rssi_std,
            'baseline_rtt_std': rtt_std,
        }

    def apply_calibration(self, signal: Any, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Apply calibration parameters to signal.
        
        Normalizes the signal using the current or provided calibration parameters.
        
        Args:
            signal: Signal to calibrate (RSSI and RTT data)
            params: Optional calibration parameters. If None, uses current params.
            
        Returns:
            Dictionary containing calibrated signal data:
            - 'rssi': Calibrated RSSI values
            - 'rtt': Calibrated RTT values
            - 'calibration_applied': Boolean indicating if calibration was applied
        """
        if signal is None:
            raise ValueError("Signal cannot be None")
        
        # Use provided params or current calibration params
        if params is None:
            params = {
                'gain': self.calibration_params.gain,
                'offset': self.calibration_params.offset,
            }
        
        gain = params.get('gain', self.calibration_params.gain)
        offset = params.get('offset', self.calibration_params.offset)
        
        # Parse input signal
        if isinstance(signal, dict):
            rssi_values = signal.get('rssi', [])
            rtt_values = signal.get('rtt', [])
        elif isinstance(signal, (tuple, list)):
            if len(signal) >= 2:
                rssi_values = signal[0]
                rtt_values = signal[1]
            else:
                rssi_values = []
                rtt_values = signal[0] if len(signal) > 0 else []
        else:
            raise ValueError(f"Invalid signal format: {type(signal)}")
        
        # Convert to numpy arrays
        rssi_values = np.array(rssi_values) if not isinstance(rssi_values, np.ndarray) else rssi_values
        rtt_values = np.array(rtt_values) if not isinstance(rtt_values, np.ndarray) else rtt_values
        
        # Apply calibration
        calibrated_rssi = rssi_values * gain + offset if len(rssi_values) > 0 else np.array([])
        calibrated_rtt = rtt_values * gain + offset if len(rtt_values) > 0 else np.array([])
        
        # Clamp values to [0, 1] range
        calibrated_rssi = np.clip(calibrated_rssi, 0, 1)
        calibrated_rtt = np.clip(calibrated_rtt, 0, 1)
        
        return {
            'rssi': calibrated_rssi,
            'rtt': calibrated_rtt,
            'calibration_applied': True,
        }

    def learn_baseline(self) -> dict[str, Any]:
        """Learn multi-person signal characteristics on startup.
        
        Analyzes initial signals to establish baseline statistics for
        environmental conditions and person signature profiles.
        
        Returns:
            Dictionary containing baseline statistics:
            - 'baseline_rssi_mean': Mean RSSI for baseline
            - 'baseline_rtt_mean': Mean RTT for baseline
            - 'baseline_rssi_std': RSSI standard deviation
            - 'baseline_rtt_std': RTT standard deviation
            - 'person_signatures_count': Number of person signatures learned
        """
        # Use existing baseline values if set, otherwise use calibration params
        if self.baseline_rssi_mean == -70.0 and self.calibration_params.baseline_rssi_mean != -70.0:
            # Use calibration params if they were set
            self.baseline_rssi_mean = self.calibration_params.baseline_rssi_mean
            self.baseline_rtt_mean = self.calibration_params.baseline_rtt_mean
            self.baseline_rssi_std = self.calibration_params.baseline_rssi_std
            self.baseline_rtt_std = self.calibration_params.baseline_rtt_std
        
        # Initialize EMA with baseline values
        self.ema_rssi_mean = self.baseline_rssi_mean
        self.ema_rtt_mean = self.baseline_rtt_mean
        
        return {
            'baseline_rssi_mean': self.baseline_rssi_mean,
            'baseline_rtt_mean': self.baseline_rtt_mean,
            'baseline_rssi_std': self.baseline_rssi_std,
            'baseline_rtt_std': self.baseline_rtt_std,
            'person_signatures_count': len(self.person_signatures),
        }

    def adapt_to_environment(self, features: dict[str, Any]) -> dict[str, Any]:
        """Use EMA for environmental adaptation.
        
        Continuously adapts calibration parameters using Exponential Moving
        Average to account for slow environmental changes.
        
        Args:
            features: Dictionary containing signal features:
                - 'rssi_mean': Current RSSI mean
                - 'rtt_mean': Current RTT mean
                - 'person_signatures': Optional list of person signatures
                
        Returns:
            Dictionary containing adaptation results:
            - 'ema_rssi_mean': Updated EMA RSSI mean
            - 'ema_rtt_mean': Updated EMA RTT mean
            - 'adaptation_applied': Boolean indicating adaptation was applied
        """
        rssi_mean = features.get('rssi_mean', self.ema_rssi_mean)
        rtt_mean = features.get('rtt_mean', self.ema_rtt_mean)
        
        # Initialize EMA if not set
        if self.ema_rssi_mean is None:
            self.ema_rssi_mean = rssi_mean
        if self.ema_rtt_mean is None:
            self.ema_rtt_mean = rtt_mean
        
        # Apply EMA update
        # EMA_new = alpha * EMA_old + (1 - alpha) * EMA_new
        # Using decay factor: EMA_new = (1 - decay) * EMA_old + decay * new_value
        self.ema_rssi_mean = (1 - self.ema_decay) * self.ema_rssi_mean + self.ema_decay * rssi_mean
        self.ema_rtt_mean = (1 - self.ema_decay) * self.ema_rtt_mean + self.ema_decay * rtt_mean
        
        # Update person signatures if provided
        person_signatures = features.get('person_signatures', [])
        if person_signatures:
            self._update_person_signatures(person_signatures)
        
        return {
            'ema_rssi_mean': self.ema_rssi_mean,
            'ema_rtt_mean': self.ema_rtt_mean,
            'adaptation_applied': True,
        }

    def trigger_recalibration(self, current_features: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Trigger recalibration when threshold exceeded.
        
        Compares current signal characteristics to baseline to detect
        significant environmental changes that require recalibration.
        
        Args:
            current_features: Dictionary containing current signal features:
                - 'rssi_mean': Current RSSI mean
                - 'rtt_mean': Current RTT mean
                - 'rssi_std': Current RSSI standard deviation
                - 'rtt_std': Current RTT standard deviation
                
        Returns:
            Tuple of (should_recalibrate, metadata):
            - 'should_recalibrate': Boolean indicating if recalibration is needed
            - 'metadata': Dictionary with change metrics:
                - 'rssi_change': RSSI change magnitude
                - 'rtt_change': RTT change magnitude
                - 'total_change': Total change magnitude
        """
        rssi_mean = current_features.get('rssi_mean', self.ema_rssi_mean)
        rtt_mean = current_features.get('rtt_mean', self.ema_rtt_mean)
        rssi_std = current_features.get('rssi_std', self.baseline_rssi_std)
        rtt_std = current_features.get('rtt_std', self.baseline_rtt_std)
        
        # Calculate changes from baseline
        rssi_change = abs(rssi_mean - self.baseline_rssi_mean) / (self.baseline_rssi_std + 1e-6)
        rtt_change = abs(rtt_mean - self.baseline_rtt_mean) / (self.baseline_rtt_std + 1e-6)
        
        # Calculate total change (normalized)
        total_change = (rssi_change + rtt_change) / 2.0
        
        # Determine if recalibration is needed
        should_recalibrate = total_change > self.recalibration_threshold
        
        metadata = {
            'rssi_change': float(rssi_change),
            'rtt_change': float(rtt_change),
            'total_change': float(total_change),
            'threshold': self.recalibration_threshold,
            'should_recalibrate': should_recalibrate,
        }
        
        if should_recalibrate:
            self.last_recalibration_frame = len(self.calibration_history)
            metadata['last_recalibration_frame'] = self.last_recalibration_frame
        
        return should_recalibrate, metadata

    def _update_person_signatures(self, person_signatures: list[dict[str, Any]]) -> None:
        """Update person signature profiles for adaptation.
        
        Args:
            person_signatures: List of person signature dictionaries
        """
        for sig in person_signatures:
            person_id = sig.get('person_id', 0)
            
            if person_id not in self.person_signatures:
                # Initialize new signature profile
                self.person_signatures[person_id] = {
                    'position': sig.get('position', (0.0, 0.0)),
                    'activity': sig.get('activity', 'unknown'),
                    'signal_strength': sig.get('signal_strength', -70.0),
                    'confidence': sig.get('confidence', 1.0),
                    'ema_signal_strength': sig.get('signal_strength', -70.0),
                }
            else:
                # Update existing signature with EMA
                current = self.person_signatures[person_id]
                new_strength = sig.get('signal_strength', current['signal_strength'])
                new_confidence = sig.get('confidence', current['confidence'])
                
                # Update EMA for signal strength
                current['ema_signal_strength'] = (
                    (1 - self.ema_decay) * current['ema_signal_strength'] +
                    self.ema_decay * new_strength
                )
                
                # Update other fields
                current['position'] = sig.get('position', current['position'])
                current['activity'] = sig.get('activity', current['activity'])
                current['confidence'] = new_confidence

    def get_calibration_params(self) -> dict[str, Any]:
        """Get current calibration parameters.
        
        Returns:
            Dictionary containing current calibration parameters
        """
        return {
            'gain': self.calibration_params.gain,
            'offset': self.calibration_params.offset,
            'ema_decay': self.calibration_params.ema_decay,
            'recalibration_threshold': self.calibration_params.recalibration_threshold,
            'baseline_rssi_mean': self.baseline_rssi_mean,
            'baseline_rtt_mean': self.baseline_rtt_mean,
            'ema_rssi_mean': self.ema_rssi_mean,
            'ema_rtt_mean': self.ema_rtt_mean,
        }

    def reset(self) -> None:
        """Reset calibration module to initial state."""
        self.calibration_params = CalibrationParams()
        self.baseline_rssi_mean = -70.0
        self.baseline_rtt_mean = 0.5
        self.baseline_rssi_std = 5.0
        self.baseline_rtt_std = 0.1
        self.ema_rssi_mean = None
        self.ema_rtt_mean = None
        self.calibration_history = []
        self.last_recalibration_frame = 0
        self.person_signatures = {}
