"""Shared types for the detection engine."""

from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class Detection:
    entity_type: str
    text: str
    start: int
    end: int
    confidence: float
    source_file: str
    line_number: int
    detector: str  # "regex" or "ner"


class Detector(Protocol):
    """Common interface every detector implements."""

    name: str

    def detect(self, text: str) -> List["PartialDetection"]:
        ...


@dataclass
class PartialDetection:
    """A detection before file/line metadata is attached by the engine."""

    entity_type: str
    text: str
    start: int
    end: int
    confidence: float
    detector: str
