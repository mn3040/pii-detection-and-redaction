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

# Confidence values assigned in ner_detector.py — used for the threshold sweep.
NER_THRESHOLDS = [
    (1.00, "regex only          (threshold ≥ 1.00)"),
    (0.75, "+ PERSON            (threshold ≥ 0.75)"),
    (0.70, "+ LOCATION          (threshold ≥ 0.70)"),
    (0.65, "+ ORGANIZATION      (threshold ≥ 0.65)"),
    (0.60, "+ DATE / all NER    (threshold ≥ 0.60)"),
]


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


def _to_pred_dicts(detections, detector_filter=None, min_confidence=0.0):
    result = []
    for d in detections:
        if detector_filter and d.detector != detector_filter:
            continue
        if d.confidence < min_confidence:
            continue
        result.append({
            "line_number": d.line_number,
            "entity_type": d.entity_type,
            "text": d.text,
            "start": d.start,
            "end": d.end,
            "confidence": d.confidence,
        })
    return result


def run_evaluation(detections, ground_truth, detector_filter=None, label="ALL"):
    predictions = _to_pred_dicts(detections, detector_filter)
    tp, fp, fn = _match(predictions, ground_truth)
    precision, recall, f1 = _precision_recall_f1(len(tp), len(fp), len(fn))

    print(f"\n=== {label} ===")
    print(f"TP {len(tp):>4}  FP {len(fp):>4}  FN {len(fn):>4}  |  "
          f"Precision {precision:.3f}  Recall {recall:.3f}  F1 {f1:.3f}")

    by_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for d in tp:
        by_type[d["entity_type"]]["tp"] += 1
    for d in fp:
        by_type[d["entity_type"]]["fp"] += 1
    for d in fn:
        by_type[d["entity_type"]]["fn"] += 1

    print(f"\n  {'Entity type':<18}{'TP':>5}{'FP':>5}{'FN':>5}  "
          f"{'Precision':<12}{'Recall':<12}{'F1'}")
    for entity_type in sorted(by_type):
        c = by_type[entity_type]
        p, r, f = _precision_recall_f1(c["tp"], c["fp"], c["fn"])
        print(f"  {entity_type:<18}{c['tp']:>5}{c['fp']:>5}{c['fn']:>5}  "
              f"{p:<12.3f}{r:<12.3f}{f:.3f}")

    return {"precision": precision, "recall": recall, "f1": f1}, tp, fp, fn


def analyze_false_positives(fp_list, entity_type="ORGANIZATION", limit=12):
    """Print text samples from false positive detections for a given entity type."""
    hits = [d for d in fp_list if d["entity_type"] == entity_type]
    if not hits:
        print(f"\n  No false positives found for {entity_type}.")
        return
    print(f"\n=== False positive samples: {entity_type} (showing up to {limit}) ===")
    for d in hits[:limit]:
        print(f"  line {d['line_number']:>3}  conf {d['confidence']:.2f}  \"{d['text']}\"")
    if len(hits) > limit:
        print(f"  ... and {len(hits) - limit} more")


def run_threshold_sweep(detections, ground_truth):
    """Show how overall precision/recall change as the confidence threshold drops,
    adding each NER entity type in turn."""
    print("\n=== Confidence threshold sweep ===")
    print(f"  {'Operating point':<42}{'TP':>5}{'FP':>5}{'FN':>5}  "
          f"{'Precision':<12}{'Recall':<10}{'F1'}")
    for threshold, label in NER_THRESHOLDS:
        preds = _to_pred_dicts(detections, min_confidence=threshold)
        tp, fp, fn = _match(preds, ground_truth)
        p, r, f = _precision_recall_f1(len(tp), len(fp), len(fn))
        print(f"  {label:<42}{len(tp):>5}{len(fp):>5}{len(fn):>5}  "
              f"{p:<12.3f}{r:<10.3f}{f:.3f}")


def main():
    if not os.path.exists(TEXT_PATH):
        print("Test dataset not found. Run: python data_gen/generate_test_data.py")
        return

    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    engine = PIIEngine(use_ner=True)
    detections = engine.scan_txt_file(TEXT_PATH)

    _, tp_all, fp_all, _ = run_evaluation(
        detections, ground_truth, detector_filter=None, label="Combined (regex + NER)"
    )
    run_evaluation(detections, ground_truth, detector_filter="regex", label="Regex only")
    run_evaluation(detections, ground_truth, detector_filter="ner",   label="NER only")

    run_threshold_sweep(detections, ground_truth)

    # Show what spaCy is tagging as ORGANIZATION when it shouldn't be.
    print()
    analyze_false_positives(fp_all, entity_type="ORGANIZATION")


if __name__ == "__main__":
    main()
