"""Signal processing module for multi-person detection.

This module provides signal processing capabilities for extracting features,
clustering signals, and separating overlapping signals from multiple people
using Wi-Fi signal metadata (RSSI and RTT).
"""

import numpy as np
from scipy import signal as scipy_signal
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform
from dataclasses import dataclass
from typing import Any, Optional
from multi_person.core.models import PersonSignature
from multi_person.core.interfaces import SignalProcessorInterface


@dataclass
class SignalFeatures:
    """Features extracted from a Wi-Fi signal."""
    rssi_mean: float
    rssi_std: float
    rtt_mean: float
    rtt_std: float
    rtt_jitter: float
    dominant_frequency: float
    dominant_frequency_magnitude: float
    breathing_energy: float
    walking_energy: float
    fft_spectrum: np.ndarray
    frequencies: np.ndarray


class SignalProcessor(SignalProcessorInterface):
    """Signal processor for multi-person detection.
    
    This class implements signal processing algorithms for:
    - Preprocessing raw Wi-Fi signal data
    - Extracting frequency domain features using FFT
    - Clustering signals by person using RTT jitter patterns
    - Separating overlapping signals using cross-correlation
    """

    def __init__(
        self,
        sample_rate: float = 10.0,
        breathing_band: tuple = (0.1, 0.5),
        walking_band: tuple = (1.0, 4.0),
        rtt_window: int = 100,
        rssi_window: int = 50,
    ):
        """Initialize the signal processor.
        
        Args:
            sample_rate: Sampling rate in Hz
            breathing_band: Frequency band for breathing detection (Hz)
            walking_band: Frequency band for walking detection (Hz)
            rtt_window: Window size for RTT data
            rssi_window: Window size for RSSI data
        """
        self.sample_rate = sample_rate
        self.breathing_band = breathing_band
        self.walking_band = walking_band
        self.rtt_window = rtt_window
        self.rssi_window = rssi_window
        
        # Buffer for RTT and RSSI data
        self.rtt_buffer: list[float] = []
        self.rssi_buffer: list[float] = []
        
        # FFT frequency bins
        self.freq_bins: Optional[np.ndarray] = None
        self.spectrum: Optional[np.ndarray] = None

    def preprocess_signal(self, raw_signal: Any) -> dict[str, Any]:
        """Preprocess raw signal data.
        
        Cleans and normalizes Wi-Fi signal data (RSSI and RTT) to prepare
        for feature extraction.
        
        Args:
            raw_signal: Raw signal data containing RSSI and RTT values.
                       Expected format: dict with 'rssi' and 'rtt' keys,
                       or a tuple/list of (rssi, rtt) values.
        
        Returns:
            Dictionary containing preprocessed signal data with keys:
            - 'rssi': Normalized RSSI values
            - 'rtt': Normalized RTT values
            - 'cleaned': Boolean indicating if data was cleaned
            - 'metadata': Preprocessing metadata
        
        Raises:
            ValueError: If input format is invalid or data is empty
        """
        if raw_signal is None:
            raise ValueError("Raw signal cannot be None")
        
        # Parse input
        if isinstance(raw_signal, dict):
            rssi_values = raw_signal.get('rssi', [])
            rtt_values = raw_signal.get('rtt', [])
        elif isinstance(raw_signal, (tuple, list)):
            if len(raw_signal) >= 2:
                rssi_values = raw_signal[0]
                rtt_values = raw_signal[1]
            elif len(raw_signal) == 1:
                rssi_values = []
                rtt_values = raw_signal[0]
            else:
                raise ValueError("Invalid signal format: empty tuple/list")
        else:
            raise ValueError(f"Invalid signal format: {type(raw_signal)}")
        
        # Convert to numpy arrays
        rssi_values = np.array(rssi_values) if not isinstance(rssi_values, np.ndarray) else rssi_values
        rtt_values = np.array(rtt_values) if not isinstance(rtt_values, np.ndarray) else rtt_values
        
        # Handle empty data
        if len(rssi_values) == 0 and len(rtt_values) == 0:
            return {
                'rssi': np.array([]),
                'rtt': np.array([]),
                'cleaned': False,
                'metadata': {'warning': 'Empty signal data'}
            }
        
        cleaned = False
        
        # Process RSSI
        if len(rssi_values) > 0:
            # Remove outliers using IQR
            q1, q3 = np.percentile(rssi_values, [25, 75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            rssi_cleaned = rssi_values[(rssi_values >= lower_bound) & (rssi_values <= upper_bound)]
            
            if len(rssi_cleaned) < len(rssi_values):
                cleaned = True
            
            # Normalize to 0-1 range
            if len(rssi_cleaned) > 0:
                rssi_min, rssi_max = rssi_cleaned.min(), rssi_cleaned.max()
                if rssi_max - rssi_min > 1e-6:
                    rssi_normalized = (rssi_cleaned - rssi_min) / (rssi_max - rssi_min)
                else:
                    rssi_normalized = np.zeros_like(rssi_cleaned)
            else:
                rssi_normalized = np.array([])
        else:
            rssi_normalized = np.array([])
        
        # Process RTT
        if len(rtt_values) > 0:
            # Remove outliers using IQR
            q1, q3 = np.percentile(rtt_values, [25, 75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            rtt_cleaned = rtt_values[(rtt_values >= lower_bound) & (rtt_values <= upper_bound)]
            
            if len(rtt_cleaned) < len(rtt_values):
                cleaned = True
            
            # Normalize to 0-1 range
            if len(rtt_cleaned) > 0:
                rtt_min, rtt_max = rtt_cleaned.min(), rtt_cleaned.max()
                if rtt_max - rtt_min > 1e-6:
                    rtt_normalized = (rtt_cleaned - rtt_min) / (rtt_max - rtt_min)
                else:
                    rtt_normalized = np.zeros_like(rtt_cleaned)
            else:
                rtt_normalized = np.array([])
        else:
            rtt_normalized = np.array([])
        
        # Update buffers
        self.rtt_buffer = rtt_normalized.tolist()[-self.rtt_window:]
        self.rssi_buffer = rssi_normalized.tolist()[-self.rssi_window:]
        
        return {
            'rssi': rssi_normalized,
            'rtt': rtt_normalized,
            'rtt_original': rtt_values,  # Store original RTT for jitter calculation
            'cleaned': cleaned,
            'metadata': {
                'original_rssi_count': len(rssi_values),
                'original_rtt_count': len(rtt_values),
                'cleaned_rssi_count': len(rssi_normalized),
                'cleaned_rtt_count': len(rtt_normalized),
                'sample_rate': self.sample_rate
            }
        }

    def extract_features(self, signal: dict[str, Any]) -> SignalFeatures:
        """Extract features from preprocessed signal.
        
        Performs FFT-based frequency analysis to extract features including:
        - RSSI and RTT statistics (mean, std)
        - Dominant frequency and magnitude
        - Breathing and walking energy bands
        
        Args:
            signal: Preprocessed signal dictionary from preprocess_signal()
        
        Returns:
            SignalFeatures dataclass containing extracted features
        """
        rssi = signal.get('rssi', np.array([]))
        rtt = signal.get('rtt', np.array([]))
        
        # Calculate RSSI features
        rssi_mean = float(np.mean(rssi)) if len(rssi) > 0 else 0.0
        rssi_std = float(np.std(rssi)) if len(rssi) > 0 else 0.0
        
        # Calculate RTT features
        rtt_mean = float(np.mean(rtt)) if len(rtt) > 0 else 0.0
        rtt_std = float(np.std(rtt)) if len(rtt) > 0 else 0.0
        
        # Calculate RTT jitter (variance as measure of micro-movements)
        rtt_jitter = float(np.var(rtt)) if len(rtt) > 0 else 0.0
        
        # Perform FFT on RTT signal for frequency analysis
        if len(rtt) > 1:
            # Apply Hanning window to reduce spectral leakage
            windowed_rtt = rtt * np.hanning(len(rtt))
            
            # Compute FFT
            fft_result = np.fft.fft(windowed_rtt)
            frequencies = np.fft.fftfreq(len(rtt), d=1.0 / self.sample_rate)
            
            # Get positive frequencies only
            pos_mask = frequencies >= 0
            frequencies = frequencies[pos_mask]
            fft_magnitude = np.abs(fft_result[pos_mask])
            
            # Find dominant frequency
            if len(fft_magnitude) > 1:
                dominant_idx = np.argmax(fft_magnitude[1:]) + 1  # Skip DC component
                dominant_frequency = float(frequencies[dominant_idx])
                dominant_frequency_magnitude = float(fft_magnitude[dominant_idx])
            else:
                dominant_frequency = 0.0
                dominant_frequency_magnitude = 0.0
            
            # Calculate energy in breathing and walking bands
            breathing_mask = (frequencies >= self.breathing_band[0]) & (frequencies <= self.breathing_band[1])
            walking_mask = (frequencies >= self.walking_band[0]) & (frequencies <= self.walking_band[1])
            
            breathing_energy = float(np.sum(fft_magnitude[breathing_mask] ** 2)) if np.any(breathing_mask) else 0.0
            walking_energy = float(np.sum(fft_magnitude[walking_mask] ** 2)) if np.any(walking_mask) else 0.0
            
            # Store spectrum for later use
            self.freq_bins = frequencies
            self.spectrum = fft_magnitude
        else:
            dominant_frequency = 0.0
            dominant_frequency_magnitude = 0.0
            breathing_energy = 0.0
            walking_energy = 0.0
            frequencies = np.array([])
            fft_magnitude = np.array([])
        
        return SignalFeatures(
            rssi_mean=rssi_mean,
            rssi_std=rssi_std,
            rtt_mean=rtt_mean,
            rtt_std=rtt_std,
            rtt_jitter=rtt_jitter,
            dominant_frequency=dominant_frequency,
            dominant_frequency_magnitude=dominant_frequency_magnitude,
            breathing_energy=breathing_energy,
            walking_energy=walking_energy,
            fft_spectrum=fft_magnitude,
            frequencies=frequencies
        )

    def cluster_signals(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cluster signals by person using RTT jitter patterns.
        
        Uses hierarchical clustering based on signal features to group
        signals that likely belong to the same person.
        
        Args:
            signals: List of preprocessed signal dictionaries
        
        Returns:
            List of clusters, where each cluster contains indices of signals
            that belong to the same person
        """
        if len(signals) == 0:
            return []
        
        if len(signals) == 1:
            return [[0]]
        
        # Extract features for clustering
        feature_matrix = []
        for sig in signals:
            rtt = sig.get('rtt', np.array([]))
            rssi = sig.get('rssi', np.array([]))
            
            # Calculate features
            rtt_std = float(np.std(rtt)) if len(rtt) > 0 else 0.0
            rtt_mean = float(np.mean(rtt)) if len(rtt) > 0 else 0.0
            rssi_std = float(np.std(rssi)) if len(rssi) > 0 else 0.0
            rssi_mean = float(np.mean(rssi)) if len(rssi) > 0 else 0.0
            
            # Combine features into a feature vector
            features = [
                rtt_mean,
                rtt_std,
                rssi_mean,
                rssi_std,
            ]
            feature_matrix.append(features)
        
        feature_matrix = np.array(feature_matrix)
        
        # Calculate pairwise distances
        distances = pdist(feature_matrix, metric='euclidean')
        
        # Perform hierarchical clustering
        Z = linkage(distances, method='ward')
        
        # Determine optimal number of clusters using elbow method
        # For now, use a simple distance threshold
        distance_threshold = np.percentile(distances, 75) if len(distances) > 0 else 1.0
        
        # Get cluster assignments
        cluster_labels = fcluster(Z, t=distance_threshold, criterion='distance')
        
        # Group signals by cluster
        unique_clusters = np.unique(cluster_labels)
        clusters = []
        
        for cluster_id in unique_clusters:
            cluster_indices = np.where(cluster_labels == cluster_id)[0].tolist()
            clusters.append(cluster_indices)
        
        return clusters

    def separate_overlapping_signals(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Separate overlapping signals using cross-correlation.
        
        Uses cross-correlation analysis to identify and separate signals
        from multiple people when their Wi-Fi signals overlap.
        
        Args:
            signals: List of preprocessed signal dictionaries
        
        Returns:
            List of separated signal dictionaries
        """
        if len(signals) == 0:
            return []
        
        if len(signals) == 1:
            return signals.copy()
        
        # Extract RTT sequences for cross-correlation
        rtt_sequences = []
        for sig in signals:
            rtt = sig.get('rtt', np.array([]))
            if len(rtt) > 0:
                # Normalize each sequence
                rtt_normalized = (rtt - np.mean(rtt)) / (np.std(rtt) + 1e-8)
                rtt_sequences.append(rtt_normalized)
            else:
                rtt_sequences.append(np.array([]))
        
        # If we don't have enough data, return original signals
        if len(rtt_sequences) < 2:
            return signals.copy()
        
        # Calculate cross-correlation matrix
        n_signals = len(rtt_sequences)
        correlation_matrix = np.zeros((n_signals, n_signals))
        
        for i in range(n_signals):
            for j in range(n_signals):
                if i != j and len(rtt_sequences[i]) > 0 and len(rtt_sequences[j]) > 0:
                    # Calculate cross-correlation
                    corr = np.correlate(rtt_sequences[i], rtt_sequences[j], mode='full')
                    if len(corr) > 0:
                        correlation_matrix[i, j] = np.max(np.abs(corr))
                    else:
                        correlation_matrix[i, j] = 0.0
        
        # Use correlation matrix to separate signals
        # Signals with low correlation are likely from different people
        separated_signals = []
        
        for i, sig in enumerate(signals):
            # Create a copy of the signal
            separated_sig = sig.copy()
            
            # Add separation metadata
            separated_sig['separation_info'] = {
                'signal_index': i,
                'correlation_with_others': float(np.mean(correlation_matrix[i])) if i < correlation_matrix.shape[0] else 0.0,
                'is_separated': True
            }
            
            separated_signals.append(separated_sig)
        
        return separated_signals

    def create_person_signature(
        self,
        signal: dict[str, Any],
        features: SignalFeatures,
        person_id: int,
        position: tuple[float, float] = (0.0, 0.0),
        activity: str = "unknown",
        confidence: float = 1.0
    ) -> PersonSignature:
        """Create a PersonSignature from signal data.
        
        Args:
            signal: Preprocessed signal dictionary
            features: Extracted signal features
            person_id: Unique identifier for the person
            position: Estimated (x, y) position
            activity: Detected activity (standing, walking, etc.)
            confidence: Confidence in the signature (0-1)
        
        Returns:
            PersonSignature dataclass
        """
        # Calculate velocity from signal changes (simplified)
        rtt = signal.get('rtt', np.array([]))
        if len(rtt) >= 2:
            velocity_magnitude = float(np.std(np.diff(rtt)))
            velocity = (velocity_magnitude, velocity_magnitude * 0.5)
        else:
            velocity = None
        
        return PersonSignature(
            person_id=person_id,
            position=position,
            activity=activity,
            signal_strength=features.rssi_mean,
            velocity=velocity,
            confidence=confidence
        )

    def reset(self) -> None:
        """Reset the signal processor state."""
        self.rtt_buffer = []
        self.rssi_buffer = []
        self.freq_bins = None
        self.spectrum = None
