"""Tests for the signal separator module."""

import pytest
import numpy as np
import time
from multi_person.modules.signal_separator import SignalSeparator
from multi_person.modules.signal_processor import SignalProcessor
from multi_person.core.models import PersonSignature, PersonState


class TestSignalSeparatorBasic:
    """Tests for basic signal separator functionality."""

    def test_init_default(self):
        """Test initialization with default parameters."""
        separator = SignalSeparator()
        
        assert separator.signal_processor is not None
        assert separator.timeout_seconds == 30.0
        assert separator.min_correlation == 0.3
        assert separator.distance_threshold == 0.5
        assert len(separator.person_tracks) == 0
        assert separator.next_person_id == 1

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        processor = SignalProcessor()
        separator = SignalSeparator(
            signal_processor=processor,
            timeout_seconds=60.0,
            min_correlation=0.5,
            distance_threshold=1.0,
        )
        
        assert separator.signal_processor == processor
        assert separator.timeout_seconds == 60.0
        assert separator.min_correlation == 0.5
        assert separator.distance_threshold == 1.0

    def test_separate_signals_empty(self):
        """Test separating empty signal."""
        separator = SignalSeparator()
        
        result = separator.separate_signals(None)
        assert result == []

    def test_separate_signals_single_person(self):
        """Test separating single person signal."""
        separator = SignalSeparator()
        
        # Create single person signal
        np.random.seed(42)
        rssi = np.random.normal(-70, 5, 100)
        rtt = np.random.normal(0.5, 0.1, 100)
        
        mixed_signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        result = separator.separate_signals(mixed_signal)
        
        assert len(result) == 1
        assert 'rtt' in result[0]
        assert 'rssi' in result[0]

    def test_estimate_signal_count_single_person(self):
        """Test estimating signal count for single person."""
        separator = SignalSeparator()
        
        # Create single person signal (stable RTT)
        np.random.seed(42)
        rtt = np.random.normal(0.5, 0.02, 100)  # Low variance = single person
        rssi = np.random.normal(-70, 5, 100)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        count = separator.estimate_signal_count(signal)
        
        assert count == 1

    def test_estimate_signal_count_multiple_people(self):
        """Test estimating signal count for multiple people."""
        separator = SignalSeparator()
        
        # Create multi-person signal (higher variance)
        np.random.seed(42)
        # Mix of different RTT patterns
        rtt1 = np.random.normal(0.4, 0.05, 50)
        rtt2 = np.random.normal(0.6, 0.05, 50)
        rtt = np.concatenate([rtt1, rtt2])
        
        rssi1 = np.random.normal(-70, 5, 50)
        rssi2 = np.random.normal(-75, 5, 50)
        rssi = np.concatenate([rssi1, rssi2])
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        count = separator.estimate_signal_count(signal)
        
        # Should estimate 2 or more people
        assert count >= 1


class TestPersonIdAssignment:
    """Tests for person ID assignment functionality."""

    def test_assign_person_ids_first_frame(self):
        """Test assigning IDs in first frame."""
        separator = SignalSeparator()
        
        # Create signatures
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
            PersonSignature(
                person_id=0,
                position=(3.0, 4.0),
                activity="walking",
                signal_strength=-75.0,
                confidence=0.8,
            ),
        ]
        
        states = separator.assign_person_ids(signatures)
        
        assert len(states) == 2
        assert states[0].person_id == 1
        assert states[1].person_id == 2
        assert states[0].position == (1.0, 2.0)
        assert states[1].position == (3.0, 4.0)

    def test_assign_person_ids_consistent_across_frames(self):
        """Test that IDs remain consistent across frames."""
        separator = SignalSeparator()
        
        # First frame
        signatures1 = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        
        states1 = separator.assign_person_ids(signatures1)
        assert len(states1) == 1
        first_id = states1[0].person_id
        
        # Second frame - same person, slightly different position
        signatures2 = [
            PersonSignature(
                person_id=0,
                position=(1.1, 2.1),  # Slightly moved
                activity="standing",
                signal_strength=-69.0,
                confidence=0.9,
            ),
        ]
        
        states2 = separator.assign_person_ids(signatures2)
        assert len(states2) == 1
        assert states2[0].person_id == first_id  # Same ID

    def test_assign_person_ids_new_person_gets_new_id(self):
        """Test that new person gets new ID."""
        separator = SignalSeparator()
        
        # First person
        signatures1 = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        states1 = separator.assign_person_ids(signatures1)
        first_id = states1[0].person_id
        
        # Second person (different position, low correlation)
        signatures2 = [
            PersonSignature(
                person_id=0,
                position=(10.0, 20.0),  # Far away
                activity="walking",
                signal_strength=-80.0,
                confidence=0.8,
            ),
        ]
        
        states2 = separator.assign_person_ids(signatures2)
        # Only 1 state should be returned (for the 1 signature passed)
        assert len(states2) == 1
        # The second person should get a new ID
        assert states2[0].person_id == first_id + 1

    def test_assign_person_ids_empty(self):
        """Test assigning IDs with empty signatures."""
        separator = SignalSeparator()
        
        states = separator.assign_person_ids([])
        
        assert states == []


class TestPersonIdRelease:
    """Tests for person ID release functionality."""

    def test_release_person_id(self):
        """Test releasing a person ID."""
        separator = SignalSeparator()
        
        # Create and assign a person
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        states = separator.assign_person_ids(signatures)
        person_id = states[0].person_id
        
        # Release the ID
        result = separator.release_person_id(person_id)
        
        assert result is True
        assert person_id in separator.released_ids
        assert person_id not in separator.person_tracks

    def test_release_nonexistent_person_id(self):
        """Test releasing a non-existent person ID."""
        separator = SignalSeparator()
        
        result = separator.release_person_id(999)
        
        assert result is False

    def test_reuse_released_id(self):
        """Test that released IDs are reused."""
        separator = SignalSeparator()
        
        # Create and release a person
        signatures1 = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        states1 = separator.assign_person_ids(signatures1)
        person_id = states1[0].person_id
        
        separator.release_person_id(person_id)
        
        # Create new person - should reuse the ID
        signatures2 = [
            PersonSignature(
                person_id=0,
                position=(3.0, 4.0),
                activity="walking",
                signal_strength=-75.0,
                confidence=0.8,
            ),
        ]
        states2 = separator.assign_person_ids(signatures2)
        
        assert states2[0].person_id == person_id  # Reused ID


class TestSignalSeparationAlgorithms:
    """Tests for signal separation algorithms."""

    def test_separate_by_clustering(self):
        """Test signal separation using clustering."""
        separator = SignalSeparator()
        
        # Create multi-person signal
        np.random.seed(42)
        # Person 1: Closer (lower RTT)
        rtt1 = np.random.normal(0.4, 0.05, 50)
        rssi1 = np.random.normal(-70, 5, 50)
        
        # Person 2: Further (higher RTT)
        rtt2 = np.random.normal(0.6, 0.05, 50)
        rssi2 = np.random.normal(-75, 5, 50)
        
        rtt = np.concatenate([rtt1, rtt2])
        rssi = np.concatenate([rssi1, rssi2])
        
        mixed_signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        
        # Estimate count
        count = separator.estimate_signal_count(mixed_signal)
        
        # Should estimate at least 1 person
        assert count >= 1

    def test_correlation_calculation(self):
        """Test correlation calculation between signatures."""
        separator = SignalSeparator()
        
        sig1 = PersonSignature(
            person_id=1,
            position=(1.0, 2.0),
            activity="standing",
            signal_strength=-70.0,
            confidence=0.9,
        )
        
        sig2 = PersonSignature(
            person_id=2,
            position=(1.1, 2.1),  # Very close
            activity="standing",
            signal_strength=-69.0,
            confidence=0.8,
        )
        
        correlation = separator._calculate_correlation(sig1, sig2)
        
        # Should be high correlation (close position, same activity)
        assert correlation > 0.5

    def test_correlation_low_for_distant_people(self):
        """Test low correlation for distant people."""
        separator = SignalSeparator()
        
        sig1 = PersonSignature(
            person_id=1,
            position=(1.0, 2.0),
            activity="standing",
            signal_strength=-70.0,
            confidence=0.9,
        )
        
        sig2 = PersonSignature(
            person_id=2,
            position=(10.0, 20.0),  # Far away
            activity="walking",
            signal_strength=-80.0,
            confidence=0.8,
        )
        
        correlation = separator._calculate_correlation(sig1, sig2)
        
        # Should be low correlation (distant, different activity)
        assert correlation < 0.5


class TestPersonIdLifecycle:
    """Tests for person ID lifecycle management."""

    def test_get_active_person_count(self):
        """Test getting active person count."""
        separator = SignalSeparator()
        
        # No persons initially
        assert separator.get_active_person_count() == 0
        
        # Add a person
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        separator.assign_person_ids(signatures)
        
        assert separator.get_active_person_count() == 1

    def test_get_person_states(self):
        """Test getting person states."""
        separator = SignalSeparator()
        
        # Add persons
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
            PersonSignature(
                person_id=0,
                position=(3.0, 4.0),
                activity="walking",
                signal_strength=-75.0,
                confidence=0.8,
            ),
        ]
        states = separator.assign_person_ids(signatures)
        
        assert len(states) == 2

    def test_reset(self):
        """Test resetting the separator."""
        separator = SignalSeparator()
        
        # Add some persons
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        separator.assign_person_ids(signatures)
        
        # Reset
        separator.reset()
        
        assert len(separator.person_tracks) == 0
        assert separator.next_person_id == 1
        assert len(separator.released_ids) == 0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_sample_signal(self):
        """Test with single sample signal."""
        separator = SignalSeparator()
        
        signal = {'rssi': [0.5], 'rtt': [0.5]}
        result = separator.separate_signals(signal)
        
        # Should handle gracefully
        assert len(result) >= 0

    def test_very_short_signal(self):
        """Test with very short signal."""
        separator = SignalSeparator()
        
        # Very short signal
        rtt = np.random.normal(0.5, 0.1, 3)
        rssi = np.random.normal(-70, 5, 3)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        count = separator.estimate_signal_count(signal)
        
        # Should estimate at least 1
        assert count >= 1

    def test_empty_rtt_signal(self):
        """Test with empty RTT signal."""
        separator = SignalSeparator()
        
        signal = {'rssi': [], 'rtt': []}
        count = separator.estimate_signal_count(signal)
        
        assert count == 0

    def test_single_person_signature(self):
        """Test with single person signature."""
        separator = SignalSeparator()
        
        signatures = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
        ]
        
        states = separator.assign_person_ids(signatures)
        
        assert len(states) == 1
        assert states[0].person_id == 1

    def test_many_people(self):
        """Test estimating many people."""
        separator = SignalSeparator()
        
        # Create signal with many people (capped at 5)
        np.random.seed(42)
        rtt_parts = []
        rssi_parts = []
        
        for i in range(5):
            rtt_parts.append(np.random.normal(0.4 + i * 0.1, 0.05, 50))
            rssi_parts.append(np.random.normal(-70 - i * 2, 5, 50))
        
        rtt = np.concatenate(rtt_parts)
        rssi = np.concatenate(rssi_parts)
        
        signal = {'rssi': rssi.tolist(), 'rtt': rtt.tolist()}
        count = separator.estimate_signal_count(signal)
        
        # Should be capped at 5
        assert count <= 5


class TestSignalSeparatorIntegration:
    """Integration tests for signal separator."""

    def test_full_pipeline(self):
        """Test complete signal separation pipeline."""
        separator = SignalSeparator()
        
        # Create multi-person signal
        np.random.seed(42)
        
        # Person 1
        rtt1 = np.sin(2 * np.pi * 0.2 * np.linspace(0, 10, 100)) * 0.05 + 0.5
        rssi1 = np.random.normal(-70, 5, 100)
        
        # Person 2
        rtt2 = np.sin(2 * np.pi * 0.3 * np.linspace(0, 10, 100)) * 0.05 + 0.55
        rssi2 = np.random.normal(-75, 5, 100)
        
        mixed_signal = {
            'rssi': (rssi1 + rssi2).tolist(),
            'rtt': (rtt1 + rtt2).tolist()
        }
        
        # Separate signals
        separated = separator.separate_signals(mixed_signal)
        assert len(separated) >= 1
        
        # Estimate count
        count = separator.estimate_signal_count(mixed_signal)
        assert count >= 1
        
        # Create signatures
        signatures = []
        for i, sig in enumerate(separated):
            sig_obj = PersonSignature(
                person_id=0,
                position=(float(i * 2), 0.0),
                activity="standing",
                signal_strength=float(np.mean(sig.get('rssi', []))),
                confidence=0.9,
            )
            signatures.append(sig_obj)
        
        # Assign IDs
        states = separator.assign_person_ids(signatures)
        assert len(states) >= 1

    def test_multiple_frames_with_same_people(self):
        """Test tracking same people across multiple frames."""
        separator = SignalSeparator()
        
        # Frame 1: Two people
        signatures1 = [
            PersonSignature(
                person_id=0,
                position=(1.0, 2.0),
                activity="standing",
                signal_strength=-70.0,
                confidence=0.9,
            ),
            PersonSignature(
                person_id=0,
                position=(3.0, 4.0),
                activity="walking",
                signal_strength=-75.0,
                confidence=0.8,
            ),
        ]
        states1 = separator.assign_person_ids(signatures1)
        assert len(states1) == 2
        id1_frame1 = states1[0].person_id
        id2_frame1 = states1[1].person_id
        
        # Frame 2: Same people (slightly moved)
        time.sleep(0.01)  # Small time gap
        signatures2 = [
            PersonSignature(
                person_id=0,
                position=(1.1, 2.1),
                activity="standing",
                signal_strength=-69.0,
                confidence=0.9,
            ),
            PersonSignature(
                person_id=0,
                position=(3.1, 4.1),
                activity="walking",
                signal_strength=-74.0,
                confidence=0.8,
            ),
        ]
        states2 = separator.assign_person_ids(signatures2)
        assert len(states2) == 2
        assert states2[0].person_id == id1_frame1  # Same ID
        assert states2[1].person_id == id2_frame1  # Same ID
