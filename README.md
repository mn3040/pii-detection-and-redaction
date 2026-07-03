# PII Detection and Redaction Pipeline

[![tests](https://github.com/mn3040/pii-detection-and-redaction/actions/workflows/tests.yml/badge.svg)](https://github.com/mn3040/pii-detection-and-redaction/actions/workflows/tests.yml)

Most PII detection tools are configuration files on top of a black box. You
point them at data, get flags back, and have no clear sense of what fired or
why. I wanted to understand how the rules actually work, so I built every
detector from scratch.

This project scans `.txt`, `.csv`, and `.json` files for personally identifiable
information using two layers: strict regex rules for structured formats (SSNs,
emails, phones, credit cards, IPs, addresses, dates of birth) and a spaCy NER
model for unstructured text (names, places, organizations). It reports exact
character spans, writes redacted copies, and evaluates precision and recall
against a synthetic labeled dataset so the tradeoffs are measurable instead of
hand-wavy. Every rule is readable, testable, and easy to extend.

**Try it live:** https://mn3040.github.io/pii-detection-and-redaction/

## What It Does

- Detect SSNs, emails, phone numbers, credit cards, IP addresses, street
  addresses, and dates of birth using purpose-built regex detectors.
- Detect names, locations, and organizations using spaCy NER.
- Write a findings report (JSON or CSV) with entity type, matched text,
  character span, confidence score, source file, and line number.
- Write redacted copies with `[REDACTED_TYPE]` placeholders, resolving overlaps
  before masking so offsets never corrupt.
- Evaluate detection quality with precision, recall, and F1 against synthetic
  labeled data, no real PII in the repository.
- Run the pipeline from the CLI or explore the regex layer interactively in your
  browser.

## Why I Built This

Production PII tools are designed for compliance workflows. They hide the
detection logic behind policy files and dashboards.

I wanted to understand the rules instead of trusting them. This project focuses
on transparency: every regex is annotated, every confidence score is derived from
a documented heuristic, and the evaluation pipeline makes it clear exactly where
the detectors succeed and where they fall short. The goal is a system you can
read, audit, and extend, not one you configure and hope for the best.

## Architecture

Every detector follows the same contract:

```text
detect(text) -> List[PartialDetection]
```

Detectors return `PartialDetection` objects — matched text, span, entity type,
confidence score. The engine adds source-file context and promotes each one to a
full `Detection`. The redactor either writes a report or replaces selected spans
in place.

```text
Input files
    └── PIIEngine
            ├── RegexDetector × 7   →  PartialDetection list
            └── SpacyNERDetector    →  PartialDetection list
                        │
                    promote to Detection (source_file, line_number)
                        │
                    Redactor
                        ├── write_report()    → JSON / CSV
                        └── write_masked_directory() → redacted copies
```

That contract keeps new PII types small: add a detector class, register it, and
the CLI, reporting, masking, and evaluation code continue to work unchanged.

Detectors are defined as a `Protocol` rather than a base class. That means any
object with the right `detect` method signature is a valid detector, there's
nothing to subclass, no boilerplate to inherit. Python's structural typing checks
that the interface is satisfied without enforcing a class hierarchy.

## Project Layout

```text
pii_scan.py                 CLI entry point
engine.py                   Orchestrates detectors over input files
redactor.py                 Report writer and mask writer
detectors/
  base.py                   Detection dataclasses and Detector protocol
  regex_detectors.py        Structured PII detectors
  ner_detector.py           spaCy NER wrapper
data_gen/
  generate_test_data.py     Synthetic labeled test set generator
eval/
  evaluate.py               Precision / recall / F1 evaluator
  test_dataset/             Generated labels and text
docs/                       GitHub Pages browser demo
tests/                      pytest unit tests
sample_data/                Example input file
requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

On Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

## Run the CLI

Write a findings report without touching the source files:

```bash
python pii_scan.py --input ./sample_data --mode report --output results.json
```

Write redacted copies to a separate directory:

```bash
python pii_scan.py --input ./sample_data --mode mask --output ./redacted
```

Useful options:

| Flag | Purpose |
|---|---|
| `--no-ner` | Run only regex detectors — faster, zero false positives from NER |
| `--spacy-model en_core_web_trf` | Use a larger spaCy model when accuracy matters more than speed |

## Example

Input:

```text
Hi, my name is John Smith and I live in Chicago.
You can reach me at john.smith@example.com or call (312) 555-0198.
My SSN is 412-34-5678 and my card number is 4532015112830366.
```

Masked output:

```text
Hi, my name is [REDACTED_PERSON] and I live in [REDACTED_LOCATION].
You can reach me at [REDACTED_EMAIL] or call [REDACTED_PHONE].
My SSN is [REDACTED_SSN] and my card number is [REDACTED_CREDIT_CARD].
```

Report entry:

```json
{
  "entity_type": "SSN",
  "text": "412-34-5678",
  "start": 10,
  "end": 21,
  "confidence": 1.0,
  "source_file": "sample_data/sample.txt",
  "line_number": 3,
  "detector": "regex"
}
```

## How the Detectors Work

### Regex detectors (`detectors/regex_detectors.py`)

Each regex detector targets one PII format. Confidence is `1.0` for all regex
matches — if the pattern fires, the format is exact by definition.

**SSN** — Matches `NNN-NN-NNNN` and rejects SSNs the Social Security
Administration has never issued: area codes `000`, `666`, and `900`–`999`;
group codes `00`; serial codes `0000`. These exclusions are written as negative
lookaheads so they filter without consuming characters.

**Email** — Matches the local part, `@`, domain, and TLD. Handles subdomains and
plus-addressing (`jane+work@sub.example.co.uk`).

**Phone** — Matches US formats with dashes, dots, parentheses, or spaces, with
an optional `+1` country code. Lookbehind and lookahead assertions prevent the
pattern from matching a slice out of a longer digit string (so a credit card
number doesn't produce a phone hit).

**Credit card** — Matches 13–19 digit strings with optional space or dash
separators, then runs a Luhn checksum before accepting the match.

The Luhn algorithm is a checksum used by every major card network to catch
transcription errors. Walk the digit string right to left: double every second
digit, subtract 9 from any result above 9, sum everything. A valid card number
sums to a multiple of 10. Implementing it here means the detector never flags a
random 16-digit number, only structurally valid card numbers pass.

**IP address** — Matches four dot-separated octets and validates each one against
`0`–`255`. This is done with a regex that enumerates the valid ranges
(`25[0-5]`, `2[0-4]\d`, `1\d{2}`, `[1-9]\d`, `\d`) rather than matching any
three-digit sequence and checking numerically.

**Street address** — Matches a street number followed by a capitalized name and a
recognized suffix word (Street, Avenue, Drive, Road, etc.), case-insensitively.
Confidence is `0.85`, the format is distinctive but not unique the way an SSN
or email is.

**Date of birth** — Matches `MM/DD/YYYY`, `YYYY-MM-DD`, and `MM-DD-YYYY`, with
the year range restricted to `1900`–`2019`. Dates in the current decade are
excluded to avoid matching recent timestamps. Confidence is `0.8`.

### NER detector (`detectors/ner_detector.py`)

The spaCy wrapper runs `en_core_web_sm` and maps entity labels to the pipeline's
entity types: `PERSON`, `GPE` → `LOCATION`, `ORG` → `ORGANIZATION`, `DATE`.
Confidence scores are fixed per label based on how reliable `en_core_web_sm` is
for each type in practice:

| spaCy label | Maps to | Confidence |
|---|---|---:|
| PERSON | PERSON | 0.75 |
| GPE | LOCATION | 0.70 |
| ORG | ORGANIZATION | 0.65 |
| DATE | DATE | 0.60 |

These are heuristics, not calibrated probabilities. They exist so the redactor
can resolve conflicts when a regex match and a NER match overlap on the same
span — higher confidence wins.

### Overlap resolution (`redactor.py`)

Running two detectors over the same text means two detections can cover the same
characters. Masking both independently would corrupt the offsets for everything
that follows.

Before any span is replaced, `_resolve_overlaps` sorts all detections by
confidence descending (then by span length descending as a tiebreaker), then
iterates and skips any detection whose span touches an already-claimed one. The
result is a set of non-overlapping spans. Replacements are then applied
right-to-left so earlier offsets stay valid throughout.

## Evaluation

### What the test set does and does not prove

The primary test set is synthetic: `data_gen/generate_test_data.py` uses Faker
to generate fake PII and writes ground-truth spans to
`eval/test_dataset/labels.json`, so the repository never contains real personal
data. This is deliberate — but it creates a circularity worth naming. Faker
produces SSNs with dashes, emails in standard form, and US-format phone numbers.
The regex detectors were written with those exact formats in mind, so near-perfect
regex scores on Faker data are partly self-fulfilling.

Two things break that circularity: a hand-crafted adversarial suite that targets
formats Faker never generates, and a domain-transfer check against the CoNLL-2003
newswire corpus, which the detectors were not designed for.

Run everything:

```bash
python data_gen/generate_test_data.py   # regenerate synthetic test set
python eval/evaluate.py                 # main eval with threshold sweep
python eval/adversarial_cases.py        # edge cases and failure analysis
python eval/conll_eval.py               # domain-transfer check (requires: pip install datasets)
python eval/plots.py                    # regenerate all charts from live results
```

### Synthetic test set results

![F1 by entity type](docs/assets/f1-by-entity.png)

| Detector set | Precision | Recall | F1 |
|---|---:|---:|---:|
| Regex only | 1.000 | 0.536 | 0.698 |
| NER only | 0.379 | 0.371 | 0.375 |
| Combined regex + NER | 0.599 | 0.907 | 0.721 |

The regex numbers look good because Faker generates exactly the formats the
patterns target. The NER numbers are more honest — spaCy runs on text it has
never seen and gets partial credit for unstructured entities.

### Precision-recall tradeoff by entity type

![Precision-recall scatter](docs/assets/pr-scatter.png)

The scatter plot shows each entity type as a single point. Top-right is ideal.
The six regex-detected structured types cluster at (1.0, 1.0). PERSON and
LOCATION sit in the upper-right with real but imperfect scores. STREET_ADDRESS
sits at the top-left — precision is 1.0 but recall is 0.2, because the regex
anchors on a recognized suffix word and misses abbreviated forms. ORGANIZATION
sits at the bottom-right — spaCy recalls most true organizations but tags
capitalized common nouns (like "SSN" or "Card" in the test sentences) as
organizations too. At P=0.23, three out of four ORGANIZATION detections are
false positives.

### Confidence threshold and operating point

The NER confidence scores (PERSON=0.75, GPE=0.70, ORG=0.65, DATE=0.60) are
heuristics, not calibrated probabilities. They exist to pick a winner when a
regex match and a NER match overlap, and to let users tune the operating point
by setting a confidence floor.

![Confidence threshold sweep](docs/assets/threshold-sweep.png)

Raising the threshold from 0.65 to 0.70 excludes ORGANIZATION detections.
That move trades a small recall drop for a substantial precision gain — the
right choice for any application where false positives mean legitimate text
gets masked.

### Adversarial edge cases

The Faker suite only tests formats it knows how to generate. These 40 hand-crafted
cases probe everything Faker never produces: alternative separators, international
formats, false-positive traps (ZIP+4 codes that match SSN digit counts, version
strings that match IP patterns), and NER ambiguity (Apple as a company vs. a
fruit, Washington as a person vs. a city).

![Adversarial results by category](docs/assets/adversarial-results.png)

Expected failures — things the system is designed to miss — are documented as
such. The chart separates deliberate design choices from genuine bugs.

**Known misses by design:**

- SSN with spaces (`412 34 5678`) and dots (`412.34.5678`) — regex anchors on
  hyphens. Adding space/dot variants would also catch more false positives in
  structured data.
- Phone numbers in non-US formats (`+44 20 7946 0958`) — the detector is
  explicitly US-only.
- Dates written in natural language (`born on the 14th of March, 1991`) — regex
  handles numeric formats only.
- Street addresses without a recognized suffix word (`742 Evergreen`) — intentional
  conservative tradeoff to keep precision at 1.0.
- Internationalized email domains (`user@ünicode-domain.de`) — regex matches ASCII
  characters only.

**Known NER false positives:**

Capitalized acronyms and nouns in mid-sentence position are the core weakness
of `en_core_web_sm` for this use case. "SSN", "Card", and similar tokens get
tagged as ORGANIZATION because the model was trained on newswire text where
unexplained capitalized words tend to be proper nouns.

### Domain transfer: CoNLL-2003

CoNLL-2003 is Reuters newswire from 1996, labeled with PERSON, ORG, LOC, and
MISC. It has no structured PII (no SSNs, credit cards, or IP addresses), so
only the NER detector can be compared here. Running `eval/conll_eval.py` shows
how the spaCy detector performs on text it was not designed for. Scores are
lower than on the Faker test set — that is the honest cost of domain shift, not
a calibration issue. The structured-PII detectors have no CoNLL equivalent and
are excluded from this comparison.

### Production recommendation

| Entity type | Recommended for automated redaction? |
|---|---|
| SSN, EMAIL, PHONE, CREDIT_CARD, IP_ADDRESS, DATE_OF_BIRTH | Yes — regex, precision 1.0 |
| PERSON, LOCATION | Yes — NER, precision 0.81–0.83, acceptable for most use cases |
| STREET_ADDRESS | With review — precision 1.0 but recall 0.2; misses most addresses |
| ORGANIZATION | No — precision 0.23 means 3 in 4 flags are false positives |

Exclude ORGANIZATION from any pipeline where masking false positives has a real
cost. Use `--no-ner` if only structured PII is needed, or set a confidence
threshold of 0.70 to include PERSON and LOCATION while dropping ORGANIZATION.

## GitHub Pages Demo

The `docs/` directory is a client-side reimplementation of the regex detector
layer — no Python backend, nothing sent to a server. It runs the same seven
detectors in JavaScript, renders detections as color-coded inline highlights with
hover tooltips, and shows the masked output and a detections table side by side.

The JS port mirrors the Python detector logic as closely as the language allows.
The Luhn algorithm, the SSN exclusion lookaheads, the phone lookbehind, all of
it is in `docs/detectors.js`, readable and testable in the browser console.

Deployment is handled by `.github/workflows/pages.yml`, which publishes `docs/`
to GitHub Pages whenever `main` changes.

## Tests

```bash
pytest tests/
```

`tests/test_detectors.py` covers all seven regex detectors and the overlap
resolver — 42 tests total. SSN tests include the invalid-area-code exclusions
and span accuracy; credit card tests call `_luhn_valid` directly and cover
space- and dash-separated formats; overlap tests verify that higher confidence
wins, longer spans win on ties, non-overlapping detections are both kept, and
three-way overlaps resolve to the single best detection.

## Out of Scope

This first version intentionally excludes OCR and image detection, multilingual
models, and production access controls. The goal is a focused text pipeline with
transparent behavior and measurable accuracy, not a replacement for production
systems like Microsoft Presidio or AWS Comprehend.
