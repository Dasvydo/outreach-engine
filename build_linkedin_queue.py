#!/usr/bin/env python3
"""Build the daily LinkedIn queue for one market, at 20 connects a day.

    python3 build_linkedin_queue.py --market dk
    python3 build_linkedin_queue.py --market global --days 5 --start 2026-09-08
    python3 build_linkedin_queue.py --all --dry-run

Dovy runs the `linkedin-automator` himself. This only prepares what it reads.

## The honest bit about the file format

The spec says to write "exactly the format the existing `linkedin-automator`
expects". That tool is not in this container (`find / -iname "*linkedin*automator*"`
returned nothing), so its format could not be read, and claiming a match would be
a lie in a file that gets trusted. See BLOCKED.md B4.

What is written instead is a documented queue in two shapes, JSONL and CSV, with
one record per planned connect. Every field name lives once, in `QUEUE_FIELDS`
below, so remapping to the real format is a single edit rather than a rewrite.

The 20 per day cap is enforced regardless, because that number came from the
spec and is not in doubt. It is a cap across all markets combined, not per
market, which is why `--all` interleaves rather than concatenating: running
three markets at 20 a day each would be 60 connects a day and would get the
account restricted.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from engine import ledger                              # noqa: E402
from engine.contacts import ContactRow, load_contacts  # noqa: E402

ROOT = Path(__file__).resolve().parent
QUEUE_DIR = ROOT / "queue"
HOOKS = ROOT / "config" / "hooks.yaml"

# The existing automator's cap. Not a suggestion, and not per market.
DAILY_CAP = 20

# Campaign start. LinkedIn and phone start here in all three markets; email
# cannot start before roughly 22 September because of mailbox warmup.
CAMPAIGN_START = "2026-09-08"

SEQUENCE_BY_MARKET = {"dk": "linkedin_da", "lt": "linkedin_lt", "global": "linkedin_en"}
LOCALE_BY_MARKET = {"dk": "da", "lt": "lt", "global": "en"}

# ---------------------------------------------------------------------------
# The one place the queue's field names are defined.
#
# When the real linkedin-automator turns up, open one of its queue files, match
# the names here, and nothing else in this repo has to change.
# ---------------------------------------------------------------------------
QUEUE_FIELDS = (
    "scheduled_date",     # ISO date this connect should go out
    "profile_url",        # LinkedIn profile the automator opens
    "first_name",
    "last_name",
    "company_name",
    "company_domain",
    "market",
    "locale",
    "segment",
    "sequence_id",        # which file in sequences/linkedin/ the copy came from
    "step",               # 1 = connection request
    "note",               # the connect note itself, under 300 characters
    "utm_content",        # {market}_{step}, for the touches row
)

CONNECT_NOTE_LIMIT = 300


def connect_note(contact: ContactRow, hooks: dict) -> str:
    """Step 1 copy for this contact's segment and language, from hooks.yaml."""
    locale = contact.locale or LOCALE_BY_MARKET.get(contact.market, "en")
    try:
        template = hooks["segments"][contact.segment][locale]["connect"]
    except KeyError:
        template = hooks["segments"]["accounting"][locale]["connect"]
    note = " ".join(template.split())
    note = note.format(first_name=contact.first_name or "", company=contact.company_name)
    # Falls back cleanly when the first name is unknown, rather than sending
    # "Hi ,". The sequence files say to start at the verb in that case.
    note = note.replace("Hi , ", "").replace("Hej . ", "").replace("Sveiki, . ", "")
    note = " ".join(note.split())
    if len(note) > CONNECT_NOTE_LIMIT:
        raise ValueError(
            f"connect note for {contact.work_email or contact.linkedin_url} is "
            f"{len(note)} characters, over the {CONNECT_NOTE_LIMIT} cap"
        )
    return note


def schedule(contacts: list[ContactRow], *, start: date, days: int,
             cap: int = DAILY_CAP) -> list[tuple[date, ContactRow]]:
    """Spread contacts across working days at `cap` a day.

    Weekends are skipped. Cold connects on a Saturday read as automation, which
    is the one thing the automator has to avoid looking like.
    """
    out: list[tuple[date, ContactRow]] = []
    day = start
    placed_today = 0
    used_days = 0
    for contact in contacts:
        while day.weekday() >= 5:               # 5 = Saturday, 6 = Sunday
            day += timedelta(days=1)
        if placed_today >= cap:
            day += timedelta(days=1)
            placed_today = 0
            used_days += 1
            while day.weekday() >= 5:
                day += timedelta(days=1)
        if used_days >= days:
            break
        out.append((day, contact))
        placed_today += 1
    return out


def build(markets: list[str], *, contacts_path: Path | None, start: date,
          days: int, out_dir: Path, dry_run: bool) -> dict:
    hooks = yaml.safe_load(HOOKS.read_text(encoding="utf-8"))
    all_contacts: list[ContactRow] = []
    for market in markets:
        rows = [c for c in load_contacts(contacts_path, market=market)
                if c.linkedin_url]
        all_contacts.append(rows)

    # Interleave so the shared 20 a day cap is split across markets rather than
    # spent entirely on whichever market happens to sort first.
    interleaved: list[ContactRow] = []
    for group in zip(*all_contacts) if len(all_contacts) > 1 else [(c,) for c in all_contacts[0]]:
        interleaved.extend(group)
    seen = {id(c) for c in interleaved}
    for rows in all_contacts:
        for contact in rows:
            if id(contact) not in seen:
                interleaved.append(contact)
                seen.add(id(contact))

    planned = schedule(interleaved, start=start, days=days)

    records = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for when, contact in planned:
        record = {
            "scheduled_date": when.isoformat(),
            "profile_url": contact.linkedin_url,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "company_name": contact.company_name,
            "company_domain": contact.company_domain,
            "market": contact.market,
            "locale": contact.locale or LOCALE_BY_MARKET.get(contact.market, "en"),
            "segment": contact.segment,
            "sequence_id": SEQUENCE_BY_MARKET.get(contact.market, "linkedin_en"),
            "step": 1,
            "note": connect_note(contact, hooks),
            "utm_content": f"{contact.market}_1",
        }
        records.append(record)
        if not dry_run:
            ledger.log_touch(
                company_domain=contact.company_domain,
                work_email=contact.work_email,
                channel="linkedin",
                step=1,
                sequence_id=record["sequence_id"],
                market=contact.market,
                locale=record["locale"],
                utm_content=record["utm_content"],
                status="planned",
                sent_at=None,
                replied_at=None,
                reply_sentiment=None,
                created_at=now,
            )

    stamp = start.isoformat()
    name = "-".join(markets)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"linkedin-{name}-{stamp}.jsonl"
    csv_path = out_dir / f"linkedin-{name}-{stamp}.csv"

    if not dry_run:
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(QUEUE_FIELDS))
            writer.writeheader()
            writer.writerows(records)

    per_day: dict[str, int] = {}
    for record in records:
        per_day[record["scheduled_date"]] = per_day.get(record["scheduled_date"], 0) + 1

    return {"records": records, "per_day": per_day,
            "jsonl": jsonl_path, "csv": csv_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_linkedin_queue")
    parser.add_argument("--market", choices=("dk", "lt", "global"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--contacts", type=Path, default=None)
    parser.add_argument("--start", default=CAMPAIGN_START)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=QUEUE_DIR)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the queue and write no file")
    args = parser.parse_args(argv)

    if not args.all and not args.market:
        parser.error("pass --market {dk,lt,global} or --all")

    markets = ["dk", "lt", "global"] if args.all else [args.market]
    start = date.fromisoformat(args.start)

    result = build(markets, contacts_path=args.contacts, start=start,
                   days=args.days, out_dir=args.out_dir, dry_run=args.dry_run)

    print(f"markets       {', '.join(markets)}")
    print(f"cap           {DAILY_CAP} connects a day, shared across all markets")
    print(f"queued        {len(result['records'])} connects")
    for day, count in sorted(result["per_day"].items()):
        flag = "  OVER CAP" if count > DAILY_CAP else ""
        print(f"  {day}  {count:>3}{flag}")
    if args.dry_run:
        print("\n--- DRY RUN, no file written. First 3 records ---")
        for record in result["records"][:3]:
            print(json.dumps(record, ensure_ascii=False, indent=2))
        print("--- end ---")
    else:
        print(f"\nwrote {result['jsonl']}")
        print(f"wrote {result['csv']}")
        print(f"touches logged via {ledger.backend_name()}")
    print("\nQueue field names are defined once, in QUEUE_FIELDS in this file.")
    print("The real linkedin-automator is not in this container (BLOCKED.md B4),")
    print("so match its format there and nothing else needs to change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
