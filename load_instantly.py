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
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import ledger                              # noqa: E402
from engine.contacts import ContactRow, load_contacts  # noqa: E402

# The BULK import endpoint. The single-lead endpoint at /api/v2/leads takes a
# flat body and names the campaign field `campaign`; this one takes a `leads`
# array and names it `campaign_id`. Posting one shape to the other's URL is the
# defect this file shipped with - it would have failed on the first live call.
INSTANTLY_API = "https://api.instantly.ai/api/v2/leads/add"
INSTANTLY_BLOCKLIST_API = "https://api.instantly.ai/api/v2/block-lists-entries"

# The spec caps `leads` at 1000 per request. Batched well under it so one
# oversized month cannot silently truncate.
MAX_LEADS_PER_REQUEST = 500

SEQUENCE_FILE = Path(__file__).resolve().parent / "sequences" / "email" / "en.md"

# teams.doviloop.dev was never registered. The campaign origin is the Vercel
# deployment, which is what the pixel and PostHog are actually instrumented on,
# so a link to the old host would have sent every click into the void.
UTM = ("https://campaign-site-azure.vercel.app/?utm_source=instantly"
       "&utm_medium=email&utm_campaign=teams_q4&utm_content={market}_{step}")

# Markets that may receive cold email. Lithuania was previously held back for
# "unverified addresses"; AI Arc now supplies verified contacts, and Lithuania's
# own law moved in its favour (see EMAIL_COUNTRIES), so it joins. Denmark never
# does - see the module docstring.
EMAIL_MARKETS = ("global", "lt")

# Market alone is too coarse now. `global` covers GB, NL and the US alike, and
# those three have three different answers, so the country is checked too:
#
#   GB  PECR reg 22 applies only to INDIVIDUAL subscribers, so email to a
#       limited company or LLP needs no prior consent. Sole traders and ordinary
#       partnerships are individual subscribers and DO need it - filter on
#       company form before sending, which this loader cannot yet do.
#   LT  Elektroniniu rysiu istatymas Art. 81(1), as amended by Law XV-815 of
#       2026-04-16, carves legal persons OUT of the prior-consent rule. UAB, AB,
#       MB, II, TUB and KUB all qualify. Sole traders on individuali veikla do
#       not.
#   US  Excluded by choice, not by law - Dovy, 2026-09-14. Too contested.
EMAIL_COUNTRIES = ("GB", "LT")

# The Netherlands, held back pending a second opinion.
#
# Telecommunicatiewet art. 11.7(1) has covered BUSINESS recipients since 2009
# and requires prior consent the sender must be able to PROVE. It draws no
# distinction between a BV and a sole trader, and the explanatory memorandum
# expressly excludes Kamer van Koophandel register data as a basis for consent -
# which is exactly where a bought NL list comes from. On that reading NL cold
# email is not lawful for this campaign, so it defaults off.
#
# This is a research finding, not settled advice, and NL is roughly a thousand
# ICP companies - so unlike the Danish exclusion it HAS a switch. Set it to True
# only on the strength of Dutch counsel, not on the strength of this comment.
NL_CONSENT_CONFIRMED = False

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
        country = (contact.country or "").upper()
        if country == "NL" and not NL_CONSENT_CONFIRMED:
            refused.append((contact, "NL requires provable prior consent "
                                     "(Telecommunicatiewet art. 11.7) - see NL_CONSENT_CONFIRMED"))
            continue
        # Read the flag here rather than baking it into the constant at import
        # time, so flipping it takes effect without a reload.
        allowed = EMAIL_COUNTRIES + (("NL",) if NL_CONSENT_CONFIRMED else ())
        if country and country not in allowed:
            refused.append((contact, f"country {country} is not in the email allowlist "
                                     f"({', '.join(allowed)})"))
            continue
        if "@" not in contact.work_email:
            refused.append((contact, "no work email"))
            continue
        keep.append(contact)
    return keep, refused


def chunked(items: list, size: int = MAX_LEADS_PER_REQUEST):
    """Yield successive batches. The API caps `leads` at 1000 per request."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


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
            "phone": contact.phone,
            "custom_variables": {
                # Values must be string, number, boolean or null - the spec
                # rejects objects and arrays. Anything Instantly has no first
                # class field for lives here and is read as {{key}} in the copy.
                "segmentOpener": segment_opener(contact, hooks),
                "market": contact.market,
                "segment": contact.segment,
                "role": contact.role,
                "country": contact.country,
                "linkedinUrl": contact.linkedin_url,
                "landingPage": UTM.format(market=contact.market, step=1),
            },
        })
    return {
        # `campaign_id`, not `campaign`. The latter belongs to the single-lead
        # endpoint and is silently wrong here - the leads would import with no
        # campaign attached and simply never send.
        "campaign_id": campaign_id,
        "skip_if_in_workspace": True,   # Instantly's own dedup, on top of ours
        "leads": leads,
    }


def is_uuid(value: str) -> bool:
    """Instantly campaign ids are UUIDs. The old default was `teams_q4_global`,
    which is not one, so a live run would have been rejected by the API."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _request(url: str, api_key: str, payload: dict | None = None,
             method: str = "POST", timeout: float = 60.0) -> dict:
    """One API call, with back-off on 429 and 5xx.

    Instantly rate-limits, and a run that gives up on the first 429 loses the
    batch. Anything else raises: failing closed is correct here, because the
    alternative is writing `sent` touches for mail that was never accepted.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    delay = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:500]
            if err.code in (429, 500, 502, 503, 504) and attempt < 4:
                retry_after = err.headers.get("Retry-After") if err.headers else None
                wait = float(retry_after) if (retry_after or "").isdigit() else delay
                print(f"  HTTP {err.code}, retrying in {wait:.0f}s ({body[:120]})",
                      file=sys.stderr)
                time.sleep(wait)
                delay *= 2
                continue
            raise RuntimeError(f"Instantly returned HTTP {err.code}: {body}") from err
    raise RuntimeError("Instantly kept rate-limiting after 5 attempts")


def fetch_blocklist(api_key: str, timeout: float = 60.0) -> set[str]:
    """Mirror Instantly's Global Blocklist locally.

    It holds addresses AND whole domains, and it is workspace-wide. Pulling it
    before an import means a suppressed contact is refused here, with a reason,
    instead of being silently dropped at Instantly's end where nothing in this
    repo would ever learn about it.

    A suppression list that exists only inside a vendor is a legal liability,
    not a feature: if the account goes away, so does the proof you honoured an
    opt-out. Mirroring it is the point.
    """
    blocked: set[str] = set()
    url = f"{INSTANTLY_BLOCKLIST_API}?limit=100"
    while url:
        page = _request(url, api_key, method="GET", timeout=timeout)
        for entry in page.get("items", []) or []:
            value = (entry.get("bl_value") or "").strip().lower()
            if value:
                blocked.add(value)
        cursor = page.get("next_starting_after")
        url = f"{INSTANTLY_BLOCKLIST_API}?limit=100&starting_after={cursor}" if cursor else None
    return blocked


def suppressed(contact: ContactRow, blocklist: set[str]) -> bool:
    """True when the address, or its whole domain, is on the blocklist."""
    email = (contact.work_email or "").strip().lower()
    domain = contact.email_domain
    return bool(email and email in blocklist) or bool(domain and domain in blocklist)


def push(contacts: list[ContactRow], campaign_id: str, hooks: dict, api_key: str,
         *, timeout: float = 60.0) -> tuple[list[ContactRow], dict]:
    """Import contacts in batches. Returns (contacts actually accepted, totals).

    The old code posted once, printed the response and then logged a `sent`
    touch for every contact it had intended to send - regardless of what came
    back. Instantly reports `leads_uploaded`, `in_blocklist`, `skipped_count`
    and `invalid_email_count` per batch, so a batch that half-failed produced a
    ledger that confidently disagreed with reality. Only accepted contacts are
    returned here, and the caller logs touches for those alone.
    """
    totals = {"leads_uploaded": 0, "in_blocklist": 0,
              "skipped_count": 0, "invalid_email_count": 0}
    accepted: list[ContactRow] = []

    batches = list(chunked(contacts))
    for n, batch in enumerate(batches, start=1):
        payload = build_payload(batch, campaign_id, hooks)
        print(f"  batch {n}/{len(batches)}: {len(batch)} leads", file=sys.stderr)
        body = _request(INSTANTLY_API, api_key, payload, timeout=timeout)

        for key in totals:
            value = body.get(key)
            if isinstance(value, (int, float)):
                totals[key] += int(value)

        uploaded = body.get("leads_uploaded")
        if isinstance(uploaded, int) and uploaded < len(batch):
            # The response says how many landed but not WHICH, so the honest
            # move is to take the count at face value from the front of the
            # batch rather than invent a mapping. Anything beyond it is left
            # unlogged - an under-recorded touch is recoverable, a fabricated
            # one is not.
            accepted.extend(batch[:max(0, uploaded)])
            print(f"    only {uploaded}/{len(batch)} accepted "
                  f"(blocklist {body.get('in_blocklist', 0)}, "
                  f"invalid {body.get('invalid_email_count', 0)})", file=sys.stderr)
        else:
            accepted.extend(batch)
    return accepted, totals


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
                        default=os.environ.get("INSTANTLY_CAMPAIGN_ID", ""),
                        help="Instantly campaign UUID; read it from the campaign URL")
    parser.add_argument("--unsubscribe-confirmed", action="store_true",
                        help="assert that the campaign has both "
                             "'Insert unsubscribe link header' and "
                             "'Add unsubscribes to blocklist' enabled. Both "
                             "default to OFF in Instantly and neither can be set "
                             "from the import API.")
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
        if not is_uuid(args.campaign_id):
            print(f"\nNOTE: --campaign-id is {args.campaign_id!r}, which is not a "
                  f"UUID. A live run will refuse it. Read the real id from the "
                  f"campaign URL in Instantly, or set INSTANTLY_CAMPAIGN_ID.")
        batches = list(chunked(keep))
        if len(batches) > 1:
            print(f"NOTE: {len(keep)} leads would go as {len(batches)} requests "
                  f"of at most {MAX_LEADS_PER_REQUEST}; the payload below is all "
                  f"of them in one block for reading.")
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

    if not is_uuid(args.campaign_id):
        print(f"\n--campaign-id {args.campaign_id!r} is not a UUID. Instantly "
              f"campaign ids are UUIDs and the API will reject this.",
              file=sys.stderr)
        print("Read the real id out of the campaign's URL in the Instantly UI, "
              "or set INSTANTLY_CAMPAIGN_ID.", file=sys.stderr)
        return 2

    # Two campaign-level switches decide whether this is compliant mail, and
    # BOTH default to off in Instantly. They cannot be set from the lead import
    # endpoint, so the best this loader can do is refuse to let them pass
    # unnoticed:
    #   insert_unsubscribe_header - without it no List-Unsubscribe header is
    #       emitted at all, which is the one-click opt-out bulk senders are held
    #       to, and which PECR reg 23(b) and the LT and NL rules all assume.
    #   add_unsub_to_block        - without it an unsubscribe is recorded
    #       against the campaign but never reaches the workspace blocklist, so
    #       the next campaign mails them again.
    if not args.unsubscribe_confirmed:
        print("\nRefusing to send: confirm the campaign's unsubscribe settings first.",
              file=sys.stderr)
        print("  In Instantly: Campaign -> Options -> Advanced, enable BOTH", file=sys.stderr)
        print("    'Insert unsubscribe link header'  (insert_unsubscribe_header)", file=sys.stderr)
        print("    'Add unsubscribes to blocklist'   (add_unsub_to_block)", file=sys.stderr)
        print("  Both default to OFF. Then re-run with --unsubscribe-confirmed.",
              file=sys.stderr)
        return 2

    print("\nfetching the workspace blocklist...", file=sys.stderr)
    try:
        blocklist = fetch_blocklist(api_key)
    except RuntimeError as err:
        print(f"could not read the blocklist: {err}", file=sys.stderr)
        print("Refusing to send without it - importing over a suppression list "
              "you could not read is how opt-outs get re-mailed.", file=sys.stderr)
        return 2
    print(f"blocklist holds {len(blocklist)} entries", file=sys.stderr)

    sendable = [c for c in keep if not suppressed(c, blocklist)]
    for contact in keep:
        if suppressed(contact, blocklist):
            print(f"  SUPPRESSED {contact.work_email:44s} on the Instantly blocklist")
    if not sendable:
        print("\neverything eligible is suppressed, nothing to send")
        return 0

    accepted, totals = push(sendable, args.campaign_id, hooks, api_key)
    print("\n" + json.dumps(totals, indent=2))

    written = log_touches(accepted, dry_run=False)
    print(f"{len(accepted)}/{len(sendable)} accepted by Instantly; "
          f"{written} touches logged via {ledger.backend_name()}")
    if len(accepted) < len(sendable):
        print("NOTE: fewer leads were accepted than sent. The ledger records "
              "only what Instantly confirmed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
