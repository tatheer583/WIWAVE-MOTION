"""Core data models for multi-person detection."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PersonSignature:
    """Signature of a person based on their signal characteristics."""

    person_id: int
    position: tuple[float, float]
    activity: str
    signal_strength: float
    velocity: Optional[tuple[float, float]] = None
    confidence: float = 1.0


@dataclass
class PersonState:
    """Current state of a person."""

    person_id: int
    position: tuple[float, float]
    activity: str
    timestamp: float
    signal_features: dict[str, Any]
    velocity: Optional[tuple[float, float]] = None
    confidence: float = 1.0


@dataclass
class PersonStateEvent:
    """Event representing a state change for a person."""

    event_id: int
    person_id: int
    event_type: str  # 'enter', 'exit', 'position_change', 'activity_change'
    timestamp: float
    old_state: Optional[PersonState] = None
    new_state: Optional[PersonState] = None


@dataclass
class MultiPersonOutput:
    """Output data structure for multi-person detection results."""

    frame_id: int
    timestamp: float
    persons: list[PersonState]
    person_count: int
    processing_time_ms: float
    metadata: dict[str, Any]
