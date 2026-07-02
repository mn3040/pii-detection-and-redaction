#!/usr/bin/env python
"""PII Detection and Redaction Pipeline CLI.

Examples:
    python pii_scan.py --input ./data --mode report --output results.json
    python pii_scan.py --input ./data --mode mask --output ./redacted
    python pii_scan.py --input ./data --mode report --output results.json --no-ner
"""

import argparse
import sys

from engine import PIIEngine
from redactor import write_report, write_masked_directory


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan files for PII and either report findings or redact them."
    )
    parser.add_argument(
        "--input", required=True, help="Directory containing .txt/.csv/.json files to scan"
    )
    parser.add_argument(
        "--mode", required=True, choices=["report", "mask"],
        help="'report' writes a findings report; 'mask' writes redacted copies of the files",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output file path for 'report' mode (.json or .csv), or output directory for 'mask' mode",
    )
    parser.add_argument(
        "--no-ner", action="store_true",
        help="Disable spaCy NER detection and run regex detectors only (faster, no model required)",
    )
    parser.add_argument(
        "--spacy-model", default="en_core_web_sm",
        help="spaCy model to use for NER (default: en_core_web_sm)",
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    engine = PIIEngine(use_ner=not args.no_ner, spacy_model=args.spacy_model)

    if args.mode == "report":
        detections = engine.scan_directory(args.input)
        write_report(detections, args.output)
        print(f"Scanned '{args.input}': found {len(detections)} potential PII detections.")
        print(f"Report written to '{args.output}'.")
    else:
        detections = write_masked_directory(args.input, args.output, engine)
        print(f"Scanned '{args.input}': found {len(detections)} potential PII detections.")
        print(f"Redacted copies written to '{args.output}'.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
