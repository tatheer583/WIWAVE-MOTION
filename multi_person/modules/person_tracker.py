"""Person tracker module for multi-person detection.

This module provides person tracking capabilities for maintaining consistent
person IDs across frames, tracking person states, and managing entry/exit events.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
import time

from multi_person.core.models import PersonState, PersonStateEvent
from multi_person.core.interfaces import PersonTrackerInterface
from multi_person.modules.activity_recognizer import ActivityRecognizer
from multi_person.modules.position_estimator import PositionEstimator
from multi_person.modules.signal_processor import SignalProcessor
from multi_person.modules.signal_separator import SignalSeparator


@dataclass
class TrackedPerson:
    """Represents a tracked person with their state and metadata."""
    person_id: int
    position: tuple[float, float]
    activity: str
    signal_strength: float
    confidence: float
    entry_time: float
    last_seen_time: float
    position_history: list[tuple[float, float, float]] = field(default_factory=list)
    activity_history: list[tuple[str, float]] = field(default_factory=list)
    exit_timeout: float = 30.0  # 30 seconds timeout before releasing ID


class PersonTracker(PersonTrackerInterface):
    """Person tracker for multi-person detection.
    
    This class implements person tracking algorithms for:
    - Maintaining consistent person IDs across frames
    - Tracking person states (position, activity, confidence)
    - Managing entry/exit events with timeout-based ID release
    - Emitting state change events
    """

    def __init__(
        self,
        signal_processor: Optional[SignalProcessor] = None,
        signal_separator: Optional[SignalSeparator] = None,
        position_estimator: Optional[PositionEstimator] = None,
        activity_recognizer: Optional[ActivityRecognizer] = None,
        exit_timeout_seconds: float = 30.0,
        min_confidence: float = 0.5,
    ):
        """Initialize the person tracker.
        
        Args:
            signal_processor: SignalProcessor instance for signal processing
            signal_separator: SignalSeparator instance for signal separation
            position_estimator: PositionEstimator instance for position estimation
            activity_recognizer: ActivityRecognizer instance for activity recognition
            exit_timeout_seconds: Seconds before releasing person IDs after last seen
            min_confidence: Minimum confidence for tracking a person
        """
        self.signal_processor = signal_processor or SignalProcessor()
        self.signal_separator = signal_separator or SignalSeparator()
        self.position_estimator = position_estimator or PositionEstimator()
        self.activity_recognizer = activity_recognizer or ActivityRecognizer()
        
        self.exit_timeout_seconds = exit_timeout_seconds
        self.min_confidence = min_confidence
        
        # Tracked persons state
        self.tracked_persons: dict[int, TrackedPerson] = {}
        self.next_person_id: int = 1
        
        # Event system
        self.event_callbacks: list[callable] = []
        self.event_counter: int = 0
        
        # Statistics
        self.total_entries: int = 0
        self.total_exits: int = 0

    def track_persons(
        self,
        current_positions: list[tuple[float, float]],
        current_activities: list[str],
        current_signal_strengths: Optional[list[float]] = None,
        current_confidences: Optional[list[float]] = None,
    ) -> dict[int, dict[str, Any]]:
        """Track persons across frames.
        
        Matches detected persons with existing tracked persons based on
        position, activity, and signal characteristics. Creates new tracked
        persons for new detections.
        
        Args:
            current_positions: Current positions of all detected persons
            current_activities: Current activities of all detected persons
            current_signal_strengths: Optional signal strengths for each person
            current_confidences: Optional confidence values for each person
            
        Returns:
            Dictionary mapping person IDs to their state information
        """
        current_time = time.time()
        
        if current_signal_strengths is None:
            current_signal_strengths = [-70.0] * len(current_positions)
            
        if current_confidences is None:
            current_confidences = [1.0] * len(current_positions)
        
        # Get existing tracked persons (not expired)
        existing_persons = [
            person for person in self.tracked_persons.values()
            if current_time - person.last_seen_time < person.exit_timeout
        ]
        
        # Match new detections to existing persons
        matched_existing = set()
        new_tracked_persons: list[TrackedPerson] = []
        
        for i, (position, activity) in enumerate(zip(current_positions, current_activities)):
            signal_strength = current_signal_strengths[i] if i < len(current_signal_strengths) else -70.0
            confidence = current_confidences[i] if i < len(current_confidences) else 1.0
            
            # Find best match among existing persons
            best_match_idx = -1
            best_score = -float('inf')
            
            for idx, person in enumerate(existing_persons):
                if idx in matched_existing:
                    continue
                
                score = self._calculate_match_score(
                    person, position, activity, signal_strength
                )
                
                if score > best_score:
                    best_score = score
                    best_match_idx = idx
            
            if best_match_idx >= 0 and best_score > 0.3:
                # Match found - update existing person
                person = existing_persons[best_match_idx]
                person.position = position
                person.activity = activity
                person.signal_strength = signal_strength
                person.confidence = max(person.confidence, confidence)
                person.last_seen_time = current_time
                
                # Update history
                person.position_history.append((position[0], position[1], current_time))
                person.activity_history.append((activity, current_time))
                
                # Keep history limited
                if len(person.position_history) > 100:
                    person.position_history = person.position_history[-100:]
                if len(person.activity_history) > 100:
                    person.activity_history = person.activity_history[-100:]
                
                new_tracked_persons.append(person)
                matched_existing.add(best_match_idx)
            else:
                # No match - create new tracked person
                person = TrackedPerson(
                    person_id=self._get_next_person_id(),
                    position=position,
                    activity=activity,
                    signal_strength=signal_strength,
                    confidence=confidence,
                    entry_time=current_time,
                    last_seen_time=current_time,
                    exit_timeout=self.exit_timeout_seconds,
                )
                person.position_history.append((position[0], position[1], current_time))
                person.activity_history.append((activity, current_time))
                
                new_tracked_persons.append(person)
                
                # Emit entry event
                self._emit_person_entered(person)
                self.total_entries += 1
        
        # Update tracked persons
        self.tracked_persons = {
            person.person_id: person for person in new_tracked_persons
        }
        
        # Check for exits (persons not seen in current frame)
        for idx, person in enumerate(existing_persons):
            if idx not in matched_existing:
                # Person not in current frame, check if timeout expired
                time_since_seen = current_time - person.last_seen_time
                if time_since_seen > person.exit_timeout:
                    # Emit exit event
                    self._emit_person_exited(person)
                    self.total_exits += 1
                    # Remove from tracking
                    if person.person_id in self.tracked_persons:
                        del self.tracked_persons[person.person_id]
        
        # Build result dictionary
        result = {}
        for person in self.tracked_persons.values():
            result[person.person_id] = {
                'person_id': person.person_id,
                'position': person.position,
                'activity': person.activity,
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
                'entry_time': person.entry_time,
                'last_seen_time': person.last_seen_time,
                'position_history': person.position_history[-10:],  # Last 10 positions
                'activity_history': person.activity_history[-10:],  # Last 10 activities
            }
        
        return result

    def get_or_create_person_id(
        self,
        signature: dict[str, Any],
        position: Optional[tuple[float, float]] = None,
        activity: Optional[str] = None,
    ) -> int:
        """Get existing person ID or create new one.
        
        Uses signature matching to find existing persons or creates a new ID.
        
        Args:
            signature: Person signature dictionary with signal characteristics
            position: Optional position override
            activity: Optional activity override
            
        Returns:
            Person ID (existing or newly created)
        """
        current_time = time.time()
        
        # Extract signature features
        signal_strength = signature.get('signal_strength', -70.0)
        confidence = signature.get('confidence', 1.0)
        velocity = signature.get('velocity')
        
        # Get existing tracked persons
        existing_persons = list(self.tracked_persons.values())
        
        # Find best match
        best_match_idx = -1
        best_score = -float('inf')
        
        for idx, person in enumerate(existing_persons):
            score = self._calculate_signature_match_score(
                person, signature, position, activity
            )
            
            if score > best_score:
                best_score = score
                best_match_idx = idx
        
        if best_match_idx >= 0 and best_score > 0.6:
            # Match found - return existing ID
            person = existing_persons[best_match_idx]
            person.last_seen_time = current_time
            
            # Update if new position/activity provided
            if position is not None:
                person.position = position
            if activity is not None:
                person.activity = activity
            
            return person.person_id
        else:
            # No match - create new person
            person_id = self._get_next_person_id()
            
            person = TrackedPerson(
                person_id=person_id,
                position=position or (0.0, 0.0),
                activity=activity or 'unknown',
                signal_strength=signal_strength,
                confidence=confidence,
                entry_time=current_time,
                last_seen_time=current_time,
                exit_timeout=self.exit_timeout_seconds,
            )
            
            self.tracked_persons[person_id] = person
            
            # Emit entry event
            self._emit_person_entered(person)
            self.total_entries += 1
            
            return person_id

    def update_person_state(
        self,
        person_id: int,
        state: dict[str, Any],
    ) -> bool:
        """Update person state.
        
        Args:
            person_id: Person ID to update
            state: State dictionary with position, activity, etc.
            
        Returns:
            True if update successful, False if person not found
        """
        if person_id not in self.tracked_persons:
            return False
        
        person = self.tracked_persons[person_id]
        current_time = time.time()
        
        # Update position if provided
        if 'position' in state:
            old_position = person.position
            person.position = state['position']
            
            # Emit position change event if position changed significantly
            if self._positions_different(old_position, state['position']):
                self._emit_position_changed(person, old_position, state['position'])
        
        # Update activity if provided
        if 'activity' in state:
            old_activity = person.activity
            person.activity = state['activity']
            
            # Emit activity change event if activity changed
            if old_activity != state['activity']:
                self._emit_activity_changed(person, old_activity, state['activity'])
        
        # Update signal strength if provided
        if 'signal_strength' in state:
            person.signal_strength = state['signal_strength']
        
        # Update confidence if provided
        if 'confidence' in state:
            person.confidence = max(person.confidence, state['confidence'])
        
        # Update last seen time
        person.last_seen_time = current_time
        
        # Update history
        if 'position' in state:
            person.position_history.append((
                state['position'][0],
                state['position'][1],
                current_time
            ))
        if 'activity' in state:
            person.activity_history.append((state['activity'], current_time))
        
        # Keep history limited
        if len(person.position_history) > 100:
            person.position_history = person.position_history[-100:]
        if len(person.activity_history) > 100:
            person.activity_history = person.activity_history[-100:]
        
        return True

    def release_person_id(self, person_id: int) -> bool:
        """Release person ID after timeout.
        
        Args:
            person_id: Person ID to release
            
        Returns:
            True if ID was released, False if not found
        """
        if person_id not in self.tracked_persons:
            return False
        
        person = self.tracked_persons[person_id]
        
        # Emit exit event
        self._emit_person_exited(person)
        self.total_exits += 1
        
        # Remove from tracking
        del self.tracked_persons[person_id]
        
        return True

    def get_person_count(self) -> int:
        """Get current number of tracked persons.
        
        Returns:
            Number of tracked persons
        """
        return len(self.tracked_persons)

    def get_person_state(self, person_id: int) -> Optional[dict[str, Any]]:
        """Get current state of a person.
        
        Args:
            person_id: Person ID to look up
            
        Returns:
            Person state dictionary or None if not found
        """
        if person_id not in self.tracked_persons:
            return None
        
        person = self.tracked_persons[person_id]
        
        return {
            'person_id': person.person_id,
            'position': person.position,
            'activity': person.activity,
            'signal_strength': person.signal_strength,
            'confidence': person.confidence,
            'entry_time': person.entry_time,
            'last_seen_time': person.last_seen_time,
            'position_history': person.position_history,
            'activity_history': person.activity_history,
        }

    def get_all_person_states(self) -> dict[int, dict[str, Any]]:
        """Get states of all tracked persons.
        
        Returns:
            Dictionary mapping person IDs to their states
        """
        return {
            person_id: self.get_person_state(person_id)
            for person_id in self.tracked_persons.keys()
        }

    def add_event_callback(self, callback: callable) -> None:
        """Add an event callback.
        
        Args:
            callback: Function to call on events
        """
        self.event_callbacks.append(callback)

    def remove_event_callback(self, callback: callable) -> None:
        """Remove an event callback.
        
        Args:
            callback: Function to remove
        """
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)

    def reset(self) -> None:
        """Reset the person tracker state."""
        self.tracked_persons = {}
        self.next_person_id = 1
        self.event_counter = 0
        self.event_callbacks = []
        self.total_entries = 0
        self.total_exits = 0

    def _get_next_person_id(self) -> int:
        """Get the next available person ID.
        
        Returns:
            Person ID
        """
        person_id = self.next_person_id
        self.next_person_id += 1
        return person_id

    def _calculate_match_score(
        self,
        person: TrackedPerson,
        new_position: tuple[float, float],
        new_activity: str,
        new_signal_strength: float,
    ) -> float:
        """Calculate match score between existing person and new detection.
        
        Args:
            person: Existing tracked person
            new_position: New position to match
            new_activity: New activity to match
            new_signal_strength: New signal strength to match
            
        Returns:
            Match score (0-1)
        """
        # Position score (inverse distance)
        old_position = person.position
        distance = np.sqrt(
            (new_position[0] - old_position[0]) ** 2 +
            (new_position[1] - old_position[1]) ** 2
        )
        
        # Score decreases with distance (max 10 meters for reasonable match)
        position_score = np.exp(-distance / 5.0)
        
        # Activity score
        activity_score = 1.0 if new_activity == person.activity else 0.5
        
        # Signal strength score
        strength_diff = abs(new_signal_strength - person.signal_strength)
        strength_score = np.exp(-strength_diff / 20.0)
        
        # Combined score
        combined = (
            0.4 * position_score +
            0.35 * activity_score +
            0.25 * strength_score
        )
        
        return float(combined)

    def _calculate_signature_match_score(
        self,
        person: TrackedPerson,
        signature: dict[str, Any],
        position: Optional[tuple[float, float]],
        activity: Optional[str],
    ) -> float:
        """Calculate match score between person and signature.
        
        Args:
            person: Existing tracked person
            signature: Person signature dictionary
            position: Optional position override
            activity: Optional activity override
            
        Returns:
            Match score (0-1)
        """
        # Use provided values or signature values
        sig_position = position or (0.0, 0.0)
        sig_activity = activity or 'unknown'
        sig_strength = signature.get('signal_strength', -70.0)
        
        # Position score - only use if position is provided and not default
        if sig_position != (0.0, 0.0):
            old_position = person.position
            distance = np.sqrt(
                (sig_position[0] - old_position[0]) ** 2 +
                (sig_position[1] - old_position[1]) ** 2
            )
            # Use a smaller distance threshold for better discrimination
            position_score = np.exp(-distance / 3.0)
        else:
            position_score = 0.5  # Neutral if no position provided
        
        # Activity score
        activity_score = 1.0 if sig_activity == person.activity else 0.5
        
        # Signal strength score
        strength_diff = abs(sig_strength - person.signal_strength)
        # Use a smaller threshold for signal strength discrimination
        strength_score = np.exp(-strength_diff / 10.0)
        
        # Combined score - weight position higher when provided
        if sig_position != (0.0, 0.0):
            combined = (
                0.5 * position_score +
                0.25 * activity_score +
                0.25 * strength_score
            )
        else:
            combined = (
                0.3 * position_score +
                0.35 * activity_score +
                0.35 * strength_score
            )
        
        return float(combined)

    def _positions_different(
        self,
        pos1: tuple[float, float],
        pos2: tuple[float, float],
        threshold: float = 0.1,
    ) -> bool:
        """Check if two positions are significantly different.
        
        Args:
            pos1: First position
            pos2: Second position
            threshold: Minimum distance difference
            
        Returns:
            True if positions are different
        """
        distance = np.sqrt(
            (pos2[0] - pos1[0]) ** 2 +
            (pos2[1] - pos1[1]) ** 2
        )
        return distance > threshold

    def _emit_person_entered(self, person: TrackedPerson) -> None:
        """Emit person entered event.
        
        Args:
            person: Tracked person who entered
        """
        current_time = time.time()
        
        new_state = PersonState(
            person_id=person.person_id,
            position=person.position,
            activity=person.activity,
            timestamp=current_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        self.event_counter += 1
        event = PersonStateEvent(
            event_id=self.event_counter,
            person_id=person.person_id,
            event_type='enter',
            timestamp=current_time,
            old_state=None,
            new_state=new_state,
        )
        
        # Call event callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception:
                # Skip failed callbacks
                pass

    def _emit_person_exited(self, person: TrackedPerson) -> None:
        """Emit person exited event.
        
        Args:
            person: Tracked person who exited
        """
        current_time = time.time()
        
        old_state = PersonState(
            person_id=person.person_id,
            position=person.position,
            activity=person.activity,
            timestamp=person.last_seen_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        self.event_counter += 1
        event = PersonStateEvent(
            event_id=self.event_counter,
            person_id=person.person_id,
            event_type='exit',
            timestamp=current_time,
            old_state=old_state,
            new_state=None,
        )
        
        # Call event callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception:
                # Skip failed callbacks
                pass

    def _emit_position_changed(
        self,
        person: TrackedPerson,
        old_position: tuple[float, float],
        new_position: tuple[float, float],
    ) -> None:
        """Emit position changed event.
        
        Args:
            person: Tracked person
            old_position: Previous position
            new_position: New position
        """
        current_time = time.time()
        
        old_state = PersonState(
            person_id=person.person_id,
            position=old_position,
            activity=person.activity,
            timestamp=current_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        new_state = PersonState(
            person_id=person.person_id,
            position=new_position,
            activity=person.activity,
            timestamp=current_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        self.event_counter += 1
        event = PersonStateEvent(
            event_id=self.event_counter,
            person_id=person.person_id,
            event_type='position_change',
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

    def _emit_activity_changed(
        self,
        person: TrackedPerson,
        old_activity: str,
        new_activity: str,
    ) -> None:
        """Emit activity changed event.
        
        Args:
            person: Tracked person
            old_activity: Previous activity
            new_activity: New activity
        """
        current_time = time.time()
        
        old_state = PersonState(
            person_id=person.person_id,
            position=person.position,
            activity=old_activity,
            timestamp=current_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        new_state = PersonState(
            person_id=person.person_id,
            position=person.position,
            activity=new_activity,
            timestamp=current_time,
            signal_features={
                'signal_strength': person.signal_strength,
                'confidence': person.confidence,
            },
            velocity=None,
            confidence=person.confidence,
        )
        
        self.event_counter += 1
        event = PersonStateEvent(
            event_id=self.event_counter,
            person_id=person.person_id,
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
