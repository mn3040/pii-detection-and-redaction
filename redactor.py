"""Output writers for the two pipeline modes: mask and report."""

import csv
import json
import os
from collections import defaultdict
from dataclasses import asdict
from typing import List

from detectors.base import Detection
from engine import PIIEngine


def write_report(detections: List[Detection], output_path: str) -> None:
    """Write all detections to a JSON or CSV report, inferred from extension."""
    ext = os.path.splitext(output_path)[1].lower()
    rows = [asdict(d) for d in detections]

    if ext == ".csv":
        fieldnames = [
            "entity_type", "text", "start", "end", "confidence",
            "source_file", "line_number", "detector",
        ]
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)


def _resolve_overlaps(detections: List[Detection]) -> List[Detection]:
    """Drop overlapping spans, keeping the highest-confidence (then longest)
    detection for each region so masking never corrupts the text."""
    ranked = sorted(
        detections, key=lambda d: (-d.confidence, -(d.end - d.start))
    )
    chosen: List[Detection] = []
    occupied = []  # list of (start, end) already claimed
    for d in ranked:
        if any(d.start < e and d.end > s for s, e in occupied):
            continue
        chosen.append(d)
        occupied.append((d.start, d.end))
    return chosen


def _mask_line(line: str, detections: List[Detection]) -> str:
    """Replace each detection's span with [REDACTED_TYPE], working from the
    end of the line backwards so earlier offsets stay valid."""
    non_overlapping = _resolve_overlaps(detections)
    ordered = sorted(non_overlapping, key=lambda d: d.start, reverse=True)
    masked = line
    for d in ordered:
        tag = f"[REDACTED_{d.entity_type}]"
        masked = masked[: d.start] + tag + masked[d.end :]
    return masked


def write_masked_directory(input_dir: str, output_dir: str, engine: PIIEngine) -> List[Detection]:
    """Re-scan each supported file in input_dir, write a redacted copy to
    output_dir (mirroring relative paths), and return all detections found."""
    os.makedirs(output_dir, exist_ok=True)
    all_detections: List[Detection] = []

    for root, _dirs, files in os.walk(input_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".txt", ".csv", ".json"):
                continue
            src_path = os.path.join(root, filename)
            rel_path = os.path.relpath(src_path, input_dir)
            dst_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)

            if ext == ".txt":
                detections = _mask_txt(src_path, dst_path, engine)
            elif ext == ".csv":
                detections = _mask_csv(src_path, dst_path, engine)
            else:
                detections = _mask_json(src_path, dst_path, engine)
            all_detections.extend(detections)

    return all_detections


def _mask_txt(src_path: str, dst_path: str, engine: PIIEngine) -> List[Detection]:
    detections = []
    with open(src_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(dst_path, "w", encoding="utf-8") as fout:
        for line_number, line in enumerate(fin, start=1):
            line_detections = engine.scan_text_line(line, src_path, line_number)
            detections.extend(line_detections)
            fout.write(_mask_line(line, line_detections))
    return detections


def _mask_csv(src_path: str, dst_path: str, engine: PIIEngine) -> List[Detection]:
    detections = []
    with open(src_path, "r", encoding="utf-8", errors="replace", newline="") as fin:
        reader = csv.reader(fin)
        rows = list(reader)

    with open(dst_path, "w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout)
        for row_number, row in enumerate(rows, start=1):
            row_text = ",".join(row)
            row_detections = engine.scan_text_line(row_text, src_path, row_number)
            detections.extend(row_detections)
            masked_row_text = _mask_line(row_text, row_detections)
            writer.writerow(masked_row_text.split(","))
    return detections


def _mask_json(src_path: str, dst_path: str, engine: PIIEngine) -> List[Detection]:
    detections = []
    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            with open(dst_path, "w", encoding="utf-8") as fout:
                fout.write("")
            return detections

    counter = {"line": 0}

    def _mask_value(value):
        if isinstance(value, dict):
            return {k: _mask_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_mask_value(v) for v in value]
        if isinstance(value, str):
            counter["line"] += 1
            line_detections = engine.scan_text_line(value, src_path, counter["line"])
            detections.extend(line_detections)
            return _mask_line(value, line_detections)
        return value

    masked_data = _mask_value(data)
    with open(dst_path, "w", encoding="utf-8") as fout:
        json.dump(masked_data, fout, indent=2)

    return detections
