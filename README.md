# PII Detection and Redaction Pipeline

A command-line tool that scans `.txt`, `.csv`, and `.json` files for
personally identifiable information (PII) and either reports what it
finds or produces redacted copies of the files. Built as a privacy
engineering portfolio project, with an emphasis on detection accuracy
and a quantified evaluation rather than just feature coverage.

## Overview

The pipeline combines two complementary detection strategies:

- **Regex detectors** for structured, pattern-based PII — SSNs, emails,
  phone numbers, credit card numbers (with Luhn validation), IP
  addresses, US street addresses, and dates of birth. These are
  precise but can't catch unstructured PII like names.
- **spaCy NER** (`en_core_web_sm`) for unstructured entities — person
  names, locations, organizations, and dates. This catches PII regex
  can't, at the cost of more false positives (e.g. flagging "SSN" the
  word as an organization).

Every detection records its entity type, matched text, source file,
line/row number, the detector that found it, and a confidence score
(`1.0` for regex matches, a heuristic 0.6–0.75 for NER matches based on
label reliability).

## Architecture

```
                         ┌─────────────────┐
  .txt / .csv / .json ─▶ │   PIIEngine      │
                         │  (engine.py)     │
                         └────────┬─────────┘
                                  │ runs both, line/row/field by line
                ┌─────────────────┴─────────────────┐
                ▼                                     ▼
     ┌─────────────────────┐              ┌───────────────────────┐
     │  Regex detectors      │              │  spaCy NER detector    │
     │  (regex_detectors.py) │              │  (ner_detector.py)     │
     │  SSN, EMAIL, PHONE,    │              │  PERSON, GPE→LOCATION, │
     │  CREDIT_CARD, IP,      │              │  ORG, DATE             │
     │  STREET_ADDRESS, DOB   │              │                         │
     └──────────┬────────────┘              └────────────┬────────────┘
                │                                          │
                └───────────────┬──────────────────────────┘
                                 ▼
                      List[Detection] (dataclass)
                                 │
                  ┌──────────────┴──────────────┐
                  ▼                              ▼
         report mode                      mask mode
    (redactor.write_report)      (redactor.write_masked_directory)
    JSON/CSV findings report     [REDACTED_TYPE] in-place copies
```

Detectors implement a common interface (`detect(text) -> List[PartialDetection]`),
so adding a new PII type means writing one small class and registering
it — no changes to the engine, CLI, or eval logic.

## Project layout

```
pii_scan.py              CLI entry point
engine.py                 Orchestrates detectors over input files
redactor.py                Report writer + mask writer (handles span overlap)
detectors/
  base.py                  Detection / PartialDetection dataclasses
  regex_detectors.py        7 regex-based detectors
  ner_detector.py            spaCy NER wrapper
data_gen/
  generate_test_data.py     Synthetic labeled test set generator (Faker)
eval/
  evaluate.py                Precision/recall/F1 against the synthetic set
  test_dataset/               Generated test_data.txt + labels.json
sample_data/                Example input file for demos
requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/Scripts/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Usage

**Report mode** — scan a directory and write a findings report (no source files touched):

```bash
python pii_scan.py --input ./sample_data --mode report --output results.json
```

**Mask mode** — scan a directory and write redacted copies to a new directory:

```bash
python pii_scan.py --input ./sample_data --mode mask --output ./redacted
```

Other flags:

- `--no-ner` — run regex detectors only (faster, no spaCy model needed)
- `--spacy-model en_core_web_trf` — use a larger/more accurate spaCy model

### Example output

Input (`sample_data/sample.txt`):

```
Hi, my name is John Smith and I live in Chicago.
You can reach me at john.smith@example.com or call (312) 555-0198.
My SSN is 412-34-5678 and my card number is 4532015112830366.
```

Masked output:

```
Hi, my name is [REDACTED_PERSON] and I live in [REDACTED_LOCATION].
You can reach me at [REDACTED_EMAIL] or call [REDACTED_PHONE].
My [REDACTED_ORGANIZATION] is [REDACTED_SSN] and my card number is [REDACTED_CREDIT_CARD].
```

Report entry (JSON):

```json
{
  "entity_type": "SSN",
  "text": "412-34-5678",
  "start": 10,
  "end": 21,
  "confidence": 1.0,
  "source_file": "sample_data\\sample.txt",
  "line_number": 3,
  "detector": "regex"
}
```

## Evaluation

A synthetic, labeled test set (`data_gen/generate_test_data.py`) generates
100 lines — 60 containing Faker-generated fake PII (names, SSNs, emails,
phone numbers, credit cards, addresses, dates of birth) inserted into
sentence templates, and 40 clean non-PII sentences — with ground-truth
spans recorded in `eval/test_dataset/labels.json`. No real PII is ever
included in the repo.

`eval/evaluate.py` matches predicted detections against ground truth by
line number, entity type, and span overlap, and reports precision,
recall, and F1 — overall, per entity type, and separately for the regex
and NER detectors so the two approaches can be benchmarked independently.

Run it with:

```bash
python data_gen/generate_test_data.py
python eval/evaluate.py
```

Results on the generated test set:

| Detector set | Precision | Recall | F1 |
|---|---|---|---|
| Combined (regex + NER) | 0.599 | 0.907 | 0.721 |
| Regex only | 1.000 | 0.536 | 0.698 |
| NER only | 0.379 | 0.371 | 0.375 |

Per entity type (combined):

| Entity Type | Precision | Recall | F1 |
|---|---|---|---|
| SSN | 1.000 | 1.000 | 1.000 |
| EMAIL | 1.000 | 1.000 | 1.000 |
| PHONE | 1.000 | 1.000 | 1.000 |
| CREDIT_CARD | 1.000 | 1.000 | 1.000 |
| IP_ADDRESS | 1.000 | 1.000 | 1.000 |
| DATE_OF_BIRTH | 1.000 | 1.000 | 1.000 |
| PERSON | 0.808 | 0.875 | 0.840 |
| LOCATION | 0.833 | 0.909 | 0.870 |
| STREET_ADDRESS | 1.000 | 0.200 | 0.333 |
| ORGANIZATION | 0.227 | 0.833 | 0.357 |

**Takeaways:** the regex detectors are precise but only catch ~54% of all
PII on their own, since they're blind to unstructured entities like
names. Adding NER raises recall to ~91% but drops precision to ~60% —
mainly because spaCy over-flags ORGANIZATION (it tags common nouns and
capitalized words like "SSN" as organizations) and STREET_ADDRESS regex
recall is hurt by Faker addresses that don't end in a recognized suffix
word (e.g. apartment/suite formats). This is the real precision/recall
tradeoff of combining structured pattern matching with statistical NER,
and it's the reason the pipeline reports both detector families
separately rather than just one blended number.

## Out of scope (v1)

Image/OCR-based PII detection, multi-language support, and a web UI are
intentionally excluded to keep the text/structured-data pipeline focused
and well-tested.
