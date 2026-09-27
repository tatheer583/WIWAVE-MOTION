"""Pytest fixtures for multi-person detection tests."""

import pytest
from multi_person.core.interfaces import (
    SignalProcessorInterface,
    SignalSeparatorInterface,
    PositionEstimatorInterface,
    ActivityRecognizerInterface,
    PersonTrackerInterface,
    CalibrationModuleInterface,
)


class MockSignalProcessor(SignalProcessorInterface):
    """Mock implementation of SignalProcessorInterface."""

    def preprocess_signal(self, raw_signal):
        return {"preprocessed": True, "data": raw_signal}

    def extract_features(self, signal):
        return {"features": [1.0, 2.0, 3.0]}


class MockSignalSeparator(SignalSeparatorInterface):
    """Mock implementation of SignalSeparatorInterface."""

    def separate_signals(self, mixed_signal):
        return [{"signal": 1}, {"signal": 2}]

    def estimate_signal_count(self, signal):
        return 2


class MockPositionEstimator(PositionEstimatorInterface):
    """Mock implementation of PositionEstimatorInterface."""

    def estimate_position(self, signal):
        return (1.0, 2.0)

    def estimate_positions(self, signals):
        return [(1.0, 2.0), (3.0, 4.0)]


class MockActivityRecognizer(ActivityRecognizerInterface):
    """Mock implementation of ActivityRecognizerInterface."""

    def recognize_activity(self, signal):
        return "standing"

    def recognize_activities(self, signals):
        return ["standing", "walking"]


class MockPersonTracker(PersonTrackerInterface):
    """Mock implementation of PersonTrackerInterface."""

    def track_persons(self, current_positions, current_activities):
        return {
            1: {"position": (1.0, 2.0), "activity": "standing"},
            2: {"position": (3.0, 4.0), "activity": "walking"},
        }

    def get_person_count(self):
        return 2


class MockCalibrationModule(CalibrationModuleInterface):
    """Mock implementation of CalibrationModuleInterface."""

    def calibrate(self, reference_signal):
        return {"gain": 1.0, "offset": 0.0}

    def apply_calibration(self, signal, params):
        return {"calibrated": True, "data": signal}


@pytest.fixture
def mock_signal_processor():
    return MockSignalProcessor()


@pytest.fixture
def mock_signal_separator():
    return MockSignalSeparator()


@pytest.fixture
def mock_position_estimator():
    return MockPositionEstimator()


@pytest.fixture
def mock_activity_recognizer():
    return MockActivityRecognizer()


@pytest.fixture
def mock_person_tracker():
    return MockPersonTracker()


@pytest.fixture
def mock_calibration_module():
    return MockCalibrationModule()
