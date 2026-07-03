"""spaCy NER-based detector for PERSON, GPE, ORG, DATE entities."""

from typing import List

from detectors.base import PartialDetection

# Entity types we care about for PII purposes, mapped to our taxonomy.
RELEVANT_LABELS = {
    "PERSON": "PERSON",
    "GPE": "LOCATION",
    "ORG": "ORGANIZATION",
    "DATE": "DATE",
}

# spaCy doesn't expose per-entity confidence by default, so we use a
# heuristic score based on entity length and label reliability.
LABEL_BASE_CONFIDENCE = {
    "PERSON": 0.75,
    "GPE": 0.7,
    "ORG": 0.65,
    "DATE": 0.6,
}

ORG_BLOCKLIST = {"SSN", "Card", "Email", "Phone", "Address"}
ORG_SUFFIXES_LOWER = {"inc", "ltd", "llc", "corp", "company", "co",
                      "hospital", "university", "school", "institute", "foundation"}


class SpacyNERDetector:
    name = "ner_spacy"

    def __init__(self, model_name: str = "en_core_web_sm"):
        import spacy

        try:
            self.nlp = spacy.load(model_name)
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model '{model_name}' is not installed. "
                f"Run: python -m spacy download {model_name}"
            ) from exc

    def detect(self, text: str) -> List[PartialDetection]:
        if not text.strip():
            return []
        doc = self.nlp(text)
        results = []
        for ent in doc.ents:
            if ent.label_ not in RELEVANT_LABELS:
                continue
            if ent.label_ == "ORG" and not self._is_valid_org(ent.text):
                continue
            confidence = LABEL_BASE_CONFIDENCE.get(ent.label_, 0.5)
            results.append(
                PartialDetection(
                    entity_type=RELEVANT_LABELS[ent.label_],
                    text=ent.text,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=confidence,
                    detector="ner",
                )
            )
        return results

    def _is_valid_org(self, text: str) -> bool:
        if text.strip() in ORG_BLOCKLIST:
            return False
        words = text.split()
        has_suffix = any(w.rstrip(".").lower() in ORG_SUFFIXES_LOWER for w in words)
        return has_suffix or len(words) >= 2
