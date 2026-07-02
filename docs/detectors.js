// Client-side regex detectors for the browser demo.
// These mirror detectors/regex_detectors.py so the UI and CLI explain the same
// detection logic. Each detector returns normalized span metadata:
// { entityType, text, start, end, confidence }.
// JavaScript regexes with /g keep state, so each scan resets lastIndex first.

const EmailDetector = {
  name: "regex_email",
  pattern: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "EMAIL",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 1.0,
      });
    }
    return results;
  },
};

const SSNDetector = {
  name: "regex_ssn",
  // I validate the three SSN sections in the regex itself so obvious invalid
  // values (000, 666, 900-999, 00, 0000) never enter the result set.
  pattern: /\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b/g,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "SSN",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 1.0,
      });
    }
    return results;
  },
};

const PhoneDetector = {
  name: "regex_phone",
  // The negative digit boundaries keep long account numbers from being sliced
  // into phone-looking chunks. The middle handles common US formatting styles.
  pattern: /(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)/g,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "PHONE",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 1.0,
      });
    }
    return results;
  },
};

const CreditCardDetector = {
  name: "regex_credit_card",
  // First collect card-length digit runs, including common space/dash grouping.
  // The cheaper regex pass narrows candidates before the Luhn checksum runs.
  pattern: /\b(?:\d[ -]?){13,19}\b/g,

  // Luhn is the structural checksum used by major card networks. Walking from
  // the right lets us double every second digit without allocating extra arrays.
  // Values above 9 subtract 9, which is equivalent to summing the two digits.
  luhnValid(digits) {
    if (digits.length < 13 || digits.length > 19) return false;
    let sum = 0;
    let doubleDigit = false;
    for (let i = digits.length - 1; i >= 0; i--) {
      let digit = parseInt(digits[i], 10);
      if (doubleDigit) {
        digit *= 2;
        if (digit > 9) digit -= 9;
      }
      sum += digit;
      doubleDigit = !doubleDigit;
    }
    return sum % 10 === 0;
  },

  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      const digits = match[0].replace(/[ -]/g, "");
      if (digits.length < 13 || digits.length > 19) continue;
      const confidence = this.luhnValid(digits) ? 1.0 : 0.4;
      if (confidence < 0.5) continue;
      results.push({
        entityType: "CREDIT_CARD",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence,
      });
    }
    return results;
  },
};

const IPAddressDetector = {
  name: "regex_ip_address",
  // Each octet is constrained to 0-255, so invalid IP-like strings such as
  // 999.999.999.999 are rejected by the pattern instead of post-filtering.
  pattern: /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "IP_ADDRESS",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 1.0,
      });
    }
    return results;
  },
};

const StreetAddressDetector = {
  name: "regex_street_address",
  // Addresses are more ambiguous in free text, so I anchor on a street number,
  // capitalized street body, and known suffix, then report slightly lower confidence.
  pattern: /\b\d{1,6}\s+[A-Z][A-Za-z0-9.'\s]{0,40}?\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl|Way|Terrace|Ter|Circle|Cir)\b\.?/gi,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "STREET_ADDRESS",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 0.85,
      });
    }
    return results;
  },
};

const DateOfBirthDetector = {
  name: "regex_dob",
  // DOB detection accepts common US dates and ISO-style dates, with the year
  // range limited to plausible birth years to avoid ordinary future dates.
  pattern: /\b(?:(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19\d{2}|20[0-1]\d)|(?:19\d{2}|20[0-1]\d)-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01]))\b/g,
  detect(text) {
    const results = [];
    let match;
    this.pattern.lastIndex = 0;
    while ((match = this.pattern.exec(text)) !== null) {
      results.push({
        entityType: "DATE_OF_BIRTH",
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        confidence: 0.8,
      });
    }
    return results;
  },
};

const REGEX_DETECTORS = [
  EmailDetector,
  SSNDetector,
  PhoneDetector,
  CreditCardDetector,
  IPAddressDetector,
  StreetAddressDetector,
  DateOfBirthDetector,
];
