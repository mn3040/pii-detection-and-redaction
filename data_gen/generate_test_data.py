"""Generates a small synthetic, labeled test dataset for evaluating the
PII detection engine. Uses Faker to produce fake PII values mixed into
plain sentences, and writes both the text file and a labels file
(JSON) recording the ground-truth spans.

Run from the project root:
    python data_gen/generate_test_data.py
"""

import json
import os
import random

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

NON_PII_SENTENCES = [
    "The weather today is sunny with a light breeze.",
    "Our quarterly report shows steady growth in revenue.",
    "Please remember to water the plants this weekend.",
    "The meeting has been rescheduled to next Tuesday.",
    "This recipe calls for two cups of flour and one egg.",
    "The library closes at nine on weekdays.",
    "We need to update the documentation before release.",
    "The train was delayed by about fifteen minutes.",
    "Our team finished the sprint ahead of schedule.",
    "The museum exhibit features modern sculpture.",
]

TEMPLATES = [
    ("My name is {PERSON} and I live in {LOCATION}.", ["PERSON", "LOCATION"]),
    ("Contact {PERSON} at {EMAIL} for more details.", ["PERSON", "EMAIL"]),
    ("Please call me at {PHONE} after 5pm.", ["PHONE"]),
    ("My SSN is {SSN}, please keep it confidential.", ["SSN"]),
    ("Card number {CREDIT_CARD} was charged twice.", ["CREDIT_CARD"]),
    ("I was born on {DOB}.", ["DATE_OF_BIRTH"]),
    ("The server IP address is {IP}.", ["IP_ADDRESS"]),
    ("Please ship the package to {ADDRESS}.", ["STREET_ADDRESS"]),
    ("{PERSON} works at {ORG} in {LOCATION}.", ["PERSON", "ORGANIZATION", "LOCATION"]),
    ("Reach {PERSON} via {EMAIL} or {PHONE}.", ["PERSON", "EMAIL", "PHONE"]),
]


def _luhn_checksum(digits: str) -> int:
    total = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10


def fake_credit_card() -> str:
    """Generate a 16-digit number that passes the Luhn check."""
    prefix = "4"  # visa-like prefix
    body = prefix + "".join(str(random.randint(0, 9)) for _ in range(14))
    checksum = _luhn_checksum(body + "0")
    check_digit = (10 - checksum) % 10
    return body + str(check_digit)


def fake_value(token: str):
    if token == "PERSON":
        return fake.name()
    if token == "LOCATION":
        return fake.city()
    if token == "EMAIL":
        return fake.email()
    if token == "PHONE":
        return fake.numerify("###-###-####")
    if token == "SSN":
        return fake.numerify("###-##-####")
    if token == "CREDIT_CARD":
        return fake_credit_card()
    if token == "DOB":
        return fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%m/%d/%Y")
    if token == "IP":
        return fake.ipv4_public()
    if token == "ADDRESS":
        return fake.street_address()
    if token == "ORG":
        return fake.company()
    raise ValueError(f"Unknown token: {token}")


TOKEN_TO_LABEL = {
    "PERSON": "PERSON",
    "LOCATION": "LOCATION",
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "SSN": "SSN",
    "CREDIT_CARD": "CREDIT_CARD",
    "DOB": "DATE_OF_BIRTH",
    "IP": "IP_ADDRESS",
    "ADDRESS": "STREET_ADDRESS",
    "ORG": "ORGANIZATION",
}


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "eval", "test_dataset")
    os.makedirs(out_dir, exist_ok=True)

    lines = []
    labels = []
    line_number = 1

    pii_lines_with_labels = []
    for _ in range(60):
        template, _ = random.choice(TEMPLATES)
        line = ""
        line_labels = []
        i = 0
        while i < len(template):
            if template[i] == "{":
                close = template.index("}", i)
                token = template[i + 1 : close]
                value = fake_value(token)
                start = len(line)
                line += value
                end = len(line)
                line_labels.append({
                    "entity_type": TOKEN_TO_LABEL[token],
                    "text": value,
                    "start": start,
                    "end": end,
                })
                i = close + 1
            else:
                line += template[i]
                i += 1
        pii_lines_with_labels.append((line, line_labels))

    clean_lines = [random.choice(NON_PII_SENTENCES) for _ in range(40)]

    combined = [(line, lbls) for line, lbls in pii_lines_with_labels]
    combined += [(line, []) for line in clean_lines]
    random.shuffle(combined)

    for line, line_labels in combined:
        lines.append(line)
        for lbl in line_labels:
            labels.append({"line_number": line_number, **lbl})
        line_number += 1

    text_path = os.path.join(out_dir, "test_data.txt")
    labels_path = os.path.join(out_dir, "labels.json")

    with open(text_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2)

    print(f"Generated {len(lines)} lines ({len(pii_lines_with_labels)} with PII, "
          f"{len(clean_lines)} clean) with {len(labels)} labeled entities.")
    print(f"Wrote: {text_path}")
    print(f"Wrote: {labels_path}")


if __name__ == "__main__":
    main()
