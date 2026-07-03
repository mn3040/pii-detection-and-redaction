"""Generates all evaluation charts and saves them to docs/assets/.

Charts are produced from live evaluation results, not hard-coded numbers.
Re-run this script whenever the detectors, test data, or eval logic changes.

Run from the project root:
    python data_gen/generate_test_data.py   # regenerate test set
    python eval/plots.py                    # regenerate all charts

Output files (all PNG, 150 dpi):
    docs/assets/pr-scatter.png             precision-recall scatter by entity type
    docs/assets/f1-by-entity.png           F1 bar chart per entity type
    docs/assets/threshold-sweep.png        P/R/F1 vs confidence threshold
    docs/assets/adversarial-results.png    adversarial pass/fail by category
"""

import json
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import PIIEngine
from eval.evaluate import (
    _match, _precision_recall_f1, _to_pred_dicts, NER_THRESHOLDS,
    TEXT_PATH, LABELS_PATH,
)
from eval.adversarial_cases import CASES as ADVERSARIAL_CASES, run_adversarial_eval

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "assets")
DPI = 150

# ── color palette (matches project dark theme where sensible) ────────────────
C_REGEX  = "#0f766e"   # teal  — regex detectors
C_NER    = "#7c3aed"   # violet — NER
C_BAD    = "#dc2626"   # red   — ORGANIZATION (excluded)
C_MUTED  = "#94a3b8"   # slate
C_ACCENT = "#2563eb"   # blue  — combined / highlight

ENTITY_COLORS = {
    "SSN":           C_REGEX,
    "EMAIL":         C_REGEX,
    "PHONE":         C_REGEX,
    "CREDIT_CARD":   C_REGEX,
    "IP_ADDRESS":    C_REGEX,
    "DATE_OF_BIRTH": C_REGEX,
    "STREET_ADDRESS":C_REGEX,
    "PERSON":        C_NER,
    "LOCATION":      C_NER,
    "ORGANIZATION":  C_BAD,
}


def _style():
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor":   "white",
        "axes.edgecolor":   "#cbd5e1",
        "axes.grid":        True,
        "grid.color":       "#e2e8f0",
        "grid.linewidth":   0.8,
        "font.family":      "sans-serif",
        "font.size":        11,
        "axes.titlesize":   13,
        "axes.titleweight": "bold",
        "axes.labelsize":   11,
        "xtick.color":      "#64748b",
        "ytick.color":      "#64748b",
        "text.color":       "#0f172a",
    })


def _load_faker_results():
    """Run the main evaluation and return raw results."""
    if not os.path.exists(TEXT_PATH):
        print("Test dataset not found. Run: python data_gen/generate_test_data.py")
        sys.exit(1)

    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    engine = PIIEngine(use_ner=True)
    detections = engine.scan_txt_file(TEXT_PATH)
    return detections, ground_truth


def _per_entity_metrics(detections, ground_truth, detector_filter=None):
    predictions = _to_pred_dicts(detections, detector_filter=detector_filter)
    tp, fp, fn = _match(predictions, ground_truth)

    by_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for d in tp: by_type[d["entity_type"]]["tp"] += 1
    for d in fp: by_type[d["entity_type"]]["fp"] += 1
    for d in fn: by_type[d["entity_type"]]["fn"] += 1

    metrics = {}
    for etype, c in by_type.items():
        p, r, f = _precision_recall_f1(c["tp"], c["fp"], c["fn"])
        metrics[etype] = {"precision": p, "recall": r, "f1": f, **c}
    return metrics


# ── Chart 1: Precision-Recall scatter ───────────────────────────────────────

def plot_pr_scatter(metrics, out_path):
    _style()
    fig, ax = plt.subplots(figsize=(8, 6.5))

    # iso-F1 curves
    recall_range = np.linspace(0.01, 1.0, 300)
    for f1_val, ls in [(0.5, "--"), (0.7, "--"), (0.9, "--")]:
        with np.errstate(invalid="ignore", divide="ignore"):
            prec = f1_val * recall_range / (2 * recall_range - f1_val)
        mask = (prec >= 0) & (prec <= 1)
        ax.plot(recall_range[mask], prec[mask], color=C_MUTED,
                linewidth=0.9, linestyle=ls, zorder=1)
        valid_r = recall_range[mask]
        if len(valid_r):
            ax.text(valid_r[-1] + 0.01, prec[mask][-1],
                    f"F1={f1_val}", fontsize=8.5, color=C_MUTED, va="center")

    # cluster regex-perfect entities into one point with a multi-line label
    regex_perfect = [e for e, m in metrics.items()
                     if m["precision"] == 1.0 and m["recall"] == 1.0
                     and ENTITY_COLORS.get(e) == C_REGEX]
    if regex_perfect:
        ax.scatter(1.0, 1.0, s=110, color=C_REGEX, zorder=5, edgecolors="white", linewidths=0.8)
        label = "\n".join(regex_perfect)
        ax.annotate(label, (1.0, 1.0), xytext=(-10, 6),
                    textcoords="offset points", fontsize=7.5,
                    color=C_REGEX, ha="right", va="bottom",
                    multialignment="right")

    # all other entities
    plotted_perfect = set(regex_perfect)
    for etype, m in metrics.items():
        if etype in plotted_perfect:
            continue
        r, p = m["recall"], m["precision"]
        color = ENTITY_COLORS.get(etype, C_MUTED)
        ax.scatter(r, p, s=90, color=color, zorder=5, edgecolors="white", linewidths=0.8)
        ax.annotate(etype, (r, p), xytext=(6, 3),
                    textcoords="offset points", fontsize=8.5, color=color)

    ax.set_xlim(-0.04, 1.12)
    ax.set_ylim(-0.04, 1.08)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision vs. Recall by Entity Type")

    legend_handles = [
        mpatches.Patch(color=C_REGEX,  label="Regex detector"),
        mpatches.Patch(color=C_NER,    label="spaCy NER"),
        mpatches.Patch(color=C_BAD,    label="NER — excluded from production recommendation"),
    ]
    ax.legend(handles=legend_handles, fontsize=8.5, loc="lower left", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out_path}")


# ── Chart 2: F1 bar chart per entity type ───────────────────────────────────

def plot_f1_bars(metrics, out_path):
    _style()

    # sort by F1 descending
    sorted_items = sorted(metrics.items(), key=lambda x: x[1]["f1"], reverse=True)
    entities = [e for e, _ in sorted_items]
    f1s      = [m["f1"] for _, m in sorted_items]
    colors   = [ENTITY_COLORS.get(e, C_MUTED) for e in entities]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    bars = ax.barh(entities, f1s, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, f1s):
        ax.text(min(val + 0.02, 1.0), bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=8.5, color="#334155")

    ax.set_xlim(0, 1.15)
    ax.set_xlabel("F1 Score")
    ax.set_title("F1 Score by Entity Type (combined regex + NER)")
    ax.invert_yaxis()

    legend_handles = [
        mpatches.Patch(color=C_REGEX, label="Regex detector"),
        mpatches.Patch(color=C_NER,   label="spaCy NER"),
        mpatches.Patch(color=C_BAD,   label="NER — low precision, not recommended for auto-redaction"),
    ]
    ax.legend(handles=legend_handles, fontsize=8.5, loc="lower right", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out_path}")


# ── Chart 3: Confidence threshold sweep ─────────────────────────────────────

def plot_threshold_sweep(detections, ground_truth, out_path):
    _style()

    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        gt = ground_truth

    thresholds = [t for t, _ in NER_THRESHOLDS]
    labels     = [lbl.split("(")[0].strip() for _, lbl in NER_THRESHOLDS]
    precisions, recalls, f1s = [], [], []

    for threshold in thresholds:
        preds = _to_pred_dicts(detections, min_confidence=threshold)
        tp, fp, fn = _match(preds, gt)
        p, r, f = _precision_recall_f1(len(tp), len(fp), len(fn))
        precisions.append(p)
        recalls.append(r)
        f1s.append(f)

    x = np.arange(len(thresholds))
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(x, precisions, "o-", color=C_ACCENT,  label="Precision", linewidth=1.8, markersize=7)
    ax.plot(x, recalls,    "s-", color=C_REGEX,   label="Recall",    linewidth=1.8, markersize=7)
    ax.plot(x, f1s,        "^-", color=C_NER,     label="F1",        linewidth=1.8, markersize=7)

    for xi, (p, r, f) in enumerate(zip(precisions, recalls, f1s)):
        ax.annotate(f"{p:.2f}", (xi, p), xytext=(0, 7),  textcoords="offset points",
                    fontsize=8, ha="center", color=C_ACCENT)
        ax.annotate(f"{r:.2f}", (xi, r), xytext=(0, -14), textcoords="offset points",
                    fontsize=8, ha="center", color=C_REGEX)
        ax.annotate(f"{f:.2f}", (xi, f), xytext=(0, 7),  textcoords="offset points",
                    fontsize=8, ha="center", color=C_NER)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score")
    ax.set_title("Precision / Recall / F1 vs. Confidence Threshold\n"
                 "(left = regex only; each step adds one NER entity type)")
    ax.legend(fontsize=9.5)

    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out_path}")


# ── Chart 4: Adversarial pass/fail by category ──────────────────────────────

def plot_adversarial(out_path):
    _style()

    # collect pass/fail counts from the adversarial cases without printing
    engine = PIIEngine(use_ner=True)
    cat_counts = defaultdict(lambda: {"pass": 0, "fail": 0})

    for case in ADVERSARIAL_CASES:
        entity_type = case["entity_type"]
        is_ner = entity_type in {"PERSON", "LOCATION", "ORGANIZATION"}
        detections = engine.scan_text_line(
            case["text"], source_file="adversarial", line_number=1
        )
        detected = entity_type in {d.entity_type for d in detections}
        passed = detected == case["expect"]
        cat_counts[case["category"]]["pass" if passed else "fail"] += 1

    categories = sorted(cat_counts)
    passes = [cat_counts[c]["pass"] for c in categories]
    fails  = [cat_counts[c]["fail"] for c in categories]
    y = np.arange(len(categories))

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(y, passes, color=C_REGEX,  height=0.5, label="Pass", edgecolor="white")
    ax.barh(y, fails,  left=passes, color=C_BAD, height=0.5, label="Fail", edgecolor="white")

    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontsize=9)
    ax.set_xlabel("Number of cases")
    ax.set_title("Adversarial Edge Case Results by Category")
    ax.legend(fontsize=9.5)
    ax.invert_yaxis()

    # total label at end of each bar
    for yi, (p, f) in enumerate(zip(passes, fails)):
        total = p + f
        ax.text(total + 0.05, yi, f"{p}/{total}", va="center", fontsize=8.5, color="#334155")

    ax.set_xlim(0, max(p + f for p, f in zip(passes, fails)) + 1.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out_path}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    print("Running evaluation to gather live results...")

    detections, ground_truth = _load_faker_results()
    metrics = _per_entity_metrics(detections, ground_truth)

    print("Generating charts:")
    plot_pr_scatter(metrics,
                    os.path.join(ASSETS_DIR, "pr-scatter.png"))
    plot_f1_bars(metrics,
                 os.path.join(ASSETS_DIR, "f1-by-entity.png"))
    plot_threshold_sweep(detections, ground_truth,
                         os.path.join(ASSETS_DIR, "threshold-sweep.png"))
    plot_adversarial(
                     os.path.join(ASSETS_DIR, "adversarial-results.png"))

    print("Done. Charts saved to docs/assets/")


if __name__ == "__main__":
    main()
