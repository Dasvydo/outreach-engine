"""outreach-engine CLI.

    python -m engine.cli counts                    live DK registry counts
    python -m engine.cli cvr-check                 is CVR API access working?
    python -m engine.cli list-dk --vertical accounting --out segments/x.json
    python -m engine.cli mx <domain> [<domain>...] classify mail providers
    python -m engine.cli gate <leads.json>         apply G1-G7, report keep/drop
    python -m engine.cli build <leads.json> --variant capacity --out camp.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import urllib.error
import urllib.request

from engine.cvr import (
    CVR_SEARCH_URL, Credentials, MissingCredentials, harvest,
)
from engine.enrich import classify
from engine.export import to_csv
from engine.gate import MAX_SEATS, MIN_SEATS, partition
from engine.model import Campaign, Contact, Firm
from engine.registry import NACE, dk_firm_counts, lt_sources
from engine.sequence import render, UnproofreadCopy


def _load_firms(path: Path) -> list[tuple[Firm, dict]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        firm = Firm(
            name=r["name"], domain=r.get("domain", ""),
            country=r.get("country", "DK"), vertical=r.get("vertical", "accounting"),
            nace=r.get("nace", ""), employees=r.get("employees"),
            city=r.get("city", ""), registry_id=r.get("registry_id", ""),
            has_dev_team=r.get("has_dev_team"), source=r.get("source", ""),
        )
        out.append((firm, r))
    return out


def _cvr_check() -> int:
    """Report the state of CVR access without needing credentials to run.

    Distinguishes the two failures that look alike from the outside: no
    credentials configured here, versus credentials that the registry rejects.
    """
    print(f"CVR company index: {CVR_SEARCH_URL}")
    try:
        creds = Credentials.from_env()
    except MissingCredentials as e:
        print(f"\n  credentials: NOT CONFIGURED\n\n{e}")
        creds = None

    req = urllib.request.Request(
        CVR_SEARCH_URL, data=b'{"query":{"match_all":{}},"size":0}',
        headers={"Content-Type": "application/json"},
    )
    if creds:
        req.add_header("Authorization", creds.basic_auth)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"\n  reachable, HTTP {resp.status} - access is working")
            return 0
    except urllib.error.HTTPError as e:
        print(f"\n  reachable, HTTP {e.code} {e.reason}")
        if e.code == 401:
            realm = e.headers.get("WWW-Authenticate", "")
            print(f"  the index requires HTTP Basic auth {realm}".rstrip())
            print("  -> see docs/CVR-ACCESS.md")
        return 1
    except urllib.error.URLError as e:
        print(f"\n  UNREACHABLE: {e.reason}")
        return 1


def _list_dk(a) -> int:
    """Harvest one vertical from CVR, enrich by MX, and write the Lead JSON.

    Writes the segment file only. Gating stays in `gate`/`build` so there is
    exactly one implementation of G1-G7 and the list on disk is the raw
    registry truth, not something already filtered by an older gate.
    """
    try:
        h = harvest(
            NACE[a.vertical], a.vertical,
            min_seats=a.min_seats, max_seats=a.max_seats,
            kommune_koder=a.kommune,
        )
    except MissingCredentials as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 3

    print(f"CVR branchekode {NACE[a.vertical]}, {a.min_seats}-{a.max_seats} seats")
    print(f"  {h.seen:>5} firms returned by CVR")
    print(f"  {h.dropped_reklamebeskyttet:>5} dropped: advertising-protected (may not be approached)")
    print(f"  {h.dropped_no_domain:>5} dropped: no website on file, cannot enrich or contact")
    print(f"  {len(h.firms):>5} firms with a contactable domain")

    if not h.firms:
        print("\nnothing to write", file=sys.stderr)
        return 1

    split: dict[str, int] = {}
    rows = []
    for firm in h.firms:
        provider = classify(firm.domain).provider
        split[provider.value] = split.get(provider.value, 0) + 1
        row = firm.to_dict()
        row["mail_provider"] = provider.value
        email = h.emails.get(firm.domain)
        row["contacts"] = [{"email": email}] if email else []
        rows.append(row)

    print("\nmail provider (G1):")
    for name, n in sorted(split.items(), key=lambda kv: -kv[1]):
        print(f"  {name:10s} {n:>5}")

    with_contact = sum(1 for r in rows if r["contacts"])
    print(f"\n{with_contact} / {len(rows)} firms carry an email in CVR")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="outreach-engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("counts", help="live Danish registry counts per vertical")

    sub.add_parser("cvr-check", help="report whether CVR API access is working")

    ld = sub.add_parser("list-dk", help="build a Danish lead list from CVR")
    ld.add_argument("--vertical", default="accounting", choices=sorted(NACE))
    ld.add_argument("--out", type=Path, default=Path("segments/accounting-dk.json"))
    ld.add_argument("--min-seats", type=int, default=MIN_SEATS)
    ld.add_argument("--max-seats", type=int, default=MAX_SEATS)
    ld.add_argument("--kommune", nargs="*", default=None,
                    help="municipality codes; omit for all of Denmark")

    mx = sub.add_parser("mx", help="classify mail provider by MX record")
    mx.add_argument("domains", nargs="+")

    g = sub.add_parser("gate", help="apply the seven gates to a leads file")
    g.add_argument("leads", type=Path)

    b = sub.add_parser("build", help="gate, enrich and export an Instantly CSV")
    b.add_argument("leads", type=Path)
    b.add_argument("--variant", default="capacity")
    b.add_argument("--out", type=Path, default=Path("queue/campaign.csv"))
    b.add_argument("--allow-english-fallback", action="store_true",
                   help="send English where DA/LT copy is not yet proofread")

    a = p.parse_args(argv)

    if a.cmd == "counts":
        print("Denmark, enterprises per vertical (Statistics Denmark GF12):")
        for k, v in dk_firm_counts().items():
            print(f"  {k:16s} {v:>6,}")
        print("\nLithuania - no open API. Sources:")
        for k, v in lt_sources().items():
            print(f"  {k:11s} {v}")
        return 0

    if a.cmd == "cvr-check":
        return _cvr_check()

    if a.cmd == "list-dk":
        return _list_dk(a)

    if a.cmd == "mx":
        for d in a.domains:
            r = classify(d)
            flag = "OK " if r.passes_g1 else "   "
            print(f"{flag}{r.domain:32s} {r.provider.value:10s} {', '.join(r.hosts[:2])}")
        return 0

    firms = _load_firms(a.leads)
    for firm, _ in firms:
        if firm.domain:
            firm.provider = classify(firm.domain).provider

    kept, dropped = partition([f for f, _ in firms])
    print(f"qualified {len(kept)} / {len(firms)}")
    for firm, verdict in dropped:
        print(f"  DROP {firm.name}: {verdict.rejected_for}")

    if a.cmd == "gate":
        return 0

    by_domain = {f.domain: raw for f, raw in firms}
    contacts = []
    for firm in kept:
        raw = by_domain.get(firm.domain, {})
        for c in raw.get("contacts", []):
            contacts.append(Contact(
                firm=firm, email=c["email"],
                first_name=c.get("first_name", ""), last_name=c.get("last_name", ""),
                title=c.get("title", ""), linkedin=c.get("linkedin", ""),
            ))

    if not contacts:
        print("no contacts on the qualified firms - nothing to export", file=sys.stderr)
        return 1

    fallback_used = False
    try:
        render(contacts[0], a.variant, strict=True)
    except UnproofreadCopy as e:
        if not a.allow_english_fallback:
            print(f"\nREFUSED: {e}", file=sys.stderr)
            return 2
        render(contacts[0], a.variant, strict=False)
        fallback_used = True
        print(f"\nWARNING: {contacts[0].language!r} copy for {a.variant!r} is not "
              f"proofread - sending English. The CSV language column will say "
              f"'en' so these leads are not routed to a local sequence.",
              file=sys.stderr)

    country = contacts[0].firm.country
    vertical = contacts[0].firm.vertical
    camp = Campaign(f"{vertical}-{country}-{a.variant}", vertical, country,
                    a.variant, contacts)
    out = to_csv(camp, a.out, rendered_language="en" if fallback_used else None)
    print(f"\ncell {camp.cell}: {len(contacts)} contacts -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
