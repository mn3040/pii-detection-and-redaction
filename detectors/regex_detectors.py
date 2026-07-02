"""Regex-based detectors for structured PII patterns.

The project uses regexes for PII with predictable surface forms: SSNs, phone
numbers, emails, card-like numbers, IP addresses, street addresses, and DOBs.
Each detector returns PartialDetection objects with character offsets so the
redactor can replace exact spans without re-tokenizing the text.
"""

import re
from typing import List

from detectors.base import PartialDetection


class SSNDetector:
    name = "regex_ssn"
    # Validate section ranges in the pattern so impossible SSNs are filtered
    # before they become detections.
    PATTERN = re.compile(
        r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection("SSN", m.group(), m.start(), m.end(), 1.0, "regex")
            for m in self.PATTERN.finditer(text)
        ]


class EmailDetector:
    name = "regex_email"
    PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection("EMAIL", m.group(), m.start(), m.end(), 1.0, "regex")
            for m in self.PATTERN.finditer(text)
        ]


class PhoneDetector:
    name = "regex_phone"
    # Support common US formats while using digit boundaries to avoid carving
    # phone-shaped substrings out of longer account numbers.
    PATTERN = re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection("PHONE", m.group(), m.start(), m.end(), 1.0, "regex")
            for m in self.PATTERN.finditer(text)
        ]


class CreditCardDetector:
    name = "regex_credit_card"
    # Collect card-length digit runs first, then use Luhn to separate real card
    # numbers from random long identifiers.
    PATTERN = re.compile(
        r"\b(?:\d[ -]?){13,19}\b"
    )

    @staticmethod
    def _luhn_valid(digits: str) -> bool:
        total = 0
        reverse_digits = digits[::-1]
        for i, d in enumerate(reverse_digits):
            n = int(d)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    def detect(self, text: str) -> List[PartialDetection]:
        results = []
        for m in self.PATTERN.finditer(text):
            raw = m.group()
            digits = re.sub(r"[ -]", "", raw)
            if not (13 <= len(digits) <= 19):
                continue
            confidence = 1.0 if self._luhn_valid(digits) else 0.4
            if confidence < 0.5:
                continue  # Random digit runs are too noisy to redact as cards.
            results.append(
                PartialDetection(
                    "CREDIT_CARD", raw, m.start(), m.end(), confidence, "regex"
                )
            )
        return results


class IPAddressDetector:
    name = "regex_ip_address"
    PATTERN = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection("IP_ADDRESS", m.group(), m.start(), m.end(), 1.0, "regex")
            for m in self.PATTERN.finditer(text)
        ]


class StreetAddressDetector:
    name = "regex_street_address"
    # Street addresses are fuzzy in prose, so the suffix list is the anchor and
    # the detector reports lower confidence than stricter identifiers.
    PATTERN = re.compile(
        r"\b\d{1,6}\s+[A-Z][A-Za-z0-9.'\s]{0,40}?\s+"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|"
        r"Court|Ct|Place|Pl|Way|Terrace|Ter|Circle|Cir)\b\.?",
        re.IGNORECASE,
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection(
                "STREET_ADDRESS", m.group(), m.start(), m.end(), 0.85, "regex"
            )
            for m in self.PATTERN.finditer(text)
        ]


class DateOfBirthDetector:
    name = "regex_dob"
    # Accept common US dates and ISO-style dates, with plausible birth-year
    # bounds to avoid flagging unrelated future dates.
    PATTERN = re.compile(
        r"\b(?:(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19\d{2}|20[0-1]\d)"
        r"|(?:19\d{2}|20[0-1]\d)-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01]))\b"
    )

    def detect(self, text: str) -> List[PartialDetection]:
        return [
            PartialDetection("DATE_OF_BIRTH", m.group(), m.start(), m.end(), 0.8, "regex")
            for m in self.PATTERN.finditer(text)
        ]


def get_all_regex_detectors():
    return [
        SSNDetector(),
        EmailDetector(),
        PhoneDetector(),
        CreditCardDetector(),
        IPAddressDetector(),
        StreetAddressDetector(),
        DateOfBirthDetector(),
    ]
