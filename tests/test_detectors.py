"""Unit tests for individual detector classes and the overlap resolver.

These test the detection logic in isolation — no file I/O, no NER model.
Run with:  pytest tests/
"""

import pytest
from detectors.regex_detectors import (
    SSNDetector,
    EmailDetector,
    PhoneDetector,
    CreditCardDetector,
    IPAddressDetector,
    StreetAddressDetector,
    DateOfBirthDetector,
)
from redactor import _resolve_overlaps
from detectors.base import Detection


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_detection(entity_type, start, end, confidence=1.0):
    return Detection(
        entity_type=entity_type,
        text="x",
        start=start,
        end=end,
        confidence=confidence,
        source_file="test",
        line_number=1,
        detector="regex",
    )


def types_found(detector, text):
    return [d.entity_type for d in detector.detect(text)]


def texts_found(detector, text):
    return [d.text for d in detector.detect(text)]


# ── SSN ───────────────────────────────────────────────────────────────────────

ssn = SSNDetector()

def test_ssn_valid():
    assert texts_found(ssn, "SSN is 412-34-5678") == ["412-34-5678"]

def test_ssn_multiple():
    assert len(ssn.detect("412-34-5678 and 523-45-6789")) == 2

def test_ssn_rejects_000_area():
    assert ssn.detect("000-34-5678") == []

def test_ssn_rejects_666_area():
    assert ssn.detect("666-34-5678") == []

def test_ssn_rejects_900_area():
    assert ssn.detect("987-34-5678") == []

def test_ssn_rejects_00_group():
    assert ssn.detect("412-00-5678") == []

def test_ssn_rejects_0000_serial():
    assert ssn.detect("412-34-0000") == []

def test_ssn_confidence_is_1():
    [d] = ssn.detect("412-34-5678")
    assert d.confidence == 1.0

def test_ssn_span_is_correct():
    text = "SSN: 412-34-5678 ok"
    [d] = ssn.detect(text)
    assert text[d.start:d.end] == "412-34-5678"


# ── Email ─────────────────────────────────────────────────────────────────────

email = EmailDetector()

def test_email_simple():
    assert texts_found(email, "jane@example.com") == ["jane@example.com"]

def test_email_plus_addressing():
    assert texts_found(email, "jane+work@sub.example.co.uk") == ["jane+work@sub.example.co.uk"]

def test_email_no_at_sign():
    assert email.detect("notanemail.com") == []

def test_email_no_tld():
    assert email.detect("jane@example") == []

def test_email_multiple():
    assert len(email.detect("a@b.com and c@d.org")) == 2


# ── Phone ─────────────────────────────────────────────────────────────────────

phone = PhoneDetector()

def test_phone_dashes():
    assert texts_found(phone, "555-867-5309") == ["555-867-5309"]

def test_phone_parens():
    result = texts_found(phone, "(555) 867-5309")
    assert any("867-5309" in t for t in result)

def test_phone_dots():
    assert texts_found(phone, "555.867.5309") == ["555.867.5309"]

def test_phone_country_code():
    result = phone.detect("+1 555 867 5309")
    assert len(result) == 1

def test_phone_no_false_positive_in_long_number():
    # A 16-digit credit card number should not produce a phone match
    matches = phone.detect("4532015112830366")
    assert matches == []


# ── Credit card ───────────────────────────────────────────────────────────────

cc = CreditCardDetector()

def test_cc_luhn_valid_number():
    # 4532015112830366 is a known Luhn-valid Visa test number
    result = cc.detect("4532015112830366")
    assert len(result) == 1
    assert result[0].confidence == 1.0

def test_cc_luhn_invalid_rejected():
    # Flip last digit to make it Luhn-invalid
    assert cc.detect("4532015112830361") == []

def test_cc_with_spaces():
    assert len(cc.detect("4532 0151 1283 0366")) == 1

def test_cc_with_dashes():
    assert len(cc.detect("4532-0151-1283-0366")) == 1

def test_cc_too_short():
    assert cc.detect("453201511283") == []

def test_luhn_algorithm_directly():
    assert cc._luhn_valid("4532015112830366") is True
    assert cc._luhn_valid("4532015112830361") is False
    assert cc._luhn_valid("123") is False  # too short


# ── IP address ────────────────────────────────────────────────────────────────

ip = IPAddressDetector()

def test_ip_valid():
    assert texts_found(ip, "192.168.1.10") == ["192.168.1.10"]

def test_ip_edge_values():
    assert texts_found(ip, "0.0.0.0 and 255.255.255.255") == ["0.0.0.0", "255.255.255.255"]

def test_ip_rejects_out_of_range():
    assert ip.detect("999.999.999.999") == []

def test_ip_rejects_partial():
    assert ip.detect("192.168.1") == []


# ── Street address ────────────────────────────────────────────────────────────

addr = StreetAddressDetector()

def test_street_address_basic():
    result = addr.detect("742 Evergreen Terrace")
    assert len(result) == 1

def test_street_address_avenue():
    result = addr.detect("1600 Pennsylvania Avenue")
    assert len(result) == 1

def test_street_address_confidence():
    [d] = addr.detect("742 Evergreen Terrace")
    assert d.confidence == 0.85

def test_street_address_case_insensitive():
    # The /i flag should match lowercase suffixes too
    assert len(addr.detect("10 Downing street")) == 1


# ── Date of birth ─────────────────────────────────────────────────────────────

dob = DateOfBirthDetector()

def test_dob_us_format():
    assert texts_found(dob, "born 03/14/1991") == ["03/14/1991"]

def test_dob_iso_format():
    assert texts_found(dob, "DOB: 1991-03-14") == ["1991-03-14"]

def test_dob_dashes():
    assert texts_found(dob, "03-14-1991") == ["03-14-1991"]

def test_dob_rejects_future_year():
    # 2025 is outside the 1900-2019 range
    assert dob.detect("01/01/2025") == []

def test_dob_confidence():
    [d] = dob.detect("03/14/1991")
    assert d.confidence == 0.8


# ── Overlap resolution ────────────────────────────────────────────────────────

def test_overlap_keeps_higher_confidence():
    # Two detections over the same span — higher confidence wins
    high = make_detection("EMAIL", 0, 20, confidence=1.0)
    low  = make_detection("ORG",   0, 20, confidence=0.65)
    result = _resolve_overlaps([low, high])
    assert len(result) == 1
    assert result[0].entity_type == "EMAIL"

def test_overlap_keeps_longer_when_equal_confidence():
    short = make_detection("A", 0, 10, confidence=1.0)
    long_ = make_detection("B", 0, 20, confidence=1.0)
    result = _resolve_overlaps([short, long_])
    assert len(result) == 1
    assert result[0].entity_type == "B"

def test_non_overlapping_both_kept():
    a = make_detection("EMAIL", 0, 10)
    b = make_detection("SSN",  15, 30)
    result = _resolve_overlaps([a, b])
    assert len(result) == 2

def test_three_way_overlap_keeps_best():
    best   = make_detection("EMAIL",  0, 20, confidence=1.0)
    middle = make_detection("ORG",    5, 15, confidence=0.65)
    worst  = make_detection("DATE",   8, 12, confidence=0.6)
    result = _resolve_overlaps([middle, worst, best])
    assert len(result) == 1
    assert result[0].entity_type == "EMAIL"
