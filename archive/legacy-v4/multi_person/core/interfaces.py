"""Core interfaces for multi-person detection modules."""

from abc import ABC, abstractmethod
from typing import Any


class SignalProcessorInterface(ABC):
    """Interface for signal processing operations."""

    @abstractmethod
    def preprocess_signal(self, raw_signal: Any) -> Any:
        """Preprocess raw signal data.

        Args:
            raw_signal: Raw signal data from Wi-Fi reader

        Returns:
            Preprocessed signal data
        """
        pass

    @abstractmethod
    def extract_features(self, signal: Any) -> dict[str, Any]:
        """Extract features from signal.

        Args:
            signal: Processed signal data

        Returns:
            Dictionary of extracted features
        """
        pass


class SignalSeparatorInterface(ABC):
    """Interface for separating signals from multiple people."""

    @abstractmethod
    def separate_signals(self, mixed_signal: Any) -> list[Any]:
        """Separate mixed signal into individual person signals.

        Args:
            mixed_signal: Combined signal from multiple people

        Returns:
            List of individual person signals
        """
        pass

    @abstractmethod
    def estimate_signal_count(self, signal: Any) -> int:
        """Estimate number of people in signal.

        Args:
            signal: Signal data to analyze

        Returns:
            Estimated number of people
        """
        pass


class PositionEstimatorInterface(ABC):
    """Interface for estimating person positions."""

    @abstractmethod
    def estimate_position(self, signal: Any) -> tuple[float, float]:
        """Estimate position of a person.

        Args:
            signal: Signal data from person

        Returns:
            Tuple of (x, y) coordinates
        """
        pass

    @abstractmethod
    def estimate_positions(self, signals: list[Any]) -> list[tuple[float, float]]:
        """Estimate positions of multiple people.

        Args:
            signals: List of individual person signals

        Returns:
            List of (x, y) coordinate tuples
        """
        pass


class ActivityRecognizerInterface(ABC):
    """Interface for recognizing person activities."""

    @abstractmethod
    def recognize_activity(self, signal: Any) -> str:
        """Recognize activity from signal.

        Args:
            signal: Signal data from person

        Returns:
            Activity label (e.g., 'standing', 'walking', 'falling')
        """
        pass

    @abstractmethod
    def recognize_activities(self, signals: list[Any]) -> list[str]:
        """Recognize activities for multiple people.

        Args:
            signals: List of individual person signals

        Returns:
            List of activity labels
        """
        pass


class PersonTrackerInterface(ABC):
    """Interface for tracking persons across frames."""

    @abstractmethod
    def track_persons(
        self,
        current_positions: list[tuple[float, float]],
        current_activities: list[str],
    ) -> dict[int, dict[str, Any]]:
        """Track persons across frames.

        Args:
            current_positions: Current positions of all persons
            current_activities: Current activities of all persons

        Returns:
            Dictionary mapping person IDs to their state
        """
        pass

    @abstractmethod
    def get_person_count(self) -> int:
        """Get current number of tracked persons.

        Returns:
            Number of tracked persons
        """
        pass


class CalibrationModuleInterface(ABC):
    """Interface for calibration operations."""

    @abstractmethod
    def calibrate(self, reference_signal: Any) -> dict[str, Any]:
        """Perform calibration with reference signal.

        Args:
            reference_signal: Calibration reference signal

        Returns:
            Calibration parameters
        """
        pass

    @abstractmethod
    def apply_calibration(self, signal: Any, params: dict[str, Any]) -> Any:
        """Apply calibration parameters to signal.

        Args:
            signal: Signal to calibrate
            params: Calibration parameters

        Returns:
            Calibrated signal
        """
        pass
