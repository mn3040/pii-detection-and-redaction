"""CoNLL-2003 domain-transfer evaluation.

Runs the spaCy NER detector against the CoNLL-2003 test split to measure
how well the detector generalizes outside the Faker-generated training domain.
CoNLL-2003 is newswire text — very different from the structured-PII sentences
in our synthetic test set.

Entity mapping:
    CoNLL PER  → PERSON
    CoNLL ORG  → ORGANIZATION
    CoNLL LOC  → LOCATION
    CoNLL MISC → (skipped — no equivalent in our schema)

Requires: pip install datasets
Run from the project root:
    python eval/conll_eval.py
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LABEL_MAP = {
    "PER":  "PERSON",
    "ORG":  "ORGANIZATION",
    "LOC":  "LOCATION",
}


def load_conll_sentences(split="test", max_sentences=500):
    """Load CoNLL-2003 sentences and their NER spans via HuggingFace datasets."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("Run: pip install datasets")
        sys.exit(1)

    ds = load_dataset("conll2003", split=split, trust_remote_code=True)
    label_names = ds.features["ner_tags"].feature.names

    sentences = []
    for row in ds.select(range(min(max_sentences, len(ds)))):
        tokens = row["tokens"]
        tags = row["ner_tags"]
        text = " ".join(tokens)

        spans = []
        i = 0
        char_pos = 0
        token_starts = []
        for tok in tokens:
            token_starts.append(char_pos)
            char_pos += len(tok) + 1  # +1 for the space

        while i < len(tags):
            tag = label_names[tags[i]]
            if tag.startswith("B-"):
                raw_label = tag[2:]
                if raw_label not in LABEL_MAP:
                    i += 1
                    continue
                entity_type = LABEL_MAP[raw_label]
                start = token_starts[i]
                end = token_starts[i] + len(tokens[i])
                i += 1
                while i < len(tags) and label_names[tags[i]] == f"I-{raw_label}":
                    end = token_starts[i] + len(tokens[i])
                    i += 1
                spans.append({
                    "entity_type": entity_type,
                    "start": start,
                    "end": end,
                    "text": text[start:end],
                })
            else:
                i += 1

        sentences.append({"text": text, "spans": spans})

    return sentences


def _spans_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def run_conll_eval(max_sentences=500):
    print(f"\n=== CoNLL-2003 domain-transfer evaluation (first {max_sentences} test sentences) ===")
    print("Entity types: PERSON, ORGANIZATION, LOCATION (MISC skipped — no schema equivalent)\n")

    from detectors.ner_detector import SpacyNERDetector
    detector = SpacyNERDetector()

    sentences = load_conll_sentences(max_sentences=max_sentences)

    by_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    total_tp = total_fp = total_fn = 0

    for sentence in sentences:
        text = sentence["text"]
        ground_truth = sentence["spans"]

        partial = detector.detect(text)
        predictions = [
            {"entity_type": p.entity_type, "start": p.start, "end": p.end}
            for p in partial
        ]

        gt_remaining = list(ground_truth)
        for pred in predictions:
            matched = False
            for idx, gt in enumerate(gt_remaining):
                if (pred["entity_type"] == gt["entity_type"] and
                        _spans_overlap(pred["start"], pred["end"], gt["start"], gt["end"])):
                    by_type[pred["entity_type"]]["tp"] += 1
                    gt_remaining.pop(idx)
                    matched = True
                    break
            if not matched:
                by_type[pred["entity_type"]]["fp"] += 1

        for gt in gt_remaining:
            by_type[gt["entity_type"]]["fn"] += 1

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f

    print(f"  {'Entity':<18}{'TP':>5}{'FP':>5}{'FN':>5}  {'Precision':<12}{'Recall':<12}{'F1'}")
    for etype in ["PERSON", "ORGANIZATION", "LOCATION"]:
        c = by_type[etype]
        p, r, f = prf(c["tp"], c["fp"], c["fn"])
        print(f"  {etype:<18}{c['tp']:>5}{c['fp']:>5}{c['fn']:>5}  {p:<12.3f}{r:<12.3f}{f:.3f}")
        total_tp += c["tp"]; total_fp += c["fp"]; total_fn += c["fn"]

    p, r, f = prf(total_tp, total_fp, total_fn)
    print(f"  {'OVERALL':<18}{total_tp:>5}{total_fp:>5}{total_fn:>5}  {p:<12.3f}{r:<12.3f}{f:.3f}")

    print("""
Note: CoNLL-2003 is Reuters newswire (1996). Our NER detector was not trained or
tuned on it. Lower scores here reflect genuine domain shift, not a calibration bug.
The structured-PII types (SSN, email, phone, CC, IP, DOB) have no CoNLL equivalent
and are excluded from this comparison.""")

    return {etype: by_type[etype] for etype in ["PERSON", "ORGANIZATION", "LOCATION"]}


if __name__ == "__main__":
    run_conll_eval()
