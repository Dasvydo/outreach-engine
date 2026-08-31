"""outreach-engine CLI.

    python -m engine.cli counts                    live DK registry counts
    python -m engine.cli mx <domain> [<domain>...] classify mail providers
    python -m engine.cli gate <leads.json>         apply G1-G7, report keep/drop
    python -m engine.cli build <leads.json> --variant capacity --out camp.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.enrich import classify
from engine.export import to_csv
from engine.gate import partition
from engine.model import Campaign, Contact, Firm
from engine.registry import dk_firm_counts, lt_sources
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="outreach-engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("counts", help="live Danish registry counts per vertical")

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

    strict = not a.allow_english_fallback
    try:
        render(contacts[0], a.variant, strict=strict)
    except UnproofreadCopy as e:
        print(f"\nREFUSED: {e}", file=sys.stderr)
        return 2

    country = contacts[0].firm.country
    vertical = contacts[0].firm.vertical
    camp = Campaign(f"{vertical}-{country}-{a.variant}", vertical, country,
                    a.variant, contacts)
    out = to_csv(camp, a.out)
    print(f"\ncell {camp.cell}: {len(contacts)} contacts -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
