"""Side-by-side comparison of this pipeline vs. Microsoft Presidio.

Both systems run against the same synthetic test set and are scored on the
same ground-truth labels. The comparison shows exactly where a purpose-built
pipeline wins or loses against a production library.

Requires: pip install presidio-analyzer
Run from the project root:
    python eval/presidio_compare.py
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.evaluate import (
    TEXT_PATH, LABELS_PATH, _match, _precision_recall_f1, _to_pred_dicts,
)
from engine import PIIEngine

# ---------------------------------------------------------------------------
# Entity type mapping: Presidio label -> our label
# Unmapped types (LOCATION, DATE_TIME, etc.) are included only where they
# have a reasonable equivalent. Types with no equivalent are dropped so the
# comparison is on a level playing field.
# ---------------------------------------------------------------------------
PRESIDIO_TO_OURS = {
    "US_SSN":          "SSN",
    "EMAIL_ADDRESS":   "EMAIL",
    "PHONE_NUMBER":    "PHONE",
    "CREDIT_CARD":     "CREDIT_CARD",
    "IP_ADDRESS":      "IP_ADDRESS",
    "PERSON":          "PERSON",
    "LOCATION":        "LOCATION",
    "DATE_TIME":       "DATE_OF_BIRTH",  # approximate — Presidio has no DOB type
}

# Entity types included in the comparison (those with equivalents on both sides)
COMPARABLE_TYPES = set(PRESIDIO_TO_OURS.values())


def _run_presidio(lines):
    """Run Presidio AnalyzerEngine on each line and return predictions in our
    standard format: list of dicts with line_number, entity_type, start, end."""
    try:
        from presidio_analyzer import AnalyzerEngine
    except ImportError:
        print("Run: pip install presidio-analyzer")
        sys.exit(1)

    engine = AnalyzerEngine()
    predictions = []

    for line_number, line in enumerate(lines, start=1):
        results = engine.analyze(text=line, language="en")
        for r in results:
            our_type = PRESIDIO_TO_OURS.get(r.entity_type)
            if our_type is None:
                continue
            predictions.append({
                "line_number": line_number,
                "entity_type": our_type,
                "start": r.start,
                "end": r.end,
                "text": line[r.start:r.end],
            })

    return predictions


def _run_ours(lines):
    """Run our PIIEngine line by line and return predictions in the same format."""
    engine = PIIEngine(use_ner=True)
    predictions = []

    for line_number, line in enumerate(lines, start=1):
        detections = engine.scan_text_line(
            line, source_file="test", line_number=line_number
        )
        for d in detections:
            if d.entity_type not in COMPARABLE_TYPES:
                continue
            predictions.append({
                "line_number": line_number,
                "entity_type": d.entity_type,
                "start": d.start,
                "end": d.end,
                "text": d.text,
            })

    return predictions


def _score(predictions, ground_truth, entity_types):
    """Compute per-entity P/R/F1, filtering to entity_types."""
    preds_filtered = [p for p in predictions if p["entity_type"] in entity_types]
    gt_filtered    = [g for g in ground_truth if g["entity_type"] in entity_types]
    tp, fp, fn = _match(preds_filtered, gt_filtered)

    by_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for d in tp: by_type[d["entity_type"]]["tp"] += 1
    for d in fp: by_type[d["entity_type"]]["fp"] += 1
    for d in fn: by_type[d["entity_type"]]["fn"] += 1

    overall_p, overall_r, overall_f = _precision_recall_f1(len(tp), len(fp), len(fn))
    return by_type, overall_p, overall_r, overall_f


def main():
    if not os.path.exists(TEXT_PATH):
        print("Test dataset not found. Run: python data_gen/generate_test_data.py")
        sys.exit(1)

    with open(TEXT_PATH, encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    with open(LABELS_PATH, encoding="utf-8") as f:
        ground_truth = json.load(f)

    # filter ground truth to comparable types only
    gt_comparable = [g for g in ground_truth if g["entity_type"] in COMPARABLE_TYPES]

    print("Running Presidio...")
    presidio_preds = _run_presidio(lines)

    print("Running our pipeline...")
    our_preds = _run_ours(lines)

    presidio_by_type, p_p, p_r, p_f = _score(presidio_preds, gt_comparable, COMPARABLE_TYPES)
    ours_by_type,     o_p, o_r, o_f = _score(our_preds,     gt_comparable, COMPARABLE_TYPES)

    # ── per-entity comparison table ─────────────────────────────────────────
    entity_order = sorted(
        COMPARABLE_TYPES,
        key=lambda e: -(ours_by_type[e]["tp"] + ours_by_type[e]["fn"]),
    )

    col = 14
    print(f"\n{'':18}{'--- Presidio ---':^{col*3}}  {'--- Ours ---':^{col*3}}")
    print(f"{'Entity type':<18}"
          f"{'P':>{col}}{'R':>{col}}{'F1':>{col}}  "
          f"{'P':>{col}}{'R':>{col}}{'F1':>{col}}  Winner")
    print("-" * 110)

    wins_ours = wins_presidio = ties = 0
    for etype in entity_order:
        pc = presidio_by_type[etype]
        oc = ours_by_type[etype]
        pp, pr, pf = _precision_recall_f1(pc["tp"], pc["fp"], pc["fn"])
        op, or_, of = _precision_recall_f1(oc["tp"], oc["fp"], oc["fn"])

        if of > pf + 0.01:
            winner = "OURS"
            wins_ours += 1
        elif pf > of + 0.01:
            winner = "Presidio"
            wins_presidio += 1
        else:
            winner = "~tie"
            ties += 1

        print(f"{etype:<18}"
              f"{pp:>{col}.3f}{pr:>{col}.3f}{pf:>{col}.3f}  "
              f"{op:>{col}.3f}{or_:>{col}.3f}{of:>{col}.3f}  {winner}")

    print("-" * 110)
    print(f"{'OVERALL':<18}"
          f"{p_p:>{col}.3f}{p_r:>{col}.3f}{p_f:>{col}.3f}  "
          f"{o_p:>{col}.3f}{o_r:>{col}.3f}{o_f:>{col}.3f}")

    print(f"\nSummary: ours wins {wins_ours}, Presidio wins {wins_presidio}, "
          f"ties {ties} (threshold +/-0.01 F1)")
    print("""
Notes:
  STREET_ADDRESS is excluded from Presidio comparison — Presidio has no
  dedicated street address recognizer; it falls under generic LOCATION via NER.
  DATE_TIME (Presidio) is compared against DATE_OF_BIRTH (ours) — approximate,
  since Presidio detects all dates, not just birth dates.""")


if __name__ == "__main__":
    main()
