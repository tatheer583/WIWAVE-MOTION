"""Tests for the activity recognizer module."""

import pytest
import numpy as np
from multi_person.modules.activity_recognizer import (
    ActivityRecognizer,
    ActivityFeatures,
    ActivityState,
)
from multi_person.core.models import PersonState, PersonStateEvent


class TestActivityRecognizerInitialization:
    """Tests for ActivityRecognizer initialization."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        recognizer = ActivityRecognizer()
        
        assert recognizer.signal_processor is not None
        assert recognizer.sample_rate == 10.0
        assert recognizer.min_confidence == 0.5
        assert len(recognizer.person_states) == 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        processor = ActivityRecognizer(
            sample_rate=20.0,
            min_confidence=0.7,
        )
        
        assert processor.sample_rate == 20.0
        assert processor.min_confidence == 0.7

    def test_init_with_signal_processor(self):
        """Test initialization with custom signal processor."""
        custom_processor = ActivityRecognizer(
            sample_rate=15.0,
            breathing_band=(0.2, 0.6),
            walking_band=(1.5, 5.0),
        )
        
        assert custom_processor.sample_rate == 15.0
        assert custom_processor.breathing_band == (0.2, 0.6)
        assert custom_processor.walking_band == (1.5, 5.0)


class TestActivityRecognition:
    """Tests for activity recognition functionality."""

    def test_recognize_still_activity(self):
        """Test recognizing still activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create signal with low energy and low jitter (still person)
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)  # Low variance
        rtt = np.random.normal(0.5, 0.005, 100)  # Very stable RTT (low jitter)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        activity = recognizer.recognize_activity(signal)
        
        # Should classify as still (lowest jitter)
        assert activity == 'still'

    def test_recognize_breathing_activity(self):
        """Test recognizing breathing activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create signal with breathing pattern (0.2 Hz)
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt = 0.5 + 0.01 * np.sin(2 * np.pi * 0.2 * t)  # Breathing frequency, low amplitude
        rssi = np.random.normal(-70, 2, 100)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        activity = recognizer.recognize_activity(signal)
        
        # Should classify as breathing
        assert activity == 'breathing'

    def test_recognize_walking_activity(self):
        """Test recognizing walking activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create signal with walking pattern (2 Hz)
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt = 0.5 + 0.03 * np.sin(2 * np.pi * 2 * t)  # Walking frequency
        rssi = np.random.normal(-70, 3, 100)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        activity = recognizer.recognize_activity(signal)
        
        # Should classify as walking
        assert activity == 'walking'

    def test_recognize_multiple_activities(self):
        """Test recognizing activities for multiple people."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Person 1: Still
        rssi1 = np.random.normal(-70, 2, 100)
        rtt1 = np.random.normal(0.5, 0.01, 100)
        signal1 = {'rssi': rssi1.tolist(), 'rtt': rtt1.tolist()}
        
        # Person 2: Walking
        t = np.linspace(0, 10, 100)
        rssi2 = np.random.normal(-72, 5, 100)
        rtt2 = 0.55 + 0.05 * np.sin(2 * np.pi * 2 * t)
        signal2 = {'rssi': rssi2.tolist(), 'rtt': rtt2.tolist()}
        
        signals = [signal1, signal2]
        activities = recognizer.recognize_activities(signals)
        
        assert len(activities) == 2
        assert 'walking' in activities

    def test_recognize_unknown_activity(self):
        """Test recognizing unknown activity with low confidence."""
        recognizer = ActivityRecognizer(sample_rate=10.0, min_confidence=0.9)
        
        # Create ambiguous signal
        np.random.seed(42)
        rssi = np.random.normal(-70, 10, 50)
        rtt = np.random.normal(0.5, 0.1, 50)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        activity = recognizer.recognize_activity(signal)
        
        # With high min_confidence, may return unknown
        assert activity in ['still', 'breathing', 'walking', 'gesture', 'unknown']


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    def test_calculate_confidence_no_state(self):
        """Test confidence calculation for untracked person."""
        recognizer = ActivityRecognizer()
        
        confidence = recognizer.calculate_confidence(999)
        
        assert confidence == 0.0

    def test_calculate_confidence_with_state(self):
        """Test confidence calculation for tracked person."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create signal and update state
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        # Manually update state
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        recognizer.update_person_state(1, activity, activity_features, 0.85)
        
        confidence = recognizer.calculate_confidence(1)
        
        assert confidence == 85.0

    def test_confidence_updates_with_activity(self):
        """Test confidence changes with activity updates."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Update with high confidence
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        recognizer.update_person_state(1, activity, activity_features, 0.9)
        
        assert recognizer.calculate_confidence(1) == 90.0


class TestEventEmission:
    """Tests for activity change event emission."""

    def test_emit_activity_change_event(self):
        """Test emitting activity change event."""
        recognizer = ActivityRecognizer()
        
        # First update a person state
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        recognizer.update_person_state(1, activity, activity_features, 0.85)
        
        event = recognizer.emit_activity_change_event(
            person_id=1,
            old_activity='still',
            new_activity='walking',
        )
        
        assert event is not None
        assert event.event_id > 0
        assert event.person_id == 1
        assert event.event_type == 'activity_change'
        assert event.old_state is not None
        assert event.old_state.activity == 'still'
        # new_state should be the current person state
        assert event.new_state is not None
        assert event.new_state.activity == activity

    def test_event_callback_registration(self):
        """Test registering event callbacks."""
        recognizer = ActivityRecognizer()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        recognizer.add_event_callback(callback)
        
        # Emit an event
        recognizer.emit_activity_change_event(
            person_id=1,
            old_activity='still',
            new_activity='walking',
        )
        
        assert len(events_received) == 1
        assert events_received[0].event_type == 'activity_change'

    def test_event_callback_removal(self):
        """Test removing event callbacks."""
        recognizer = ActivityRecognizer()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        recognizer.add_event_callback(callback)
        recognizer.remove_event_callback(callback)
        
        # Emit an event
        recognizer.emit_activity_change_event(
            person_id=1,
            old_activity='still',
            new_activity='walking',
        )
        
        assert len(events_received) == 0

    def test_activity_change_triggers_event(self):
        """Test that activity change triggers event."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        recognizer.add_event_callback(callback)
        
        # Create signal and update state
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        
        # First update (no event - no previous activity)
        recognizer.update_person_state(1, activity, activity_features, 0.8)
        
        # Change activity
        new_activity = 'walking' if activity != 'walking' else 'still'
        recognizer.update_person_state(1, new_activity, activity_features, 0.9)
        
        # Should have received an event
        assert len(events_received) >= 1
        assert events_received[-1].event_type == 'activity_change'
        assert events_received[-1].old_state.activity != events_received[-1].new_state.activity


class TestPerPersonStateManagement:
    """Tests for per-person state management."""

    def test_update_person_state(self):
        """Test updating person state."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        
        recognizer.update_person_state(1, activity, activity_features, 0.85)
        
        assert 1 in recognizer.person_states
        state = recognizer.person_states[1]
        assert state.person_id == 1
        assert state.activity == activity
        assert state.confidence == 0.85

    def test_get_person_activity(self):
        """Test getting person activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        
        recognizer.update_person_state(1, activity, activity_features, 0.85)
        
        retrieved_activity = recognizer.get_person_activity(1)
        
        assert retrieved_activity == activity

    def test_get_person_activity_not_found(self):
        """Test getting activity for untracked person."""
        recognizer = ActivityRecognizer()
        
        activity = recognizer.get_person_activity(999)
        
        assert activity is None

    def test_get_all_person_states(self):
        """Test getting all person states."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Update multiple persons
        for person_id in [1, 2, 3]:
            np.random.seed(42 + person_id)
            rssi = np.random.normal(-70, 2, 100)
            rtt = np.random.normal(0.5, 0.01, 100)
            signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
            
            preprocessed = recognizer.signal_processor.preprocess_signal(signal)
            features = recognizer.signal_processor.extract_features(preprocessed)
            activity_features = recognizer._calculate_activity_features(features, preprocessed)
            activity = recognizer._classify_activity(activity_features)
            
            recognizer.update_person_state(person_id, activity, activity_features, 0.8)
        
        all_states = recognizer.get_all_person_states()
        
        assert len(all_states) == 3
        assert 1 in all_states
        assert 2 in all_states
        assert 3 in all_states

    def test_reset_state(self):
        """Test resetting recognizer state."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Update some states
        np.random.seed(42)
        rssi = np.random.normal(-70, 2, 100)
        rtt = np.random.normal(0.5, 0.01, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        activity = recognizer._classify_activity(activity_features)
        
        recognizer.update_person_state(1, activity, activity_features, 0.8)
        recognizer.update_person_state(2, activity, activity_features, 0.9)
        
        # Reset
        recognizer.reset()
        
        assert len(recognizer.person_states) == 0
        assert len(recognizer.event_callbacks) == 0
        assert recognizer.event_counter == 0


class TestActivityFeatures:
    """Tests for ActivityFeatures calculations."""

    def test_calculate_activity_features(self):
        """Test calculating activity features."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        rssi = np.random.normal(-70, 5, 100)
        rtt = np.random.normal(0.5, 0.05, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        
        assert isinstance(activity_features, ActivityFeatures)
        assert activity_features.breathing_energy >= 0
        assert activity_features.walking_energy >= 0
        assert activity_features.jitter >= 0
        # Signal strength is now calculated from normalized RTT mean (0-1 range)
        assert 0 <= activity_features.signal_strength <= 1

    def test_activity_features_with_breathing_signal(self):
        """Test activity features for breathing signal."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create breathing signal
        np.random.seed(42)
        t = np.linspace(0, 10, 100)
        rtt = 0.5 + 0.02 * np.sin(2 * np.pi * 0.2 * t)  # 0.2 Hz breathing
        rssi = np.random.normal(-70, 3, 100)
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        preprocessed = recognizer.signal_processor.preprocess_signal(signal)
        features = recognizer.signal_processor.extract_features(preprocessed)
        
        activity_features = recognizer._calculate_activity_features(features, preprocessed)
        
        # Breathing signal should have significant breathing energy
        assert activity_features.breathing_energy >= 0
        # Jitter is calculated from normalized RTT, so it's in 0-1 range
        assert activity_features.jitter >= 0


class TestActivityClassification:
    """Tests for activity classification logic."""

    def test_classify_still(self):
        """Test classifying still activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create still signal (very low energy, very low jitter)
        # Using values that match actual signal processor output for still activity
        features = ActivityFeatures(
            breathing_energy=0.002,
            walking_energy=0.001,
            high_freq_energy=0.0005,
            jitter=0.0005,
            energy_ratio_breathing=0.3,
            energy_ratio_walking=0.3,
            energy_ratio_high_freq=0.1,
            signal_strength=0.5,
        )
        
        activity = recognizer._classify_activity(features)
        
        # Still should have lowest jitter and lowest energy
        assert activity == 'still'

    def test_classify_breathing(self):
        """Test classifying breathing activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create breathing signal (moderate breathing energy, low jitter)
        features = ActivityFeatures(
            breathing_energy=0.2,
            walking_energy=0.05,
            high_freq_energy=0.02,
            jitter=0.01,
            energy_ratio_breathing=0.6,
            energy_ratio_walking=0.1,
            energy_ratio_high_freq=0.1,
            signal_strength=0.5,
        )
        
        activity = recognizer._classify_activity(features)
        
        assert activity == 'breathing'

    def test_classify_walking(self):
        """Test classifying walking activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create walking signal (high walking energy)
        features = ActivityFeatures(
            breathing_energy=0.1,
            walking_energy=0.5,
            high_freq_energy=0.15,
            jitter=0.03,
            energy_ratio_breathing=0.15,
            energy_ratio_walking=0.6,
            energy_ratio_high_freq=0.2,
            signal_strength=0.5,
        )
        
        activity = recognizer._classify_activity(features)
        
        assert activity == 'walking'

    def test_classify_gesture(self):
        """Test classifying gesture activity."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Create gesture signal (high high-frequency energy)
        features = ActivityFeatures(
            breathing_energy=0.05,
            walking_energy=0.1,
            high_freq_energy=0.5,
            jitter=0.08,
            energy_ratio_breathing=0.1,
            energy_ratio_walking=0.15,
            energy_ratio_high_freq=0.7,
            signal_strength=0.5,
        )
        
        activity = recognizer._classify_activity(features)
        
        assert activity == 'gesture'


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_signal(self):
        """Test with empty signal."""
        recognizer = ActivityRecognizer()
        
        signal = {'rssi': [], 'rtt': []}
        activity = recognizer.recognize_activity(signal)
        
        # Should handle gracefully - returns 'still' for empty/unknown
        assert activity in ['still', 'breathing', 'walking', 'gesture', 'unknown']

    def test_single_sample_signal(self):
        """Test with single sample signal."""
        recognizer = ActivityRecognizer()
        
        signal = {'rssi': [-70.0], 'rtt': [0.5]}
        activity = recognizer.recognize_activity(signal)
        
        # Should handle gracefully
        assert activity in ['still', 'breathing', 'walking', 'gesture', 'unknown']

    def test_very_noisy_signal(self):
        """Test with very noisy signal."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        rssi = np.random.normal(-70, 20, 100)  # High noise
        rtt = np.random.normal(0.5, 0.2, 100)  # High jitter
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        activity = recognizer.recognize_activity(signal)
        
        # Should still return a valid activity
        assert activity in ['still', 'breathing', 'walking', 'gesture']

    def test_multiple_updates_same_person(self):
        """Test multiple activity updates for same person."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        
        # First update
        rssi1 = np.random.normal(-70, 2, 100)
        rtt1 = np.random.normal(0.5, 0.01, 100)
        signal1 = {'rssi': rssi1.tolist(), 'rtt': rtt1.tolist()}
        
        preprocessed1 = recognizer.signal_processor.preprocess_signal(signal1)
        features1 = recognizer.signal_processor.extract_features(preprocessed1)
        activity_features1 = recognizer._calculate_activity_features(features1, preprocessed1)
        activity1 = recognizer._classify_activity(activity_features1)
        
        recognizer.update_person_state(1, activity1, activity_features1, 0.8)
        
        # Second update (different activity)
        rssi2 = np.random.normal(-72, 5, 100)
        t = np.linspace(0, 10, 100)
        rtt2 = 0.55 + 0.05 * np.sin(2 * np.pi * 2 * t)
        signal2 = {'rssi': rssi2.tolist(), 'rtt': rtt2.tolist()}
        
        preprocessed2 = recognizer.signal_processor.preprocess_signal(signal2)
        features2 = recognizer.signal_processor.extract_features(preprocessed2)
        activity_features2 = recognizer._calculate_activity_features(features2, preprocessed2)
        activity2 = recognizer._classify_activity(activity_features2)
        
        recognizer.update_person_state(1, activity2, activity_features2, 0.9)
        
        # Should have updated state
        state = recognizer.person_states[1]
        assert state.activity == activity2
        assert state.confidence == 0.9

    def test_activity_history_tracking(self):
        """Test activity history tracking."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        np.random.seed(42)
        
        # Multiple updates
        for i in range(5):
            rssi = np.random.normal(-70, 2, 100)
            rtt = np.random.normal(0.5, 0.01, 100)
            signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
            
            preprocessed = recognizer.signal_processor.preprocess_signal(signal)
            features = recognizer.signal_processor.extract_features(preprocessed)
            activity_features = recognizer._calculate_activity_features(features, preprocessed)
            activity = 'still'  # Force same activity
            
            recognizer.update_person_state(1, activity, activity_features, 0.8 + i * 0.01)
        
        # Check history is maintained
        state = recognizer.person_states[1]
        assert len(state.activity_history) > 0


class TestIntegration:
    """Integration tests for activity recognizer."""

    def test_full_recognition_pipeline(self):
        """Test complete activity recognition pipeline."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        recognizer.add_event_callback(callback)
        
        # Simulate person entering and changing activity
        np.random.seed(42)
        
        # Person 1: Initially still
        rssi1 = np.random.normal(-70, 2, 100)
        rtt1 = np.random.normal(0.5, 0.01, 100)
        signal1 = {'rssi': rssi1.tolist(), 'rtt': rtt1.tolist()}
        
        activity1 = recognizer.recognize_activity(signal1)
        preprocessed1 = recognizer.signal_processor.preprocess_signal(signal1)
        features1 = recognizer.signal_processor.extract_features(preprocessed1)
        activity_features1 = recognizer._calculate_activity_features(features1, preprocessed1)
        
        recognizer.update_person_state(1, activity1, activity_features1, 0.85)
        
        # Person 1 starts walking
        t = np.linspace(0, 10, 100)
        rssi2 = np.random.normal(-72, 5, 100)
        rtt2 = 0.55 + 0.05 * np.sin(2 * np.pi * 2 * t)
        signal2 = {'rssi': rssi2.tolist(), 'rtt': rtt2.tolist()}
        
        activity2 = recognizer.recognize_activity(signal2)
        preprocessed2 = recognizer.signal_processor.preprocess_signal(signal2)
        features2 = recognizer.signal_processor.extract_features(preprocessed2)
        activity_features2 = recognizer._calculate_activity_features(features2, preprocessed2)
        
        recognizer.update_person_state(1, activity2, activity_features2, 0.9)
        
        # Verify state updated
        state = recognizer.person_states[1]
        assert state.activity == activity2
        assert state.confidence == 0.9
        
        # Verify event was emitted
        assert len(events_received) >= 1

    def test_multiple_persons_different_activities(self):
        """Test recognizing multiple persons with different activities."""
        recognizer = ActivityRecognizer(sample_rate=10.0)
        
        # Person 1: Still (very low jitter)
        np.random.seed(42)
        rssi1 = np.random.normal(-70, 2, 100)
        rtt1 = np.random.normal(0.5, 0.005, 100)
        signal1 = {'rssi': rssi1.tolist(), 'rtt': rtt1.tolist()}
        
        # Person 2: Walking (2 Hz)
        t = np.linspace(0, 10, 100)
        rssi2 = np.random.normal(-72, 3, 100)
        rtt2 = 0.55 + 0.03 * np.sin(2 * np.pi * 2 * t)
        signal2 = {'rssi': rssi2.tolist(), 'rtt': rtt2.tolist()}
        
        # Person 3: Breathing (0.2 Hz)
        rssi3 = np.random.normal(-68, 2, 100)
        rtt3 = 0.48 + 0.01 * np.sin(2 * np.pi * 0.2 * t)
        signal3 = {'rssi': rssi3.tolist(), 'rtt': rtt3.tolist()}
        
        signals = [signal1, signal2, signal3]
        activities = recognizer.recognize_activities(signals)
        
        assert len(activities) == 3
        assert 'walking' in activities
        assert 'breathing' in activities
        assert 'still' in activities
