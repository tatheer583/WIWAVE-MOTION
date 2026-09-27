"""Basic interface tests for multi-person detection."""

import pytest
from multi_person.core.interfaces import (
    SignalProcessorInterface,
    SignalSeparatorInterface,
    PositionEstimatorInterface,
    ActivityRecognizerInterface,
    PersonTrackerInterface,
    CalibrationModuleInterface,
)


def test_signal_processor_interface(mock_signal_processor):
    """Test SignalProcessorInterface implementation."""
    processor = mock_signal_processor

    # Test preprocess_signal
    result = processor.preprocess_signal({"raw": "data"})
    assert "preprocessed" in result
    assert result["preprocessed"] is True

    # Test extract_features
    features = processor.extract_features({"signal": "data"})
    assert "features" in features
    assert isinstance(features["features"], list)


def test_signal_separator_interface(mock_signal_separator):
    """Test SignalSeparatorInterface implementation."""
    separator = mock_signal_separator

    # Test separate_signals
    separated = separator.separate_signals({"mixed": "signal"})
    assert isinstance(separated, list)
    assert len(separated) == 2

    # Test estimate_signal_count
    count = separator.estimate_signal_count({"signal": "data"})
    assert count == 2


def test_position_estimator_interface(mock_position_estimator):
    """Test PositionEstimatorInterface implementation."""
    estimator = mock_position_estimator

    # Test estimate_position
    position = estimator.estimate_position({"signal": "data"})
    assert isinstance(position, tuple)
    assert len(position) == 2
    assert position == (1.0, 2.0)

    # Test estimate_positions
    positions = estimator.estimate_positions([{"signal": 1}, {"signal": 2}])
    assert isinstance(positions, list)
    assert len(positions) == 2


def test_activity_recognizer_interface(mock_activity_recognizer):
    """Test ActivityRecognizerInterface implementation."""
    recognizer = mock_activity_recognizer

    # Test recognize_activity
    activity = recognizer.recognize_activity({"signal": "data"})
    assert isinstance(activity, str)
    assert activity == "standing"

    # Test recognize_activities
    activities = recognizer.recognize_activities([{"signal": 1}, {"signal": 2}])
    assert isinstance(activities, list)
    assert len(activities) == 2


def test_person_tracker_interface(mock_person_tracker):
    """Test PersonTrackerInterface implementation."""
    tracker = mock_person_tracker

    # Test track_persons
    tracked = tracker.track_persons(
        [(1.0, 2.0), (3.0, 4.0)],
        ["standing", "walking"],
    )
    assert isinstance(tracked, dict)
    assert len(tracked) == 2

    # Test get_person_count
    count = tracker.get_person_count()
    assert count == 2


def test_calibration_module_interface(mock_calibration_module):
    """Test CalibrationModuleInterface implementation."""
    calibrator = mock_calibration_module

    # Test calibrate
    params = calibrator.calibrate({"reference": "signal"})
    assert isinstance(params, dict)
    assert "gain" in params

    # Test apply_calibration
    result = calibrator.apply_calibration({"signal": "data"}, params)
    assert "calibrated" in result
    assert result["calibrated"] is True
