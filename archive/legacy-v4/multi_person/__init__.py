"""Multi-person detection module for WiWave."""

from multi_person.modules import SignalProcessor, SignalFeatures, SignalSeparator, CalibrationModule, CalibrationParams
from multi_person.core.models import PersonSignature, PersonState, PersonStateEvent, MultiPersonOutput
from multi_person.core.interfaces import (
    SignalProcessorInterface,
    SignalSeparatorInterface,
    PositionEstimatorInterface,
    ActivityRecognizerInterface,
    PersonTrackerInterface,
    CalibrationModuleInterface,
)

__all__ = [
    # Modules
    'SignalProcessor',
    'SignalFeatures',
    'SignalSeparator',
    'CalibrationModule',
    'CalibrationParams',
    # Core models
    'PersonSignature',
    'PersonState',
    'PersonStateEvent',
    'MultiPersonOutput',
    # Core interfaces
    'SignalProcessorInterface',
    'SignalSeparatorInterface',
    'PositionEstimatorInterface',
    'ActivityRecognizerInterface',
    'PersonTrackerInterface',
    'CalibrationModuleInterface',
]
