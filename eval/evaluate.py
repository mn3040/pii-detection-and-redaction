"""Evaluates detection accuracy against the synthetic labeled test set.

A predicted detection is counted as a true positive if it has the same
entity_type, same line_number, and its span overlaps the ground-truth
span. Reports precision/recall/F1 overall and broken down by entity type,
plus separate numbers for regex-only and NER-only detectors so the two
approaches can be benchmarked independently.

Run from the project root (after generating the test set):
    python eval/evaluate.py
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import PIIEngine

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_dataset")
TEXT_PATH = os.path.join(TEST_DATA_DIR, "test_data.txt")
LABELS_PATH = os.path.join(TEST_DATA_DIR, "labels.json")


def _spans_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and a_end > b_start


def _match(predictions, ground_truth):
    """Greedily match predictions to ground truth by (line_number,
    entity_type, overlapping span). Returns (true_positives, false_positives,
    false_negatives) as lists."""
    gt_remaining = list(ground_truth)
    true_positives = []
    false_positives = []

    for pred in predictions:
        match_idx = None
        for idx, gt in enumerate(gt_remaining):
            if (
                pred["line_number"] == gt["line_number"]
                and pred["entity_type"] == gt["entity_type"]
                and _spans_overlap(pred["start"], pred["end"], gt["start"], gt["end"])
            ):
                match_idx = idx
                break
        if match_idx is not None:
            true_positives.append(pred)
            gt_remaining.pop(match_idx)
        else:
            false_positives.append(pred)

    false_negatives = gt_remaining
    return true_positives, false_positives, false_negatives


def _precision_recall_f1(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _to_pred_dicts(detections, detector_filter=None):
    result = []
    for d in detections:
        if detector_filter and d.detector != detector_filter:
            continue
        result.append({
            "line_number": d.line_number,
            "entity_type": d.entity_type,
            "start": d.start,
            "end": d.end,
        })
    return result


def run_evaluation(detector_filter=None, label="ALL"):
    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    engine = PIIEngine(use_ner=True)
    detections = engine.scan_txt_file(TEXT_PATH)
    predictions = _to_pred_dicts(detections, detector_filter)

    tp, fp, fn = _match(predictions, ground_truth)
    precision, recall, f1 = _precision_recall_f1(len(tp), len(fp), len(fn))

    print(f"\n=== Evaluation: {label} ===")
    print(f"True Positives:  {len(tp)}")
    print(f"False Positives: {len(fp)}")
    print(f"False Negatives: {len(fn)}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1 Score:  {f1:.3f}")

    # Per entity-type breakdown
    by_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for d in tp:
        by_type[d["entity_type"]]["tp"] += 1
    for d in fp:
        by_type[d["entity_type"]]["fp"] += 1
    for d in fn:
        by_type[d["entity_type"]]["fn"] += 1

    print(f"\n{'Entity Type':<18}{'Precision':<12}{'Recall':<12}{'F1':<8}")
    for entity_type in sorted(by_type):
        counts = by_type[entity_type]
        p, r, f = _precision_recall_f1(counts["tp"], counts["fp"], counts["fn"])
        print(f"{entity_type:<18}{p:<12.3f}{r:<12.3f}{f:<8.3f}")

    return {"precision": precision, "recall": recall, "f1": f1}


def main():
    if not os.path.exists(TEXT_PATH):
        print("Test dataset not found. Run: python data_gen/generate_test_data.py")
        return

    run_evaluation(detector_filter=None, label="Combined (regex + NER)")
    run_evaluation(detector_filter="regex", label="Regex detectors only")
    run_evaluation(detector_filter="ner", label="NER detector only")


if __name__ == "__main__":
    main()
