"""Signal separator module for multi-person detection.

This module provides signal separation capabilities for extracting individual
signatures from mixed signals, assigning consistent person IDs, and managing
person ID lifecycle with timeout.
"""

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform
from scipy.signal import correlate
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
import time

from multi_person.core.models import PersonState, PersonSignature
from multi_person.core.interfaces import SignalSeparatorInterface
from multi_person.modules.signal_processor import SignalProcessor, SignalFeatures


@dataclass
class PersonTrack:
    """Track for a single person's signal over time."""
    person_id: int
    signatures: list[PersonSignature] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    active: bool = True


class SignalSeparator(SignalSeparatorInterface):
    """Signal separator for multi-person detection.
    
    This class implements algorithms for:
    - Separating mixed signals from multiple people
    - Assigning and managing person IDs
    - Tracking person signatures over time
    - Releasing person IDs after timeout
    """

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        timeout_seconds: float = 30.0,
        min_correlation: float = 0.3,
        distance_threshold: float = 0.5,
    ):
        """Initialize the signal separator.
        
        Args:
            signal_processor: SignalProcessor instance for feature extraction
            timeout_seconds: Seconds before releasing unused person IDs
            min_correlation: Minimum correlation for signal matching
            distance_threshold: Distance threshold for clustering
        """
        self.signal_processor = signal_processor or SignalProcessor()
        self.timeout_seconds = timeout_seconds
        self.min_correlation = min_correlation
        self.distance_threshold = distance_threshold
        
        # Person tracking state
        self.person_tracks: dict[int, PersonTrack] = {}
        self.next_person_id: int = 1
        self.released_ids: list[int] = []
        
        # Signal history for cross-correlation
        self.signal_history: list[dict[str, Any]] = []
        self.max_history: int = 10

    def separate_signals(self, mixed_signal: Any) -> list[dict[str, Any]]:
        """Separate mixed signal into individual person signals.
        
        Uses RTT jitter pattern analysis and cross-correlation to identify
        and separate signals from multiple people.
        
        Args:
            mixed_signal: Combined signal from multiple people
            
        Returns:
            List of separated signal dictionaries
        """
        if mixed_signal is None:
            return []
        
        # Preprocess the mixed signal
        preprocessed = self.signal_processor.preprocess_signal(mixed_signal)
        
        # If no data, return empty list
        rtt = preprocessed.get('rtt', np.array([]))
        if len(rtt) == 0:
            return []
        
        # Estimate number of people
        estimated_count = self.estimate_signal_count(preprocessed)
        
        # If only one person, return as-is
        if estimated_count == 1:
            return [preprocessed]
        
        # If we have multiple signals to separate
        if isinstance(mixed_signal, dict) and 'rtt' in mixed_signal:
            # Try to separate using clustering
            separated = self._separate_by_clustering(preprocessed, estimated_count)
        else:
            separated = [preprocessed]
        
        # Update signal history
        self.signal_history.append(preprocessed)
        if len(self.signal_history) > self.max_history:
            self.signal_history.pop(0)
        
        return separated

    def _separate_by_clustering(self, signal: dict[str, Any], n_clusters: int) -> list[dict[str, Any]]:
        """Separate signals using hierarchical clustering.
        
        Args:
            signal: Preprocessed signal dictionary
            n_clusters: Number of clusters (people) to separate
            
        Returns:
            List of separated signal dictionaries
        """
        rtt = signal.get('rtt', np.array([]))
        rssi = signal.get('rssi', np.array([]))
        
        if len(rtt) == 0:
            return [signal]
        
        # Only separate if we have enough data points
        if len(rtt) < 20:
            return [signal]
        
        # Only separate if we have enough people to separate
        if n_clusters <= 1:
            return [signal]
        
        # Split the signal into segments for clustering
        # This is a simplified approach - in practice, you'd use more sophisticated methods
        segment_length = max(10, len(rtt) // n_clusters)
        
        segments = []
        for i in range(0, len(rtt), segment_length):
            segment_rtt = rtt[i:i + segment_length]
            segment_rssi = rssi[i:i + segment_length]
            
            if len(segment_rtt) > 0:
                segments.append({
                    'rtt': segment_rtt,
                    'rssi': segment_rssi,
                })
        
        if len(segments) == 0:
            return [signal]
        
        # Extract features for clustering
        feature_matrix = []
        for seg in segments:
            rtt_seg = seg.get('rtt', np.array([]))
            rssi_seg = seg.get('rssi', np.array([]))
            
            features = [
                np.mean(rtt_seg) if len(rtt_seg) > 0 else 0.0,
                np.std(rtt_seg) if len(rtt_seg) > 0 else 0.0,
                np.mean(rssi_seg) if len(rssi_seg) > 0 else 0.0,
                np.std(rssi_seg) if len(rssi_seg) > 0 else 0.0,
            ]
            feature_matrix.append(features)
        
        feature_matrix = np.array(feature_matrix)
        
        # If we don't have enough segments, return original signal
        if len(feature_matrix) < 2:
            return [signal]
        
        # Calculate distances and perform clustering
        try:
            distances = pdist(feature_matrix, metric='euclidean')
            Z = linkage(distances, method='ward')
            cluster_labels = fcluster(Z, t=n_clusters, criterion='maxclust')
        except Exception:
            # Fallback if clustering fails
            return [signal]
        
        # Group segments by cluster
        separated_signals = []
        for cluster_id in range(1, n_clusters + 1):
            cluster_indices = np.where(cluster_labels == cluster_id)[0]
            
            if len(cluster_indices) == 0:
                continue
            
            # Combine segments in this cluster
            combined_rtt = np.concatenate([segments[i]['rtt'] for i in cluster_indices])
            combined_rssi = np.concatenate([segments[i]['rssi'] for i in cluster_indices])
            
            separated_signals.append({
                'rtt': combined_rtt,
                'rssi': combined_rssi,
                'cluster_id': int(cluster_id),
            })
        
        return separated_signals if separated_signals else [signal]

    def assign_person_ids(self, signatures: list[PersonSignature]) -> list[PersonState]:
        """Assign consistent person IDs to signatures.
        
        Uses cross-correlation and temporal tracking to maintain consistent
        person IDs across frames.
        
        Args:
            signatures: List of person signatures to assign IDs to
            
        Returns:
            List of PersonState objects with assigned IDs
        """
        current_time = time.time()
        person_states = []
        
        if len(signatures) == 0:
            return person_states
        
        # Get existing person tracks
        existing_tracks = [
            track for track in self.person_tracks.values()
            if track.active and (current_time - track.last_seen) < self.timeout_seconds
        ]
        
        # Calculate correlation matrix between new signatures and existing tracks
        n_new = len(signatures)
        n_existing = len(existing_tracks)
        
        if n_existing == 0:
            # No existing tracks, assign new IDs
            for sig in signatures:
                person_id = self._get_next_person_id()
                track = PersonTrack(
                    person_id=person_id,
                    signatures=[sig],
                    last_seen=current_time,
                )
                self.person_tracks[person_id] = track
                
                person_state = PersonState(
                    person_id=person_id,
                    position=sig.position,
                    activity=sig.activity,
                    timestamp=current_time,
                    signal_features=self._signature_to_features(sig),
                    velocity=sig.velocity,
                    confidence=sig.confidence,
                )
                person_states.append(person_state)
        else:
            # Match new signatures to existing tracks
            matched_existing = set()
            
            for sig in signatures:
                best_match_idx = -1
                best_correlation = -1
                
                for idx, track in enumerate(existing_tracks):
                    if idx in matched_existing:
                        continue
                    
                    # Calculate correlation with track's average signature
                    if len(track.signatures) > 0:
                        avg_sig = self._average_signature(track.signatures)
                        correlation = self._calculate_correlation(sig, avg_sig)
                        
                        if correlation > best_correlation:
                            best_correlation = correlation
                            best_match_idx = idx
                
                if best_match_idx >= 0 and best_correlation >= self.min_correlation:
                    # Match found, update existing track
                    track = existing_tracks[best_match_idx]
                    track.signatures.append(sig)
                    track.last_seen = current_time
                    
                    person_state = PersonState(
                        person_id=track.person_id,
                        position=sig.position,
                        activity=sig.activity,
                        timestamp=current_time,
                        signal_features=self._signature_to_features(sig),
                        velocity=sig.velocity,
                        confidence=sig.confidence,
                    )
                    person_states.append(person_state)
                    matched_existing.add(best_match_idx)
                else:
                    # No match found, assign new ID
                    person_id = self._get_next_person_id()
                    track = PersonTrack(
                        person_id=person_id,
                        signatures=[sig],
                        last_seen=current_time,
                    )
                    self.person_tracks[person_id] = track
                    
                    person_state = PersonState(
                        person_id=person_id,
                        position=sig.position,
                        activity=sig.activity,
                        timestamp=current_time,
                        signal_features=self._signature_to_features(sig),
                        velocity=sig.velocity,
                        confidence=sig.confidence,
                    )
                    person_states.append(person_state)
        
        # Mark unmatched tracks as inactive (will be released after timeout)
        for idx, track in enumerate(existing_tracks):
            if idx not in matched_existing:
                # Track not matched in this frame, but still active
                # It will be released after timeout
                pass
        
        return person_states

    def release_person_id(self, person_id: int) -> bool:
        """Release a person ID after timeout.
        
        Args:
            person_id: ID to release
            
        Returns:
            True if ID was released, False if not found
        """
        if person_id in self.person_tracks:
            track = self.person_tracks[person_id]
            track.active = False
            self.released_ids.append(person_id)
            del self.person_tracks[person_id]
            return True
        return False

    def _get_next_person_id(self) -> int:
        """Get the next available person ID.
        
        Reuses released IDs if available.
        
        Returns:
            Person ID
        """
        if self.released_ids:
            return self.released_ids.pop(0)
        
        person_id = self.next_person_id
        self.next_person_id += 1
        return person_id

    def estimate_signal_count(self, signal: Any) -> int:
        """Estimate number of people in signal.
        
        Uses RTT jitter pattern analysis to estimate how many people
        are present in the signal.
        
        Args:
            signal: Signal data to analyze
            
        Returns:
            Estimated number of people
        """
        if signal is None:
            return 0
        
        # Preprocess if needed
        if isinstance(signal, dict) and 'rtt' not in signal:
            signal = self.signal_processor.preprocess_signal(signal)
        
        rtt = signal.get('rtt', np.array([]))
        
        if len(rtt) == 0:
            return 0
        
        if len(rtt) < 10:
            return 1  # Not enough data, assume single person
        
        # Calculate RTT statistics
        rtt_std = float(np.std(rtt))
        rtt_mean = float(np.mean(rtt))
        
        # Analyze RTT jitter patterns
        # Multiple people typically show more complex jitter patterns
        
        # Method 1: Variance analysis
        # Higher variance may indicate multiple people
        variance_ratio = rtt_std / (rtt_mean + 1e-8)
        
        # Method 2: Peak detection in RTT signal
        # Multiple people may cause multiple peaks
        rtt_diff = np.diff(rtt)
        zero_crossings = np.sum(np.diff(np.sign(rtt_diff)) != 0)
        
        # Method 3: Frequency domain analysis
        # Multiple people may show multiple frequency components
        if len(rtt) > 20:
            try:
                fft_result = np.fft.fft(rtt - np.mean(rtt))
                frequencies = np.fft.fftfreq(len(rtt), d=0.1)
                magnitudes = np.abs(fft_result[:len(rtt) // 2])
                
                # Count significant frequency peaks
                threshold = np.mean(magnitudes) + 2 * np.std(magnitudes)  # Higher threshold
                peaks = np.sum(magnitudes[1:] > threshold)
                
                # Estimate count based on frequency analysis
                freq_based_estimate = min(5, max(1, peaks // 3))  # More conservative
            except Exception:
                freq_based_estimate = 1
        else:
            freq_based_estimate = 1
        
        # Combine methods
        # Use variance ratio as primary indicator
        if variance_ratio > 2.0:
            # High variance suggests multiple people
            base_estimate = min(5, max(1, int(variance_ratio)))
        else:
            base_estimate = 1
        
        # Adjust based on frequency analysis
        estimated_count = max(base_estimate, freq_based_estimate)
        
        # Cap at reasonable maximum
        return min(estimated_count, 5)

    def _signature_to_features(self, signature: PersonSignature) -> dict[str, Any]:
        """Convert PersonSignature to signal features dict.
        
        Args:
            signature: PersonSignature to convert
            
        Returns:
            Dictionary of signal features
        """
        return {
            'rssi_mean': signature.signal_strength,
            'position': signature.position,
            'activity': signature.activity,
            'confidence': signature.confidence,
            'velocity': signature.velocity,
        }

    def _average_signature(self, signatures: list[PersonSignature]) -> PersonSignature:
        """Calculate average of multiple signatures.
        
        Args:
            signatures: List of signatures to average
            
        Returns:
            Average signature
        """
        if len(signatures) == 0:
            return signatures[0] if signatures else PersonSignature(
                person_id=0,
                position=(0.0, 0.0),
                activity="unknown",
                signal_strength=0.0,
                confidence=0.0,
            )
        
        if len(signatures) == 1:
            return signatures[0]
        
        positions = np.array([s.position for s in signatures])
        avg_position = (float(np.mean(positions[:, 0])), float(np.mean(positions[:, 1])))
        
        return PersonSignature(
            person_id=signatures[0].person_id,
            position=avg_position,
            activity=signatures[0].activity,
            signal_strength=float(np.mean([s.signal_strength for s in signatures])),
            velocity=signatures[0].velocity,
            confidence=float(np.mean([s.confidence for s in signatures])),
        )

    def _calculate_correlation(self, sig1: PersonSignature, sig2: PersonSignature) -> float:
        """Calculate correlation between two signatures.
        
        Args:
            sig1: First signature
            sig2: Second signature
            
        Returns:
            Correlation value (-1 to 1)
        """
        # Position correlation (inverse distance)
        pos1 = np.array(sig1.position)
        pos2 = np.array(sig2.position)
        distance = np.linalg.norm(pos1 - pos2)
        
        # Convert distance to correlation (closer = higher correlation)
        # Use smaller distance threshold for better discrimination
        position_correlation = np.exp(-distance / 10.0)
        
        # Activity correlation
        activity_correlation = 1.0 if sig1.activity == sig2.activity else 0.0
        
        # Signal strength correlation
        strength_diff = abs(sig1.signal_strength - sig2.signal_strength)
        strength_correlation = np.exp(-strength_diff / 30.0)
        
        # Combined correlation
        combined = (
            0.4 * position_correlation +
            0.3 * activity_correlation +
            0.3 * strength_correlation
        )
        
        return float(combined)

    def get_active_person_count(self) -> int:
        """Get count of currently active persons.
        
        Returns:
            Number of active person tracks
        """
        current_time = time.time()
        return sum(
            1 for track in self.person_tracks.values()
            if track.active and (current_time - track.last_seen) < self.timeout_seconds
        )

    def get_person_states(self) -> list[PersonState]:
        """Get current states of all tracked persons.
        
        Returns:
            List of PersonState objects
        """
        current_time = time.time()
        person_states = []
        
        for track in self.person_tracks.values():
            if track.active and (current_time - track.last_seen) < self.timeout_seconds:
                if track.signatures:
                    latest_sig = track.signatures[-1]
                    person_state = PersonState(
                        person_id=track.person_id,
                        position=latest_sig.position,
                        activity=latest_sig.activity,
                        timestamp=track.last_seen,
                        signal_features=self._signature_to_features(latest_sig),
                        velocity=latest_sig.velocity,
                        confidence=latest_sig.confidence,
                    )
                    person_states.append(person_state)
        
        return person_states

    def reset(self) -> None:
        """Reset the signal separator state."""
        self.person_tracks = {}
        self.next_person_id = 1
        self.released_ids = []
        self.signal_history = []
