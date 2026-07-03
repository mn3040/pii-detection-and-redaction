"""Hand-crafted adversarial and edge-case evaluation.

Faker-generated ground truth is circular: Faker produces SSNs with dashes,
emails in standard form, and US phone numbers — the same assumptions baked
into the regex. These cases deliberately probe everything Faker never generates:
alternative formats, false-positive traps, NER ambiguity, and boundary conditions.

Each case declares the expected outcome so failures are explicit and counted.

Run from the project root:
    python eval/adversarial_cases.py
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import PIIEngine

# ---------------------------------------------------------------------------
# Case definitions
# Each dict: text, entity_type, expect (True=should detect, False=should not),
# category, note.
# ---------------------------------------------------------------------------

CASES = [
    # ── SSN: format variants ─────────────────────────────────────────────────
    {
        "text": "SSN 412 34 5678",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN format variant",
        "note": "spaces instead of dashes — regex anchors on hyphens",
    },
    {
        "text": "Social security number is 412.34.5678",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN format variant",
        "note": "dot-separated SSN — not matched by regex",
    },
    {
        "text": "SSN: 412-34-5678",
        "entity_type": "SSN",
        "expect": True,
        "category": "SSN baseline",
        "note": "standard format with label prefix",
    },
    # ── SSN: false positive traps ────────────────────────────────────────────
    {
        "text": "ZIP+4 code 90210-1234 is in Beverly Hills",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN false positive trap",
        "note": "ZIP+4 has wrong digit counts — should not match",
    },
    {
        "text": "Order reference 000-34-5678 was shipped",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN false positive trap",
        "note": "000 area code is invalid — excluded by lookahead",
    },
    {
        "text": "Employee ID 666-12-3456 is in the system",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN false positive trap",
        "note": "666 area code is invalid — excluded by lookahead",
    },
    {
        "text": "Reference number 900-12-3456",
        "entity_type": "SSN",
        "expect": False,
        "category": "SSN false positive trap",
        "note": "9xx area codes are invalid — excluded by lookahead",
    },
    # ── Phone: format variants ───────────────────────────────────────────────
    {
        "text": "Call me at +44 20 7946 0958",
        "entity_type": "PHONE",
        "expect": False,
        "category": "Phone format variant",
        "note": "UK number — regex covers US formats only",
    },
    {
        "text": "My extension is x4521",
        "entity_type": "PHONE",
        "expect": False,
        "category": "Phone format variant",
        "note": "extension-only — too short to match",
    },
    {
        "text": "Fax: 555-867-5309 ext. 12",
        "entity_type": "PHONE",
        "expect": True,
        "category": "Phone baseline",
        "note": "standard US number with trailing extension text",
    },
    # ── Phone: false positive traps ──────────────────────────────────────────
    {
        "text": "Use promo code 555-867-5309-SAVE",
        "entity_type": "PHONE",
        "expect": True,
        "category": "Phone false positive trap",
        "note": "phone-like prefix before text suffix — partial match expected",
    },
    {
        "text": "Track order 1234567890 at our website",
        "entity_type": "PHONE",
        "expect": False,
        "category": "Phone false positive trap",
        "note": "10-digit order number with no separators — lookbehind should block",
    },
    # ── Credit card: format variants ─────────────────────────────────────────
    {
        "text": "Amex card 3714 496353 98431",
        "entity_type": "CREDIT_CARD",
        "expect": True,
        "category": "Credit card format variant",
        "note": "15-digit Amex in 4-6-5 grouping — Luhn valid",
    },
    {
        "text": "Card: 4532-0151-1283-0366",
        "entity_type": "CREDIT_CARD",
        "expect": True,
        "category": "Credit card baseline",
        "note": "dash-separated Luhn-valid Visa",
    },
    {
        "text": "Invalid card 4532015112830361",
        "entity_type": "CREDIT_CARD",
        "expect": False,
        "category": "Credit card false positive trap",
        "note": "16 digits but Luhn checksum fails",
    },
    {
        "text": "Product SKU 1234567890123456 in stock",
        "entity_type": "CREDIT_CARD",
        "expect": False,
        "category": "Credit card false positive trap",
        "note": "16-digit product code — passes length check but should fail Luhn",
    },
    # ── IP address: false positive traps ────────────────────────────────────
    {
        "text": "Version 3.14.15.92 released today",
        "entity_type": "IP_ADDRESS",
        "expect": False,
        "category": "IP false positive trap",
        "note": "version string with four dot-separated numbers",
    },
    {
        "text": "Path /192.168.1 is not a full IP",
        "entity_type": "IP_ADDRESS",
        "expect": False,
        "category": "IP false positive trap",
        "note": "only three octets — should not match",
    },
    {
        "text": "Connect to 999.999.999.999",
        "entity_type": "IP_ADDRESS",
        "expect": False,
        "category": "IP false positive trap",
        "note": "out-of-range octets",
    },
    {
        "text": "Server is at 10.0.0.1",
        "entity_type": "IP_ADDRESS",
        "expect": True,
        "category": "IP baseline",
        "note": "private-range IP — valid regardless of routability",
    },
    # ── Email: edge cases ────────────────────────────────────────────────────
    {
        "text": "Write to jane at example dot com",
        "entity_type": "EMAIL",
        "expect": False,
        "category": "Email format variant",
        "note": "natural-language obfuscation — regex requires literal @",
    },
    {
        "text": "Contact info@ünicode-domain.de for help",
        "entity_type": "EMAIL",
        "expect": False,
        "category": "Email format variant",
        "note": "internationalized domain name — regex handles ASCII only",
    },
    {
        "text": "Reply to jane+filter@sub.example.co.uk",
        "entity_type": "EMAIL",
        "expect": True,
        "category": "Email baseline",
        "note": "plus addressing with subdomain and two-part TLD",
    },
    {
        "text": "Email address: user@",
        "entity_type": "EMAIL",
        "expect": False,
        "category": "Email false positive trap",
        "note": "@ present but no domain — should not match",
    },
    # ── Date of birth: format variants ───────────────────────────────────────
    {
        "text": "Born on the 14th of March, 1991",
        "entity_type": "DATE_OF_BIRTH",
        "expect": False,
        "category": "DOB format variant",
        "note": "written-out date format — regex handles numeric only",
    },
    {
        "text": "DOB: 03-14-1991",
        "entity_type": "DATE_OF_BIRTH",
        "expect": True,
        "category": "DOB baseline",
        "note": "dash-separated US format with label prefix",
    },
    {
        "text": "Event on 01/01/2024",
        "entity_type": "DATE_OF_BIRTH",
        "expect": False,
        "category": "DOB false positive trap",
        "note": "future/recent year — year range excludes 2020+",
    },
    {
        "text": "Report dated 1985-13-01",
        "entity_type": "DATE_OF_BIRTH",
        "expect": False,
        "category": "DOB false positive trap",
        "note": "month 13 is invalid — regex month range is 01-12",
    },
    # ── Street address: edge cases ───────────────────────────────────────────
    {
        "text": "Ship to 742 Evergreen Terrace",
        "entity_type": "STREET_ADDRESS",
        "expect": True,
        "category": "Address baseline",
        "note": "canonical form with recognized suffix",
    },
    {
        "text": "Lives at 123 Main St Apt 4B",
        "entity_type": "STREET_ADDRESS",
        "expect": False,
        "category": "Address format variant",
        "note": "abbreviated suffix 'St' — regex requires full word",
    },
    {
        "text": "Delivery to 742 Evergreen",
        "entity_type": "STREET_ADDRESS",
        "expect": False,
        "category": "Address format variant",
        "note": "no suffix word — conservative regex misses this",
    },
    # ── NER ambiguity ────────────────────────────────────────────────────────
    {
        "text": "I bought an apple at the store",
        "entity_type": "ORGANIZATION",
        "expect": False,
        "category": "NER ambiguity",
        "note": "lowercase 'apple' — spaCy should not tag as ORG",
    },
    {
        "text": "Apple reported record earnings this quarter",
        "entity_type": "ORGANIZATION",
        "expect": True,
        "category": "NER ambiguity",
        "note": "uppercase Apple in financial context — likely tagged as ORG",
    },
    {
        "text": "Washington signed the bill into law",
        "entity_type": "PERSON",
        "expect": True,
        "category": "NER ambiguity",
        "note": "Washington as a person — may compete with LOCATION",
    },
    {
        "text": "The team flew to Washington for the summit",
        "entity_type": "LOCATION",
        "expect": True,
        "category": "NER ambiguity",
        "note": "Washington as a place — NER should prefer LOCATION in travel context",
    },
    {
        "text": "Dr. María García is the lead investigator",
        "entity_type": "PERSON",
        "expect": True,
        "category": "NER multilingual name",
        "note": "accented name with title — spaCy en_core_web_sm may miss or catch",
    },
    {
        "text": "Wei Zhang joined the team last month",
        "entity_type": "PERSON",
        "expect": True,
        "category": "NER multilingual name",
        "note": "Chinese name in Western name order",
    },
    {
        "text": "The SSN field was left blank",
        "entity_type": "ORGANIZATION",
        "expect": False,
        "category": "NER false positive trap",
        "note": "capitalized acronym 'SSN' — small NER models often tag as ORG",
    },
    {
        "text": "Card number was flagged by the system",
        "entity_type": "ORGANIZATION",
        "expect": False,
        "category": "NER false positive trap",
        "note": "'Card' as a capitalized noun — known false positive with en_core_web_sm",
    },
]


def run_adversarial_eval(use_ner: bool = True):
    engine = PIIEngine(use_ner=use_ner)
    results_by_category = defaultdict(lambda: {"pass": 0, "fail": 0, "cases": []})
    total_pass = 0
    total_fail = 0

    for case in CASES:
        entity_type = case["entity_type"]
        is_ner_entity = entity_type in {"PERSON", "LOCATION", "ORGANIZATION"}

        if is_ner_entity and not use_ner:
            continue

        detections = engine.scan_text_line(case["text"], source_file="adversarial", line_number=1)
        detected_types = {d.entity_type for d in detections}
        detected = entity_type in detected_types

        passed = detected == case["expect"]
        outcome = "PASS" if passed else "FAIL"

        cat = case["category"]
        results_by_category[cat]["pass" if passed else "fail"] += 1
        results_by_category[cat]["cases"].append({**case, "detected": detected, "outcome": outcome})

        if passed:
            total_pass += 1
        else:
            total_fail += 1

    print(f"\n=== Adversarial edge case results ===")
    print(f"Total: {total_pass + total_fail}  PASS: {total_pass}  FAIL: {total_fail}\n")

    print(f"{'Category':<32}{'Pass':>6}{'Fail':>6}")
    print("─" * 46)
    for cat in sorted(results_by_category):
        r = results_by_category[cat]
        print(f"{cat:<32}{r['pass']:>6}{r['fail']:>6}")

    print("\n── Failures ──")
    any_fail = False
    for cat in sorted(results_by_category):
        for c in results_by_category[cat]["cases"]:
            if c["outcome"] == "FAIL":
                any_fail = True
                expected_str = "detect" if c["expect"] else "no detect"
                got_str = "detected" if c["detected"] else "not detected"
                print(f"  [{cat}]")
                print(f"    text:     \"{c['text']}\"")
                print(f"    expected: {expected_str} {c['entity_type']}")
                print(f"    got:      {got_str}")
                print(f"    note:     {c['note']}")
    if not any_fail:
        print("  (none)")

    return results_by_category


if __name__ == "__main__":
    run_adversarial_eval(use_ner=True)
