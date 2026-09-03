#!/usr/bin/env python3
"""Push `global` contacts into an Instantly campaign and log each as a touch.

    python3 load_instantly.py --dry-run
    python3 load_instantly.py --dry-run --contacts lists/contacts-global.csv
    python3 load_instantly.py --live            # refuses without INSTANTLY_API_KEY

Nothing sends in this batch. There is no INSTANTLY_API_KEY in the session and
the sending domains do not exist yet, so `--live` is written, stubbed and logged
as blocked (BLOCKED.md B6). `--dry-run` prints the exact payload that would go
over the wire.

=========================================================================
DANISH ADDRESSES ARE EXCLUDED HERE, IN CODE, AND CANNOT BE FLAGGED BACK ON
=========================================================================

Denmark's marketing law (markedsføringsloven) is stricter than the rest of the
EU on unsolicited commercial email to businesses. Until Dovy confirms otherwise
in writing, no Danish address is permitted into Instantly. Denmark is worked
through LinkedIn and phone instead, which that law does not restrict the same
way, and phone is deliberately the channel that replaces cold email there.

This is enforced as a filter, not as a convention, because a convention is a
thing somebody forgets at 6pm on a Friday and a filter is not. Four independent
signals each exclude on their own, so mislabelling one field is not enough to
get a Danish contact through:

    1. market == "dk"
    2. country == "DK"
    3. the email domain ends in .dk
    4. the phone number is a Danish +45 number

There is no flag, no environment variable and no argument that disables it.
`tests/test_danish_exclusion.py` fails the build if anyone weakens it, including
the case of a Danish firm mislabelled as market `global`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import ledger                              # noqa: E402
from engine.contacts import ContactRow, load_contacts  # noqa: E402

INSTANTLY_API = "https://api.instantly.ai/api/v2/leads"

SEQUENCE_FILE = Path(__file__).resolve().parent / "sequences" / "email" / "en.md"
UTM = ("https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email"
       "&utm_campaign=teams_q4&utm_content=global_{step}")

# The only market that gets cold email. Lithuania joins once addresses are
# verified; Denmark never does, see the module docstring.
EMAIL_MARKETS = ("global",)

DANISH_TLD = ".dk"
DANISH_DIALLING = "+45"


class DanishAddressRefused(RuntimeError):
    """Raised if a Danish contact ever reaches the payload builder.

    Belt and braces. The filter runs first and this should be unreachable, which
    is exactly why it is here: if it ever fires, something upstream changed and
    the run must stop rather than quietly send.
    """


def is_danish(contact: ContactRow) -> tuple[bool, str]:
    """Four independent tests. Any one of them excludes the contact.

    Returns the reason too, because a silently dropped contact is one nobody can
    audit, and this particular drop is a legal decision that needs a paper trail.
    """
    if contact.market == "dk":
        return True, "market is dk"
    if contact.country == "DK":
        return True, "company country is DK"
    if contact.email_domain.endswith(DANISH_TLD):
        return True, f"email domain {contact.email_domain} is a .dk domain"
    if contact.phone.replace(" ", "").startswith(DANISH_DIALLING):
        return True, "phone number is a Danish +45 number"
    return False, ""


def eligible(contacts: list[ContactRow]) -> tuple[list[ContactRow], list[tuple[ContactRow, str]]]:
    """Split into contacts Instantly may have, and contacts it may not."""
    keep: list[ContactRow] = []
    refused: list[tuple[ContactRow, str]] = []
    for contact in contacts:
        danish, reason = is_danish(contact)
        if danish:
            refused.append((contact, f"Danish exclusion: {reason}"))
            continue
        if contact.market not in EMAIL_MARKETS:
            refused.append((contact, f"market {contact.market!r} is not an email market"))
            continue
        if "@" not in contact.work_email:
            refused.append((contact, "no work email"))
            continue
        keep.append(contact)
    return keep, refused


def segment_opener(contact: ContactRow, hooks: dict) -> str:
    try:
        return " ".join(
            hooks["segments"][contact.segment][contact.locale or "en"]["email_opener"].split()
        )
    except KeyError:
        return ""


def build_payload(contacts: list[ContactRow], campaign_id: str, hooks: dict) -> dict:
    """The exact body that would be POSTed to Instantly."""
    leads = []
    for contact in contacts:
        danish, reason = is_danish(contact)
        if danish:
            # Unreachable if `eligible()` ran. Kept so that any future caller
            # that skips the filter still cannot build a Danish payload.
            raise DanishAddressRefused(
                f"{contact.work_email} would have been sent to Instantly ({reason})"
            )
        leads.append({
            "email": contact.work_email,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "company_name": contact.company_name,
            "website": contact.company_domain,
            "personalization": segment_opener(contact, hooks),
            "custom_variables": {
                "segmentOpener": segment_opener(contact, hooks),
                "market": contact.market,
                "segment": contact.segment,
                "role": contact.role,
                "landingPage": UTM.format(step=1),
            },
        })
    return {
        "campaign": campaign_id,
        "skip_if_in_workspace": True,   # Instantly's own dedup, on top of ours
        "leads": leads,
    }


def log_touches(contacts: list[ContactRow], *, dry_run: bool) -> int:
    """One `campaign.touches` row per contact, step 1, status planned.

    The identity fields below (company_name, the two name parts, linkedin_url,
    segment, country) are not new vocabulary and are not written as touch
    columns. They are here because `campaign.touches.contact_id` is NOT NULL on
    the ledger side and this loader works from domains and email addresses:
    `engine/ledger.py` uses them to resolve, or create, the contact the touch
    belongs to. Without them a real ledger has nothing to hang the touch on.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written = 0
    for contact in contacts:
        ledger.log_touch(
            company_domain=contact.company_domain,
            work_email=contact.work_email,
            channel="email",
            step=1,
            sequence_id="email_en",
            market=contact.market,
            locale=contact.locale,
            utm_content=f"{contact.market}_1",
            status="planned" if dry_run else "sent",
            sent_at=None if dry_run else now,
            replied_at=None,
            reply_sentiment=None,
            created_at=now,
            # identity, for contact resolution only
            company_name=contact.company_name,
            first_name=contact.first_name,
            last_name=contact.last_name,
            linkedin_url=contact.linkedin_url,
            role=contact.role,
            segment=contact.segment,
            country=contact.country,
            email_source="instantly_finder",
        )
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="load_instantly")
    parser.add_argument("--contacts", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="print the exact payload and send nothing (default)")
    parser.add_argument("--live", dest="dry_run", action="store_false",
                        help="actually push to Instantly; needs INSTANTLY_API_KEY")
    parser.add_argument("--campaign-id",
                        default=os.environ.get("INSTANTLY_CAMPAIGN_ID", "teams_q4_global"))
    args = parser.parse_args(argv)

    import yaml
    hooks = yaml.safe_load(
        (Path(__file__).resolve().parent / "config" / "hooks.yaml").read_text(encoding="utf-8"))

    contacts = load_contacts(args.contacts)
    keep, refused = eligible(contacts)

    print(f"read {len(contacts)} contacts")
    print(f"eligible for Instantly: {len(keep)}")
    print(f"refused: {len(refused)}")
    for contact, reason in refused:
        print(f"  REFUSED {contact.work_email:46s} {reason}")

    danish_refusals = sum(1 for _, r in refused if r.startswith("Danish exclusion"))
    print(f"\nDanish addresses blocked at the loader: {danish_refusals}")
    print("This is markedsforingsloven, not a preference. Denmark runs on "
          "LinkedIn and phone.")

    if not keep:
        print("\nnothing eligible, nothing to do")
        return 0

    payload = build_payload(keep, args.campaign_id, hooks)

    if args.dry_run:
        print(f"\n--- DRY RUN, nothing sent. Payload for POST {INSTANTLY_API} ---")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        written = log_touches(keep, dry_run=True)
        print(f"--- end payload. {written} touches logged as planned via "
              f"{ledger.backend_name()} ---")
        return 0

    api_key = os.environ.get("INSTANTLY_API_KEY", "")
    if not api_key:
        print("\nINSTANTLY_API_KEY is not set. Refusing to run live.",
              file=sys.stderr)
        print("This is expected in the campaign batch. See BLOCKED.md B6.",
              file=sys.stderr)
        return 2

    # Live push. Never executed in this batch: no key, and the sending domains
    # need two to three weeks of warmup before any of this is safe to run.
    import urllib.request
    request = urllib.request.Request(
        INSTANTLY_API,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.load(response)
    print(json.dumps(body, indent=2))
    log_touches(keep, dry_run=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
