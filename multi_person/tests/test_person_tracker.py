"""Tests for the person tracker module."""

import pytest
import numpy as np
import time
from multi_person.modules.person_tracker import PersonTracker, TrackedPerson
from multi_person.core.models import PersonState, PersonStateEvent


class TestPersonTrackerInitialization:
    """Tests for PersonTracker initialization."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        tracker = PersonTracker()
        
        assert len(tracker.tracked_persons) == 0
        assert tracker.next_person_id == 1
        assert tracker.exit_timeout_seconds == 30.0
        assert tracker.min_confidence == 0.5
        assert len(tracker.event_callbacks) == 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        tracker = PersonTracker(
            exit_timeout_seconds=60.0,
            min_confidence=0.7,
        )
        
        assert tracker.exit_timeout_seconds == 60.0
        assert tracker.min_confidence == 0.7

    def test_init_with_dependencies(self):
        """Test initialization with custom dependencies."""
        from multi_person.modules.signal_processor import SignalProcessor
        from multi_person.modules.signal_separator import SignalSeparator
        from multi_person.modules.position_estimator import PositionEstimator
        from multi_person.modules.activity_recognizer import ActivityRecognizer
        
        tracker = PersonTracker(
            signal_processor=SignalProcessor(),
            signal_separator=SignalSeparator(),
            position_estimator=PositionEstimator(),
            activity_recognizer=ActivityRecognizer(),
        )
        
        assert tracker.signal_processor is not None
        assert tracker.signal_separator is not None
        assert tracker.position_estimator is not None
        assert tracker.activity_recognizer is not None


class TestPersonIdLifecycle:
    """Tests for person ID lifecycle management."""

    def test_get_or_create_person_id_first_call(self):
        """Test getting or creating person ID for first detection."""
        tracker = PersonTracker()
        
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        
        person_id = tracker.get_or_create_person_id(signature)
        
        assert person_id == 1
        assert person_id in tracker.tracked_persons
        assert tracker.tracked_persons[person_id].confidence == 0.9

    def test_get_or_create_person_id_same_person(self):
        """Test getting same person ID for consistent detection."""
        tracker = PersonTracker()
        
        # First detection
        signature1 = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id1 = tracker.get_or_create_person_id(signature1)
        
        # Second detection (same person, similar signature)
        signature2 = {
            'signal_strength': -69.0,  # Slightly different
            'confidence': 0.95,
        }
        person_id2 = tracker.get_or_create_person_id(signature2)
        
        # Should get same ID (matched)
        assert person_id1 == person_id2

    def test_get_or_create_person_id_new_person(self):
        """Test getting new person ID for new detection."""
        tracker = PersonTracker()
        
        # First person
        signature1 = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id1 = tracker.get_or_create_person_id(signature1)
        
        # Second person (very different position)
        signature2 = {
            'signal_strength': -80.0,
            'confidence': 0.8,
        }
        person_id2 = tracker.get_or_create_person_id(signature2, position=(10.0, 20.0))
        
        # Should get different ID
        assert person_id2 == person_id1 + 1

    def test_release_person_id(self):
        """Test releasing a person ID."""
        tracker = PersonTracker()
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Release the ID
        result = tracker.release_person_id(person_id)
        
        assert result is True
        assert person_id not in tracker.tracked_persons

    def test_release_nonexistent_person_id(self):
        """Test releasing a non-existent person ID."""
        tracker = PersonTracker()
        
        result = tracker.release_person_id(999)
        
        assert result is False

    def test_get_person_count(self):
        """Test getting person count."""
        tracker = PersonTracker()
        
        # No persons initially
        assert tracker.get_person_count() == 0
        
        # Add a person
        signature1 = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        tracker.get_or_create_person_id(signature1)
        
        assert tracker.get_person_count() == 1
        
        # Add another person with different signature (not just position)
        signature2 = {
            'signal_strength': -80.0,  # Different signal strength
            'confidence': 0.8,
        }
        tracker.get_or_create_person_id(signature2, position=(5.0, 5.0))
        
        assert tracker.get_person_count() == 2

    def test_reset(self):
        """Test resetting the tracker."""
        tracker = PersonTracker()
        
        # Add some persons
        for i in range(3):
            signature = {
                'signal_strength': -70.0 + i,
                'confidence': 0.9,
            }
            tracker.get_or_create_person_id(signature)
        
        # Reset
        tracker.reset()
        
        assert len(tracker.tracked_persons) == 0
        assert tracker.next_person_id == 1
        assert tracker.total_entries == 0
        assert tracker.total_exits == 0


class TestPersonTracking:
    """Tests for person tracking functionality."""

    def test_track_persons_basic(self):
        """Test basic person tracking."""
        tracker = PersonTracker()
        
        positions = [(1.0, 2.0), (3.0, 4.0)]
        activities = ['standing', 'walking']
        
        result = tracker.track_persons(positions, activities)
        
        assert len(result) == 2
        assert 1 in result
        assert 2 in result
        assert result[1]['position'] == (1.0, 2.0)
        assert result[1]['activity'] == 'standing'
        assert result[2]['position'] == (3.0, 4.0)
        assert result[2]['activity'] == 'walking'

    def test_track_persons_consistent_across_frames(self):
        """Test that persons maintain IDs across frames."""
        tracker = PersonTracker()
        
        # Frame 1
        positions1 = [(1.0, 2.0), (3.0, 4.0)]
        activities1 = ['standing', 'walking']
        result1 = tracker.track_persons(positions1, activities1)
        
        id1_frame1 = result1[1]['person_id']
        id2_frame1 = result1[2]['person_id']
        
        # Frame 2 - same persons, slightly moved
        positions2 = [(1.1, 2.1), (3.1, 4.1)]
        activities2 = ['standing', 'walking']
        result2 = tracker.track_persons(positions2, activities2)
        
        # Should have same IDs
        assert result2[id1_frame1]['position'] == (1.1, 2.1)
        assert result2[id2_frame1]['position'] == (3.1, 4.1)

    def test_track_persons_new_person_in_frame(self):
        """Test new person getting new ID in frame."""
        tracker = PersonTracker()
        
        # Frame 1: One person
        positions1 = [(1.0, 2.0)]
        activities1 = ['standing']
        result1 = tracker.track_persons(positions1, activities1)
        
        id1_frame1 = list(result1.keys())[0]
        
        # Frame 2: Same person + new person
        positions2 = [(1.1, 2.1), (10.0, 20.0)]
        activities2 = ['standing', 'walking']
        result2 = tracker.track_persons(positions2, activities2)
        
        # Should have 2 persons
        assert len(result2) == 2
        
        # One should have same ID, one new
        ids = list(result2.keys())
        assert id1_frame1 in ids

    def test_track_persons_empty(self):
        """Test tracking with empty inputs."""
        tracker = PersonTracker()
        
        result = tracker.track_persons([], [])
        
        assert result == {}

    def test_track_persons_with_signal_strengths(self):
        """Test tracking with signal strengths."""
        tracker = PersonTracker()
        
        positions = [(1.0, 2.0)]
        activities = ['standing']
        signal_strengths = [-70.0]
        
        result = tracker.track_persons(positions, activities, signal_strengths)
        
        assert len(result) == 1
        assert result[1]['signal_strength'] == -70.0

    def test_track_persons_with_confidences(self):
        """Test tracking with confidence values."""
        tracker = PersonTracker()
        
        positions = [(1.0, 2.0)]
        activities = ['standing']
        confidences = [0.95]
        
        result = tracker.track_persons(positions, activities, None, confidences)
        
        assert len(result) == 1
        assert result[1]['confidence'] == 0.95


class TestPersonStateUpdate:
    """Tests for person state update functionality."""

    def test_update_person_state_basic(self):
        """Test basic person state update."""
        tracker = PersonTracker()
        
        # Create a person first
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update state
        state = {
            'position': (2.0, 3.0),
            'activity': 'walking',
            'signal_strength': -68.0,
            'confidence': 0.95,
        }
        
        result = tracker.update_person_state(person_id, state)
        
        assert result is True
        assert tracker.tracked_persons[person_id].position == (2.0, 3.0)
        assert tracker.tracked_persons[person_id].activity == 'walking'

    def test_update_person_state_not_found(self):
        """Test updating state for non-existent person."""
        tracker = PersonTracker()
        
        state = {
            'position': (2.0, 3.0),
        }
        
        result = tracker.update_person_state(999, state)
        
        assert result is False

    def test_update_person_state_partial(self):
        """Test updating only some state fields."""
        tracker = PersonTracker()
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update only position
        state = {
            'position': (2.0, 3.0),
        }
        
        result = tracker.update_person_state(person_id, state)
        
        assert result is True
        assert tracker.tracked_persons[person_id].position == (2.0, 3.0)
        # Other fields should remain unchanged
        assert tracker.tracked_persons[person_id].activity == 'unknown'


class TestEventSystem:
    """Tests for event system."""

    def test_person_entered_event(self):
        """Test person entered event emission."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Should have received enter event
        assert len(events_received) >= 1
        assert events_received[0].event_type == 'enter'
        assert events_received[0].person_id == person_id
        assert events_received[0].new_state is not None

    def test_person_exited_event(self):
        """Test person exited event emission."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        
        # Create and release a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        tracker.release_person_id(person_id)
        
        # Should have received exit event
        assert len(events_received) >= 2  # enter + exit
        assert events_received[-1].event_type == 'exit'
        assert events_received[-1].person_id == person_id
        assert events_received[-1].old_state is not None

    def test_position_changed_event(self):
        """Test position changed event emission."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update position
        state = {
            'position': (5.0, 6.0),
        }
        tracker.update_person_state(person_id, state)
        
        # Should have received position change event
        position_events = [e for e in events_received if e.event_type == 'position_change']
        assert len(position_events) >= 1
        assert position_events[0].person_id == person_id
        assert position_events[0].old_state is not None
        assert position_events[0].new_state is not None

    def test_activity_changed_event(self):
        """Test activity changed event emission."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update activity
        state = {
            'activity': 'walking',
        }
        tracker.update_person_state(person_id, state)
        
        # Should have received activity change event
        activity_events = [e for e in events_received if e.event_type == 'activity_change']
        assert len(activity_events) >= 1
        assert activity_events[0].person_id == person_id
        assert activity_events[0].old_state is not None
        assert activity_events[0].new_state is not None

    def test_event_callback_removal(self):
        """Test removing event callbacks."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        tracker.remove_event_callback(callback)
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        tracker.get_or_create_person_id(signature)
        
        # Should not have received any events
        assert len(events_received) == 0

    def test_get_person_state(self):
        """Test getting person state."""
        tracker = PersonTracker()
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Get state
        state = tracker.get_person_state(person_id)
        
        assert state is not None
        assert state['person_id'] == person_id
        assert state['position'] is not None
        assert state['activity'] is not None

    def test_get_all_person_states(self):
        """Test getting all person states."""
        tracker = PersonTracker()
        
        # Create multiple persons with distinct signatures
        for i in range(3):
            signature = {
                'signal_strength': -70.0 + i * 5,  # Different signal strengths
                'confidence': 0.9,
            }
            tracker.get_or_create_person_id(signature, position=(float(i * 2), float(i * 2)))
        
        # Get all states
        all_states = tracker.get_all_person_states()
        
        assert len(all_states) == 3
        assert 1 in all_states
        assert 2 in all_states
        assert 3 in all_states


class TestTimeoutHandling:
    """Tests for timeout handling."""

    def test_person_exits_after_timeout(self):
        """Test that person exits after timeout period."""
        tracker = PersonTracker(exit_timeout_seconds=0.1)  # 100ms timeout
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        assert person_id in tracker.tracked_persons
        
        # Wait for timeout
        time.sleep(0.15)
        
        # Track with no detections - person should exit
        result = tracker.track_persons([], [])
        
        assert person_id not in tracker.tracked_persons

    def test_person_stays_within_timeout(self):
        """Test that person stays within timeout period."""
        tracker = PersonTracker(exit_timeout_seconds=1.0)  # 1 second timeout
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        assert person_id in tracker.tracked_persons
        
        # Track with same person (within timeout)
        time.sleep(0.1)
        positions = [(1.0, 2.0)]
        activities = ['standing']
        tracker.track_persons(positions, activities)
        
        # Person should still be tracked
        assert person_id in tracker.tracked_persons


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_person_tracking(self):
        """Test tracking a single person."""
        tracker = PersonTracker()
        
        positions = [(1.0, 2.0)]
        activities = ['standing']
        
        result = tracker.track_persons(positions, activities)
        
        assert len(result) == 1
        assert 1 in result

    def test_many_persons_tracking(self):
        """Test tracking many persons."""
        tracker = PersonTracker()
        
        positions = [(float(i), float(i)) for i in range(5)]
        activities = ['standing'] * 5
        
        result = tracker.track_persons(positions, activities)
        
        assert len(result) == 5

    def test_person_with_zero_confidence(self):
        """Test person with zero confidence."""
        tracker = PersonTracker()
        
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.0,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        assert person_id == 1
        assert tracker.tracked_persons[person_id].confidence == 0.0

    def test_position_update_with_small_change(self):
        """Test position update with small change."""
        tracker = PersonTracker()
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update with very small position change
        state = {
            'position': (1.001, 2.001),  # Very small change
        }
        tracker.update_person_state(person_id, state)
        
        # Position should be updated
        assert tracker.tracked_persons[person_id].position == (1.001, 2.001)

    def test_activity_update_same_activity(self):
        """Test activity update with same activity."""
        tracker = PersonTracker()
        
        # Create a person
        signature = {
            'signal_strength': -70.0,
            'confidence': 0.9,
        }
        person_id = tracker.get_or_create_person_id(signature)
        
        # Update with same activity
        state = {
            'activity': 'unknown',  # Same as initial
        }
        tracker.update_person_state(person_id, state)
        
        # Should not emit activity change event
        # (no assertion here, just checking it doesn't crash)


class TestIntegration:
    """Integration tests for person tracker."""

    def test_full_tracking_pipeline(self):
        """Test complete tracking pipeline."""
        tracker = PersonTracker()
        events_received = []
        
        def callback(event):
            events_received.append(event)
        
        tracker.add_event_callback(callback)
        
        # Frame 1: Person enters
        positions1 = [(1.0, 2.0)]
        activities1 = ['standing']
        result1 = tracker.track_persons(positions1, activities1)
        
        assert len(result1) == 1
        person_id = list(result1.keys())[0]
        
        # Frame 2: Person moves
        positions2 = [(1.5, 2.5)]
        activities2 = ['walking']
        result2 = tracker.track_persons(positions2, activities2)
        
        assert len(result2) == 1
        assert result2[person_id]['position'] == (1.5, 2.5)
        assert result2[person_id]['activity'] == 'walking'
        
        # Frame 3: Person exits (no detection)
        time.sleep(0.01)
        result3 = tracker.track_persons([], [])
        
        # Person should have exited
        assert person_id not in result3

    def test_multiple_persons_with_state_updates(self):
        """Test multiple persons with state updates."""
        tracker = PersonTracker()
        
        # Create multiple persons with distinct signatures
        for i in range(3):
            signature = {
                'signal_strength': -70.0 + i * 5,  # Different signal strengths
                'confidence': 0.9,
            }
            tracker.get_or_create_person_id(signature, position=(float(i * 2), float(i * 2)))
        
        # Update states
        for person_id in [1, 2, 3]:
            state = {
                'position': (float(person_id * 2), float(person_id * 2)),
                'activity': 'walking',
            }
            tracker.update_person_state(person_id, state)
        
        # Verify all states updated
        for person_id in [1, 2, 3]:
            state = tracker.get_person_state(person_id)
            assert state is not None
            assert state['position'] == (float(person_id * 2), float(person_id * 2))
            assert state['activity'] == 'walking'

    def test_mixed_operations(self):
        """Test mixed operations (create, update, release)."""
        tracker = PersonTracker()
        
        # Create persons with distinct signatures
        id1 = tracker.get_or_create_person_id({'signal_strength': -70.0})
        id2 = tracker.get_or_create_person_id({'signal_strength': -75.0}, position=(5.0, 5.0))
        
        assert tracker.get_person_count() == 2
        
        # Update one person
        tracker.update_person_state(id1, {'position': (5.0, 5.0)})
        
        # Release one person
        result = tracker.release_person_id(id2)
        assert result is True
        
        assert tracker.get_person_count() == 1
        assert id1 in tracker.tracked_persons
        assert id2 not in tracker.tracked_persons


class TestMatchScoring:
    """Tests for match scoring logic."""

    def test_position_match_score(self):
        """Test position-based match scoring."""
        tracker = PersonTracker()
        
        # Create a person
        person = TrackedPerson(
            person_id=1,
            position=(1.0, 2.0),
            activity='standing',
            signal_strength=-70.0,
            confidence=0.9,
            entry_time=time.time(),
            last_seen_time=time.time(),
        )
        
        # Close position - high score
        score_close = tracker._calculate_match_score(
            person, (1.1, 2.1), 'standing', -70.0
        )
        
        # Far position - low score
        score_far = tracker._calculate_match_score(
            person, (10.0, 20.0), 'standing', -70.0
        )
        
        assert score_close > score_far

    def test_activity_match_score(self):
        """Test activity-based match scoring."""
        tracker = PersonTracker()
        
        person = TrackedPerson(
            person_id=1,
            position=(1.0, 2.0),
            activity='standing',
            signal_strength=-70.0,
            confidence=0.9,
            entry_time=time.time(),
            last_seen_time=time.time(),
        )
        
        # Same activity - higher score
        score_same = tracker._calculate_match_score(
            person, (1.0, 2.0), 'standing', -70.0
        )
        
        # Different activity - lower score
        score_diff = tracker._calculate_match_score(
            person, (1.0, 2.0), 'walking', -70.0
        )
        
        assert score_same > score_diff

    def test_signal_strength_match_score(self):
        """Test signal strength-based match scoring."""
        tracker = PersonTracker()
        
        person = TrackedPerson(
            person_id=1,
            position=(1.0, 2.0),
            activity='standing',
            signal_strength=-70.0,
            confidence=0.9,
            entry_time=time.time(),
            last_seen_time=time.time(),
        )
        
        # Similar strength - higher score
        score_similar = tracker._calculate_match_score(
            person, (1.0, 2.0), 'standing', -69.0
        )
        
        # Very different strength - lower score
        score_different = tracker._calculate_match_score(
            person, (1.0, 2.0), 'standing', -90.0
        )
        
        assert score_similar > score_different
