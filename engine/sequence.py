"""Render a copy variant into per-contact sequence steps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.model import Contact

ROOT = Path(__file__).resolve().parent.parent
COPY_DIR = ROOT / "copy"
PROOFREAD_SENTINEL = "NEEDS_NATIVE_PROOFREAD"


@dataclass(frozen=True)
class Step:
    day: int
    subject: str
    body: str


class UnproofreadCopy(RuntimeError):
    """Raised rather than sending a sentinel to a real prospect."""


def load_variant(variant: str) -> dict:
    path = COPY_DIR / f"{variant}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in COPY_DIR.glob("*.json")))
        raise FileNotFoundError(f"no copy variant {variant!r}; have: {available}")
    return json.loads(path.read_text(encoding="utf-8"))


def render(contact: Contact, variant: str, *, strict: bool = True) -> list[Step]:
    """Build the sequence for one contact in that contact's language.

    strict=True refuses to render copy still carrying the proofread sentinel.
    Danish and Lithuanian bodies are drafted but NOT native-checked, so a real
    send must either pass strict or explicitly fall back to English.
    """
    spec = load_variant(variant)
    lang = contact.language
    steps: list[Step] = []

    for raw in spec["steps"]:
        subject = raw["subject"].get(lang) or raw["subject"]["en"]
        body = raw["body"].get(lang) or raw["body"]["en"]

        if PROOFREAD_SENTINEL in (subject, body):
            if strict:
                raise UnproofreadCopy(
                    f"variant {variant!r} step day {raw['day']} is not proofread "
                    f"in {lang!r}. Get a native speaker, or pass strict=False to "
                    f"fall back to English."
                )
            subject = raw["subject"]["en"]
            body = raw["body"]["en"]

        fields = {
            "firstName": contact.first_name or "there",
            "companyName": contact.firm.name,
            "sendingAccountFirstName": "{{sendingAccountFirstName}}",
        }
        for key, value in fields.items():
            subject = subject.replace("{{%s}}" % key, value)
            body = body.replace("{{%s}}" % key, value)

        steps.append(Step(raw["day"], subject, body))

    return steps
