#!/usr/bin/env python3
"""Pull Instantly replies, classify them, write the result back to touches.

    python3 sync_replies.py --dry-run
    python3 sync_replies.py --dry-run --replies fixtures/replies/sample.json
    python3 sync_replies.py --live                 # needs INSTANTLY_API_KEY

Writes `replied_at` and `reply_sentiment` onto `campaign.touches` through
`campaign_db.record_reply`.

## The taxonomy

The spec says to classify with the DSD discovery pipeline's six-value taxonomy.
That pipeline is not in this container and the spec never enumerates the six
values, so `config/reply_taxonomy.yaml` holds six reconstructed ones, honestly
labelled. See BLOCKED.md B5. This module reads the YAML, so replacing the six
with the real ones is a config edit and no Python changes.

## Two classifiers

`--classifier=keyword` is the default. Deterministic, no API key, no network,
and it is what the tests exercise. Good enough to ship week 1.

`--classifier=model` is written for Claude Haiku, matching the DSD pipeline's
own shape, and is unreachable in this batch because there is no ANTHROPIC_API_KEY
(BLOCKED.md B7).

Neither classifier ever invents a value. Anything that matches nothing falls back
to the YAML's `fallback`, which is `objection`, because "a human should read
this" is the safe wrong answer and "not interested" is not.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from engine import ledger  # noqa: E402
from engine.contacts import ContactRow, load_contacts  # noqa: E402

ROOT = Path(__file__).resolve().parent
TAXONOMY_PATH = ROOT / "config" / "reply_taxonomy.yaml"
DEFAULT_REPLIES = ROOT / "fixtures" / "replies" / "sample.json"

INSTANTLY_REPLIES_API = "https://api.instantly.ai/api/v2/emails?type=received"


def load_taxonomy(path: Path | None = None) -> dict:
    return yaml.safe_load(Path(path or TAXONOMY_PATH).read_text(encoding="utf-8"))


def _fold(text: str) -> str:
    """Lowercase and strip accents so the keyword lists work on real replies.

    A Danish reply says "afmeld" and a Lithuanian one says "nerašykite". The
    keyword lists are written without diacritics on purpose, so both sides of the
    comparison get folded rather than the lists getting duplicated.
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def classify_keyword(body: str, taxonomy: dict) -> tuple[str, str]:
    """Deterministic classification. Returns (value, why).

    Order matters and is the YAML's order, so `unsubscribe` is checked first and
    beats a polite "no thanks, please remove me" that also matches `not_a_fit`.
    """
    folded = _fold(body)
    for value, by_locale in taxonomy["keywords"].items():
        for locale, words in by_locale.items():
            for word in words:
                if _fold(word) in folded:
                    return value, f"matched {locale}:{word!r}"
    return taxonomy["fallback"], "nothing matched, sent to a human"


def classify_model(body: str, taxonomy: dict) -> tuple[str, str]:
    """Claude Haiku classification. Unreachable in this batch, no API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set, so --classifier=model cannot run. "
            "See BLOCKED.md B7. Use the default keyword classifier."
        )
    values = ", ".join(v["id"] for v in taxonomy["values"])
    prompt = (
        "Classify this reply to a cold outreach email into exactly one of these "
        f"values: {values}. Answer with the value and nothing else.\n\n"
        f"Reply:\n{body}"
    )
    import urllib.request
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    answer = payload["content"][0]["text"].strip().lower()
    valid = {v["id"] for v in taxonomy["values"]}
    if answer not in valid:
        # A model that answers off-vocabulary is not trusted into the ledger.
        return taxonomy["fallback"], f"model returned {answer!r}, not in the taxonomy"
    return answer, "claude-haiku-4-5"


def fetch_replies(path: Path | None, *, live: bool) -> list[dict]:
    if not live:
        return json.loads(Path(path or DEFAULT_REPLIES).read_text(encoding="utf-8"))["replies"]

    api_key = os.environ.get("INSTANTLY_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "INSTANTLY_API_KEY is not set. Refusing to run live. See BLOCKED.md B6."
        )
    import urllib.request
    request = urllib.request.Request(
        INSTANTLY_REPLIES_API,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    return payload.get("items", [])


def contacts_by_email(path: Path | None) -> dict[str, ContactRow]:
    """Index the contacts export by lowercased work email.

    Missing or unreadable is not fatal: the classification still prints, and
    each unmatched reply is named. Losing the whole run because one export is
    stale would be worse than losing the ledger write for one reply.
    """
    try:
        rows = load_contacts(path)
    except FileNotFoundError:
        print(f"NOTE: no contacts export at {path}, replies cannot be matched "
              f"back to a contact row. Pass --contacts.\n")
        return {}
    return {row.work_email.strip().lower(): row for row in rows
            if row.work_email}


def identity(contact: ContactRow | None) -> dict[str, str]:
    """The fields `engine/ledger.py` needs to resolve a reply to a contact_id.

    Not reply data and not written as touch columns. campaign.touches.contact_id
    is NOT NULL and campaign_db exposes no reader, so the only way to attach a
    reply to a person is to be able to name the firm and the person. Empty when
    the address is not in the export, which makes the ledger write fail loudly
    with LedgerContactUnresolved rather than inventing a contact.
    """
    if contact is None:
        return {}
    return {
        "company_name": contact.company_name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "linkedin_url": contact.linkedin_url,
        "role": contact.role,
        "segment": contact.segment,
        "country": contact.country,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sync_replies")
    parser.add_argument("--replies", type=Path, default=None)
    parser.add_argument("--taxonomy", type=Path, default=None)
    parser.add_argument("--classifier", choices=("keyword", "model"), default="keyword")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="classify and print, write nothing (default)")
    parser.add_argument("--live", dest="dry_run", action="store_false",
                        help="fetch from Instantly and write to the ledger")
    parser.add_argument("--contacts", type=Path, default=None,
                        help="the contacts export a reply is matched back to, "
                             "so the reply can be tied to a contact row")
    args = parser.parse_args(argv)

    taxonomy = load_taxonomy(args.taxonomy)
    if not taxonomy.get("canonical", False):
        print("NOTE: the reply taxonomy in config/reply_taxonomy.yaml is "
              "reconstructed, not the real DSD six. See BLOCKED.md B5.\n")

    replies = fetch_replies(args.replies, live=not args.dry_run)
    stages = {v["id"]: v["ledger_stage"] for v in taxonomy["values"]}
    actions = {v["id"]: v["next_action"] for v in taxonomy["values"]}
    classify = classify_keyword if args.classifier == "keyword" else classify_model

    print(f"{len(replies)} replies, classifier={args.classifier}, "
          f"ledger={ledger.backend_name()}\n")

    # A reply arrives as an address and a body. campaign.touches keys on
    # contact_id, so the reply has to be matched back to the person it came
    # from before it can be recorded. The contacts export is the only place
    # that mapping exists - campaign_db has no contact reader, see BLOCKED.md
    # B14 - and a reply from an address that is not in it is reported rather
    # than written under a guessed identity.
    by_email = contacts_by_email(args.contacts)

    counts: dict[str, int] = {}
    written = 0
    for reply in replies:
        body = reply.get("body", "")
        value, why = classify(body, taxonomy)
        counts[value] = counts.get(value, 0) + 1
        replied_at = reply.get("received_at") or datetime.now(
            timezone.utc).isoformat(timespec="seconds")

        print(f"  {reply.get('from', '?'):40s} -> {value:12s} ({why})")
        print(f"      stage {stages[value]:12s} next: {actions[value]}")

        payload = dict(
            company_domain=reply.get("company_domain", ""),
            work_email=reply.get("from", ""),
            channel="email",
            step=reply.get("step", 1),
            market=reply.get("market", "global"),
            replied_at=replied_at,
            reply_sentiment=value,
            ledger_stage=stages[value],
            classifier=args.classifier,
            classifier_note=why,
            **identity(by_email.get((reply.get("from") or "").strip().lower())),
        )
        if args.dry_run:
            if written == 0:
                print("\n--- DRY RUN, nothing written. "
                      "record_reply payload for the first reply ---")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                print("--- end payload, remaining replies summarised only ---\n")
        else:
            ledger.record_reply(**payload)
        written += 1

    print(f"\nclassified {written} replies")
    for value in (v["id"] for v in taxonomy["values"]):
        print(f"  {value:12s} {counts.get(value, 0)}")

    if args.dry_run:
        print("\nDRY RUN. Nothing was written to campaign.touches and no live "
              "Instantly call was made. See BLOCKED.md B6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
