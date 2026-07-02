"""Detection engine: walks input files and runs all registered detectors
line-by-line (or row/field-by-field for csv/json), producing fully
populated Detection objects.
"""

import csv
import json
import os
from typing import List, Optional

from detectors.base import Detection
from detectors.regex_detectors import get_all_regex_detectors
from detectors.ner_detector import SpacyNERDetector

SUPPORTED_EXTENSIONS = {".txt", ".csv", ".json"}


class PIIEngine:
    def __init__(self, use_ner: bool = True, spacy_model: str = "en_core_web_sm"):
        self.regex_detectors = get_all_regex_detectors()
        self.ner_detector = SpacyNERDetector(spacy_model) if use_ner else None

    def _run_detectors(self, text: str) -> List["Detection"]:
        partials = []
        for detector in self.regex_detectors:
            partials.extend(detector.detect(text))
        if self.ner_detector is not None:
            partials.extend(self.ner_detector.detect(text))
        return partials

    def scan_text_line(self, text: str, source_file: str, line_number: int) -> List[Detection]:
        partials = self._run_detectors(text)
        return [
            Detection(
                entity_type=p.entity_type,
                text=p.text,
                start=p.start,
                end=p.end,
                confidence=p.confidence,
                source_file=source_file,
                line_number=line_number,
                detector=p.detector,
            )
            for p in partials
        ]

    def scan_txt_file(self, path: str) -> List[Detection]:
        detections = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line_number, line in enumerate(f, start=1):
                detections.extend(self.scan_text_line(line, path, line_number))
        return detections

    def scan_csv_file(self, path: str) -> List[Detection]:
        detections = []
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row_number, row in enumerate(reader, start=1):
                row_text = ",".join(row)
                detections.extend(self.scan_text_line(row_text, path, row_number))
        return detections

    def scan_json_file(self, path: str) -> List[Detection]:
        detections = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return detections
        flat_strings = _flatten_json_strings(data)
        for line_number, value in enumerate(flat_strings, start=1):
            detections.extend(self.scan_text_line(value, path, line_number))
        return detections

    def scan_file(self, path: str) -> List[Detection]:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".txt":
            return self.scan_txt_file(path)
        if ext == ".csv":
            return self.scan_csv_file(path)
        if ext == ".json":
            return self.scan_json_file(path)
        return []

    def scan_directory(self, directory: str) -> List[Detection]:
        all_detections = []
        for root, _dirs, files in os.walk(directory):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                full_path = os.path.join(root, filename)
                all_detections.extend(self.scan_file(full_path))
        return all_detections


def _flatten_json_strings(data) -> List[str]:
    """Recursively pull every string value out of a JSON structure."""
    strings = []
    if isinstance(data, dict):
        for value in data.values():
            strings.extend(_flatten_json_strings(value))
    elif isinstance(data, list):
        for item in data:
            strings.extend(_flatten_json_strings(item))
    elif isinstance(data, str):
        strings.append(data)
    return strings
