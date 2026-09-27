"""Activity recognizer module for multi-person detection.

This module provides activity recognition capabilities for classifying human
activities (walking, breathing, still, gesture) based on Wi-Fi signal features.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
import time

from multi_person.core.models import PersonState, PersonStateEvent
from multi_person.core.interfaces import ActivityRecognizerInterface
from multi_person.modules.signal_processor import SignalProcessor, SignalFeatures


@dataclass
class ActivityFeatures:
    """Features extracted for activity classification."""
    breathing_energy: float
    walking_energy: float
    high_freq_energy: float
    jitter: float
    energy_ratio_breathing: float
    energy_ratio_walking: float
    energy_ratio_high_freq: float
    signal_strength: float


@dataclass
class ActivityState:
    """Current activity state for a person."""
    person_id: int
    activity: str
    timestamp: float
    confidence: float
    features: ActivityFeatures
    activity_history: list[tuple[str, float]] = field(default_factory=list)


class ActivityRecognizer(ActivityRecognizerInterface):
    """Activity recognizer for multi-person detection.
    
    This class implements activity recognition algorithms for:
    - Classifying activities (walking, breathing, still, gesture)
    - Analyzing frequency band energy patterns
    - Calculating activity confidence percentages
    - Emitting activity change events
    - Managing per-person activity states
    """

    # Activity definitions
    # Energy values are relative (0-1 range for ratios, absolute for raw energy)
    ACTIVITIES = {
        'walking': {
            'breathing_band': (0.1, 0.5),
            'walking_band': (1.0, 4.0),
            'high_freq_band': (4.0, 10.0),
            'min_breathing_energy': 0.01,
            'min_walking_energy': 0.1,
            'min_high_freq_energy': 0.02,
            'max_jitter': 0.1,
            'min_jitter': 0.01,
            'optimal_breathing_energy': 0.1,
            'optimal_walking_energy': 0.5,
            'optimal_high_freq_energy': 0.2,
            'min_breathing_ratio': 0.05,
            'optimal_breathing_ratio': 0.2,
            'min_walking_ratio': 0.3,
            'optimal_walking_ratio': 0.7,
            'min_high_freq_ratio': 0.05,
            'optimal_high_freq_ratio': 0.3,
        },
        'breathing': {
            'breathing_band': (0.1, 0.5),
            'walking_band': (1.0, 4.0),
            'high_freq_band': (4.0, 10.0),
            'min_breathing_energy': 0.01,
            'min_walking_energy': 0.005,
            'min_high_freq_energy': 0.002,
            'max_jitter': 0.03,
            'min_jitter': 0.001,
            'optimal_breathing_energy': 0.5,
            'optimal_walking_energy': 0.1,
            'optimal_high_freq_energy': 0.05,
            'min_breathing_ratio': 0.3,
            'optimal_breathing_ratio': 0.7,
            'min_walking_ratio': 0.05,
            'optimal_walking_ratio': 0.2,
            'min_high_freq_ratio': 0.01,
            'optimal_high_freq_ratio': 0.1,
        },
        'still': {
            'breathing_band': (0.1, 0.5),
            'walking_band': (1.0, 4.0),
            'high_freq_band': (4.0, 10.0),
            'min_breathing_energy': 0.00005,
            'min_walking_energy': 0.00005,
            'min_high_freq_energy': 0.00002,
            'max_jitter': 0.001,
            'min_jitter': 0.0,
            'optimal_breathing_energy': 0.0005,
            'optimal_walking_energy': 0.0002,
            'optimal_high_freq_energy': 0.0001,
            'min_breathing_ratio': 0.1,
            'optimal_breathing_ratio': 0.4,
            'min_walking_ratio': 0.05,
            'optimal_walking_ratio': 0.2,
            'min_high_freq_ratio': 0.01,
            'optimal_high_freq_ratio': 0.1,
        },
        'gesture': {
            'breathing_band': (0.1, 0.5),
            'walking_band': (1.0, 4.0),
            'high_freq_band': (4.0, 10.0),
            'min_breathing_energy': 0.01,
            'min_walking_energy': 0.02,
            'min_high_freq_energy': 0.1,
            'max_jitter': 0.2,
            'min_jitter': 0.05,
            'optimal_breathing_energy': 0.05,
            'optimal_walking_energy': 0.1,
            'optimal_high_freq_energy': 0.5,
            'min_breathing_ratio': 0.05,
            'optimal_breathing_ratio': 0.2,
            'min_walking_ratio': 0.1,
            'optimal_walking_ratio': 0.3,
            'min_high_freq_ratio': 0.3,
            'optimal_high_freq_ratio': 0.7,
        },
    }

    # Default thresholds
    DEFAULT_THRESHOLDS = {
        'breathing_energy': 0.1,
        'walking_energy': 0.1,
        'high_freq_energy': 0.1,
        'jitter': 0.05,
    }

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        sample_rate: float = 10.0,
        breathing_band: tuple = (0.1, 0.5),
        walking_band: tuple = (1.0, 4.0),
        high_freq_band: tuple = (4.0, 10.0),
        min_confidence: float = 0.5,
    ):
        """Initialize the activity recognizer.
        
        Args:
            signal_processor: SignalProcessor instance for feature extraction
            sample_rate: Sampling rate in Hz
            breathing_band: Frequency band for breathing detection (Hz)
            walking_band: Frequency band for walking detection (Hz)
            high_freq_band: Frequency band for gesture detection (Hz)
            min_confidence: Minimum confidence for activity classification
        """
        self.signal_processor = signal_processor or SignalProcessor(
            sample_rate=sample_rate,
            breathing_band=breathing_band,
            walking_band=walking_band,
        )
        self.sample_rate = sample_rate
        self.breathing_band = breathing_band
        self.walking_band = walking_band
        self.high_freq_band = high_freq_band
        self.min_confidence = min_confidence
        
        # Per-person activity state tracking
        self.person_states: dict[int, ActivityState] = {}
        self.last_activity_times: dict[int, float] = {}
        
        # Event system
        self.event_callbacks: list[callable] = []
        self.event_counter: int = 0

    def recognize_activity(self, signal: Any) -> str:
        """Recognize activity from a single person's signal.
        
        Analyzes the signal's frequency band energy and jitter to classify
        the person's activity (walking, breathing, still, or gesture).
        
        Args:
            signal: Signal data from person (dict with 'rssi', 'rtt' keys,
                   or tuple/list of (rssi, rtt) values)
        
        Returns:
            Activity label ('walking', 'breathing', 'still', 'gesture')
        """
        # Preprocess the signal
        preprocessed = self.signal_processor.preprocess_signal(signal)
        
        # Extract features
        features = self.signal_processor.extract_features(preprocessed)
        
        # Calculate activity features
        activity_features = self._calculate_activity_features(features, preprocessed)
        
        # Classify activity
        activity = self._classify_activity(activity_features)
        
        return activity

    def recognize_activities(self, signals: list[Any]) -> list[str]:
        """Recognize activities for multiple people.
        
        Args:
            signals: List of individual person signals
        
        Returns:
            List of activity labels for each person
        """
        activities = []
        for signal in signals:
            activity = self.recognize_activity(signal)
            activities.append(activity)
        return activities

    def calculate_confidence(self, person_id: int) -> float:
        """Calculate activity confidence percentage for a person.
        
        Args:
            person_id: Person ID to calculate confidence for
        
        Returns:
            Confidence percentage (0-100)
        """
        if person_id not in self.person_states:
            return 0.0
        
        state = self.person_states[person_id]
        return state.confidence * 100

    def emit_activity_change_event(
        self,
        person_id: int,
        old_activity: str,
        new_activity: str,
    ) -> Optional[PersonStateEvent]:
        """Emit an activity change event.
        
        Args:
            person_id: Person ID
            old_activity: Previous activity
            new_activity: New activity
        
        Returns:
            PersonStateEvent object or None if no event emitted
        """
        current_time = time.time()
        
        # Get current person state
        person_state = self.person_states.get(person_id)
        
        # Create new state for old_state if not available
        old_state = None
        if old_activity:
            old_state = PersonState(
                person_id=person_id,
                position=(0.0, 0.0),
                activity=old_activity,
                timestamp=current_time,
                signal_features={},
            )
        
        # Create new state for new_state if available
        new_state = None
        if person_state:
            new_state = PersonState(
                person_id=person_state.person_id,
                position=(0.0, 0.0),
                activity=person_state.activity,
                timestamp=person_state.timestamp,
                signal_features={},
            )
        
        # Create event
        self.event_counter += 1
        event = PersonStateEvent(
            event_id=self.event_counter,
            person_id=person_id,
            event_type='activity_change',
            timestamp=current_time,
            old_state=old_state,
            new_state=new_state,
        )
        
        # Call event callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception:
                # Skip failed callbacks
                pass
        
        return event

    def update_person_state(
        self,
        person_id: int,
        activity: str,
        features: ActivityFeatures,
        confidence: float,
    ) -> None:
        """Update the activity state for a person.
        
        Args:
            person_id: Person ID
            activity: Current activity
            features: Activity features
            confidence: Confidence in classification
        """
        current_time = time.time()
        
        # Get previous activity if exists
        old_activity = None
        if person_id in self.person_states:
            old_activity = self.person_states[person_id].activity
        
        # Create new state
        state = ActivityState(
            person_id=person_id,
            activity=activity,
            timestamp=current_time,
            confidence=confidence,
            features=features,
            activity_history=[
                (old_activity, current_time)
                for old_activity, _ in self.person_states.get(person_id, ActivityState(
                    person_id=person_id,
                    activity="",
                    timestamp=0,
                    confidence=0,
                    features=ActivityFeatures(
                        breathing_energy=0,
                        walking_energy=0,
                        high_freq_energy=0,
                        jitter=0,
                        energy_ratio_breathing=0,
                        energy_ratio_walking=0,
                        energy_ratio_high_freq=0,
                        signal_strength=0,
                    ),
                )).activity_history[-10:]
            ] + [(activity, current_time)],
        )
        
        self.person_states[person_id] = state
        self.last_activity_times[person_id] = current_time
        
        # Emit event if activity changed
        if old_activity is not None and old_activity != activity:
            self.emit_activity_change_event(person_id, old_activity, activity)

    def _calculate_activity_features(
        self,
        features: SignalFeatures,
        preprocessed: dict[str, Any],
    ) -> ActivityFeatures:
        """Calculate activity-specific features.
        
        Args:
            features: Signal features from SignalProcessor
            preprocessed: Preprocessed signal data
        
        Returns:
            ActivityFeatures dataclass
        """
        # Calculate total energy for ratios
        total_energy = (
            features.breathing_energy +
            features.walking_energy +
            0.1  # Small constant to avoid division by zero
        )
        
        # Calculate energy ratios
        breathing_ratio = features.breathing_energy / total_energy
        walking_ratio = features.walking_energy / total_energy
        
        # Calculate high frequency energy (simplified)
        high_freq_energy = self._estimate_high_freq_energy(features)
        high_freq_ratio = high_freq_energy / total_energy if total_energy > 0 else 0.0
        
        # Get jitter from original RTT if available, otherwise use normalized
        # The original RTT is stored for accurate jitter calculation
        rtt_original = preprocessed.get('rtt_original')
        if rtt_original is not None and len(rtt_original) > 0:
            jitter = float(np.std(rtt_original)) if len(rtt_original) > 0 else 0.0
        else:
            rtt = preprocessed.get('rtt', np.array([]))
            jitter = float(np.std(rtt)) if len(rtt) > 0 else 0.0
        
        # Get signal strength from original raw RSSI if available
        # The preprocessed signal contains normalized RSSI (0-1), but we need raw RSSI
        # Check if original data is available in metadata
        original_rssi = preprocessed.get('metadata', {}).get('original_rssi_count', 0)
        if original_rssi > 0 and len(rtt_original) > 0:
            # Use the normalized RSSI as a relative measure
            signal_strength = float(np.mean(rtt_original))  # Use RTT mean as proxy
        else:
            signal_strength = -70.0
        
        return ActivityFeatures(
            breathing_energy=features.breathing_energy,
            walking_energy=features.walking_energy,
            high_freq_energy=high_freq_energy,
            jitter=jitter,
            energy_ratio_breathing=breathing_ratio,
            energy_ratio_walking=walking_ratio,
            energy_ratio_high_freq=high_freq_ratio,
            signal_strength=signal_strength,
        )

    def _estimate_high_freq_energy(self, features: SignalFeatures) -> float:
        """Estimate high frequency energy from spectrum.
        
        Args:
            features: Signal features
        
        Returns:
            High frequency energy estimate
        """
        # Use dominant frequency magnitude as proxy for high freq energy
        # This is a simplified estimation
        return features.dominant_frequency_magnitude * 0.1

    def _classify_activity(self, features: ActivityFeatures) -> str:
        """Classify activity based on features.
        
        Args:
            features: Activity features
        
        Returns:
            Activity label
        """
        # Use energy ratios for classification (more discriminative)
        breathing_ratio = features.energy_ratio_breathing
        walking_ratio = features.energy_ratio_walking
        high_freq_ratio = features.energy_ratio_high_freq
        jitter = features.jitter
        
        # Simple rule-based classification
        # 1. Check for gesture (high high-frequency energy)
        if high_freq_ratio > 0.3 and jitter > 0.05:
            return 'gesture'
        
        # 2. Check for walking (high walking energy, moderate jitter)
        if walking_ratio > 0.4 and jitter > 0.02:
            return 'walking'
        
        # 3. Check for still (very low jitter, low walking energy)
        if jitter < 0.005 and walking_ratio < 0.4:
            return 'still'
        
        # 4. Check for breathing (high breathing energy, low jitter)
        if breathing_ratio > 0.4 and jitter < 0.05:
            return 'breathing'
        
        # 5. Fallback to breathing (most common stationary activity)
        return 'breathing'

    def _calculate_activity_score(
        self,
        features: ActivityFeatures,
        thresholds: dict[str, Any],
    ) -> float:
        """Calculate activity classification score.
        
        Args:
            features: Activity features
            thresholds: Activity thresholds
        
        Returns:
            Score from 0 to 1
        """
        score = 0.0
        
        # Get optimal energy values
        opt_breathing = thresholds.get('optimal_breathing_energy', 0.5)
        opt_walking = thresholds.get('optimal_walking_energy', 0.5)
        opt_high_freq = thresholds.get('optimal_high_freq_energy', 0.5)
        
        # Use energy ratios for scoring (more discriminative)
        # This makes the scoring more robust to absolute energy scales
        breathing_ratio = features.energy_ratio_breathing
        walking_ratio = features.energy_ratio_walking
        high_freq_ratio = features.energy_ratio_high_freq
        
        # Breathing energy score - weighted more heavily
        # Score is high when breathing ratio is high (for breathing/still)
        # and low when walking ratio is high (for walking/gesture)
        breathing_score = self._calculate_ratio_score(
            breathing_ratio,
            thresholds.get('min_breathing_ratio', 0.01),
            thresholds.get('optimal_breathing_ratio', 0.5),
        )
        score += 0.4 * breathing_score
        
        # Walking energy score - weighted more heavily
        walking_score = self._calculate_ratio_score(
            walking_ratio,
            thresholds.get('min_walking_ratio', 0.01),
            thresholds.get('optimal_walking_ratio', 0.5),
        )
        score += 0.4 * walking_score
        
        # High frequency energy score
        high_freq_score = self._calculate_ratio_score(
            high_freq_ratio,
            thresholds.get('min_high_freq_ratio', 0.01),
            thresholds.get('optimal_high_freq_ratio', 0.5),
        )
        score += 0.1 * high_freq_score
        
        # Jitter score - lighter weight
        jitter_score = self._calculate_jitter_score(
            features.jitter,
            thresholds['min_jitter'],
            thresholds['max_jitter'],
        )
        score += 0.1 * jitter_score
        
        return min(score, 1.0)

    def _calculate_ratio_score(
        self,
        ratio: float,
        min_ratio: float,
        optimal_ratio: float,
    ) -> float:
        """Calculate ratio-based score.
        
        Args:
            ratio: Measured energy ratio
            min_ratio: Minimum required ratio
            optimal_ratio: Optimal ratio
        
        Returns:
            Score from 0 to 1
        """
        if ratio <= 0:
            return 0.0
        
        # Score is based on how well ratio aligns with optimal
        if ratio >= optimal_ratio:
            return 1.0
        
        # Linear interpolation between min and optimal
        if min_ratio >= optimal_ratio:
            return 0.5
        
        return (ratio - min_ratio) / (optimal_ratio - min_ratio)

    def _calculate_energy_score(
        self,
        energy: float,
        min_energy: float,
        optimal_energy: float,
    ) -> float:
        """Calculate energy-based score.
        
        Args:
            energy: Measured energy
            min_energy: Minimum required energy
            optimal_energy: Optimal energy level
        
        Returns:
            Score from 0 to 1
        """
        # Use relative energy (ratio) for scoring
        # This makes the scoring more robust to absolute energy scales
        if energy <= 0:
            return 0.0
        
        # Score is based on how well energy aligns with optimal
        # Higher energy than optimal is still good (saturated)
        if energy >= optimal_energy:
            return 1.0
        
        # Linear interpolation between min and optimal
        if min_energy >= optimal_energy:
            return 0.5
        
        return (energy - min_energy) / (optimal_energy - min_energy)

    def _calculate_jitter_score(
        self,
        jitter: float,
        min_jitter: float,
        max_jitter: float,
    ) -> float:
        """Calculate jitter-based score.
        
        Args:
            jitter: Measured jitter
            min_jitter: Minimum required jitter
            max_jitter: Maximum allowed jitter
        
        Returns:
            Score from 0 to 1
        """
        if jitter < min_jitter or jitter > max_jitter:
            return 0.0
        
        # Score is 1 when jitter is at the optimal point (closer to min for still/breathing)
        # For activities with low jitter (still, breathing), optimal is near min_jitter
        # For activities with high jitter (walking, gesture), optimal is near max_jitter
        
        # Calculate position in range (0 = min, 1 = max)
        position = (jitter - min_jitter) / (max_jitter - min_jitter) if (max_jitter > min_jitter) else 0.5
        
        # For still/breathing (low jitter), we want jitter close to min
        # For walking/gesture (high jitter), we want jitter close to max
        # Use a simple linear score that peaks at the expected position
        
        # For now, use a simple approach: score is 1 when jitter is optimal
        # Optimal is at 25% of range for still/breathing, 75% for walking/gesture
        
        if jitter <= min_jitter * 1.5:  # Very close to minimum
            return 1.0
        elif jitter >= max_jitter * 0.75:  # Close to maximum
            return 1.0
        else:
            # Decay from optimal points
            return 0.5

    def add_event_callback(self, callback: callable) -> None:
        """Add an event callback.
        
        Args:
            callback: Function to call on activity change events
        """
        self.event_callbacks.append(callback)

    def remove_event_callback(self, callback: callable) -> None:
        """Remove an event callback.
        
        Args:
            callback: Function to remove
        """
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)

    def get_person_activity(self, person_id: int) -> Optional[str]:
        """Get the current activity for a person.
        
        Args:
            person_id: Person ID
        
        Returns:
            Current activity or None if not tracked
        """
        if person_id not in self.person_states:
            return None
        return self.person_states[person_id].activity

    def get_all_person_states(self) -> dict[int, ActivityState]:
        """Get all person activity states.
        
        Returns:
            Dictionary mapping person IDs to ActivityState
        """
        return self.person_states.copy()

    def reset(self) -> None:
        """Reset the activity recognizer state."""
        self.person_states = {}
        self.last_activity_times = {}
        self.event_counter = 0
        self.event_callbacks = []
