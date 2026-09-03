"""ICP discovery for the three campaign markets.

Search -> Microsoft 365 MX gate -> ledger dedup -> soft signals -> dated CSV.

## What this extends, and what it does not

The spec describes an existing `icp_finder.py` doing Google Custom Search -> MX
lookup -> CSV, and says to extend it rather than rewrite it. That file is not in
this container (`find / -name "icp_finder*"` found nothing) and could not be
extended, but its two halves were handled separately:

* **The MX half already exists here** as `engine/enrich.py` and `engine/gate.py`,
  and it was extended, not replaced. This module imports and calls them. The one
  change made to `enrich.py` was adding the `.mx.microsoft` signature, because
  probing 84 real ICP domains showed real Microsoft 365 firms
  (`redmark.dk`, `vbtm.nl`) were being classified OTHER and failing the hard gate.
* **The search half is new code**, written against the exact `leads_*.csv` column
  contract recovered from the two real output files in the Drive "DoviLoop Ops"
  folder, so old and new files stay interchangeable.

## Gates, in the order the spec sets

1. Hard: MX resolves to Microsoft 365. Real DNS, every run, fixtures included.
2. Hard: not already in `campaign.companies`. Dedup through `campaign_db.py`.
3. Soft: no dev team. Scored from the company's own public site, never blocking.
4. Soft: size estimate from the site.

Company-level public data only. No LinkedIn scraping, that stays in DSD.

## Usage

    python3 -m engine.icp_finder --market dk
    python3 -m engine.icp_finder --all --probe
    python3 -m engine.icp_finder --market lt --no-probe --lists-dir /tmp/x
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml

from engine import ledger
from engine.enrich import Provider, classify
from engine.gate import evaluate
from engine.model import Firm
from engine.signals import SiteProfile, dev_team_signal, size_estimate, to_band

log = logging.getLogger("icp_finder")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config" / "queries"
FIXTURE_DIR = ROOT / "fixtures" / "serp"
LISTS_DIR = ROOT / "lists"
HOOKS_PATH = ROOT / "config" / "hooks.yaml"

MARKETS = ("dk", "lt", "global")

# The campaign's three segments map onto the three verticals engine/gate.py
# already knows. housing_admin is administrative: back-office work done for
# somebody else, which is exactly the 82.11 shape the gate encodes.
SEGMENT_TO_VERTICAL = {
    "accounting": "accounting",
    "insurance": "insurance",
    "housing_admin": "administrative",
}

LOCALE_BY_MARKET = {"dk": "da", "lt": "lt", "global": "en"}

# The first ten columns are the exact contract of the real leads_*.csv files
# found in Drive, in the same order, so Dovy's existing files still load and the
# new ones drop into the same sheet. Everything after is a campaign addition.
CSV_COLUMNS = [
    "date_added", "company", "domain", "country", "vertical", "est_size",
    "fit_score", "hook_seed", "status", "notes",
    # campaign additions
    "market", "segment", "locale", "team_size", "mail_provider", "mx_host",
    "dev_team_signal", "dev_team_reasons", "name_source", "source",
]

GOOGLE_CSE = "https://www.googleapis.com/customsearch/v1"

_UA = "Mozilla/5.0 (compatible; DoviLoop-ICP/1.0; +https://doviloop.dev)"
_CA = "/root/.ccr/ca-bundle.crt"

# Paths worth a second request when the homepage links to them.
_INTERESTING = re.compile(
    r"(about|om-os|om_os|/om/|apie|team|medarbejder|people|staff|komanda|"
    r"career|job|stilling|karriere|karjera|vacature|contact|kontakt)", re.I)
_HREF = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG = re.compile(r"<[^>]+>")


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    domain: str
    company: str
    segment: str
    country: str
    market: str
    query: str
    snippet: str = ""
    name_source: str = "derived"


def _domain_of(item: dict[str, Any]) -> str:
    raw = item.get("displayLink") or urllib.parse.urlparse(item.get("link", "")).netloc
    return raw.strip().lower().removeprefix("www.")


def load_config(market: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{market}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no query config for market {market!r} at {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def from_fixture(market: str) -> list[Candidate]:
    """Candidates from the recorded-shape stand-in. No API key needed."""
    path = FIXTURE_DIR / f"{market}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[Candidate] = []
    for response in payload["responses"]:
        for item in response["items"]:
            out.append(Candidate(
                domain=_domain_of(item),
                company=item.get("title", "").strip(),
                segment=response["segment"],
                country=response.get("country", ""),
                market=market,
                query=response.get("query", ""),
                snippet=item.get("snippet", ""),
                name_source=item.get("name_source", "derived"),
            ))
    return out


def from_search(market: str, cfg: dict[str, Any], *,
                api_key: str, cse_id: str) -> list[Candidate]:
    """Candidates from live Google Custom Search.

    Never runs in this batch: there is no GOOGLE_API_KEY in the session, so the
    caller falls back to the fixture. Kept a thin wrapper on purpose, because
    the only difference between the two paths is where the items come from.
    """
    search = cfg.get("search", {})
    hints = search.get("country_hints") or {"": ""}
    out: list[Candidate] = []
    for segment in cfg["segments"]:
        for query in segment["queries"]:
            for country, hint in hints.items():
                for page in range(search.get("pages_per_query", 1)):
                    params = {
                        "key": api_key, "cx": cse_id,
                        "q": f"{query} {hint}".strip(),
                        "num": search.get("results_per_query", 10),
                        "start": 1 + page * search.get("results_per_query", 10),
                    }
                    if search.get("gl"):
                        params["gl"] = search["gl"]
                    if search.get("lr"):
                        params["lr"] = search["lr"]
                    if search.get("cr"):
                        params["cr"] = search["cr"]
                    url = f"{GOOGLE_CSE}?{urllib.parse.urlencode(params)}"
                    try:
                        with urllib.request.urlopen(url, timeout=20) as resp:
                            payload = json.load(resp)
                    except Exception as exc:      # one bad page must not end the run
                        log.warning("search failed for %r: %s", query, exc)
                        continue
                    items = payload.get("items", [])
                    if not items:
                        break
                    for item in items:
                        out.append(Candidate(
                            domain=_domain_of(item),
                            company=item.get("title", "").strip(),
                            segment=segment["id"],
                            country=country or cfg["country_codes"][0],
                            market=market,
                            query=query,
                            snippet=item.get("snippet", ""),
                            name_source="search",
                        ))
    return out


# --------------------------------------------------------------------------
# Live probe of the company's own public site, for the soft signals
# --------------------------------------------------------------------------

def _get(url: str, timeout: float) -> str:
    ctx = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else None
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read(400_000).decode("utf-8", "ignore")


def _text_of(html: str) -> str:
    return _ANY_TAG.sub(" ", _TAG.sub(" ", html))


def probe_site(domain: str, *, timeout: float = 12.0, max_pages: int = 4) -> SiteProfile:
    """Read a company's own public pages for the two soft signals.

    Homepage first, then up to three pages it links to whose path looks like an
    about, team or careers page. Public and unauthenticated, company level only.
    A site that will not load is a data quality signal, not an error, so this
    never raises.
    """
    profile = SiteProfile(domain=domain)
    chunks: list[str] = []
    links: list[str] = []
    paths: list[str] = []

    try:
        home = _get(f"https://{domain}/", timeout)
    except Exception as exc:
        profile.notes.append(f"probe failed: {type(exc).__name__}")
        return profile

    chunks.append(_text_of(home))
    links.append(home)
    paths.append("/")

    seen: set[str] = set()
    for href in _HREF.findall(home):
        if not _INTERESTING.search(href):
            continue
        parsed = urllib.parse.urlparse(href)
        if parsed.netloc and domain not in parsed.netloc:
            continue
        path = parsed.path or "/"
        if path in seen or path == "/":
            continue
        seen.add(path)
        paths.append(path)
        if len(seen) > max_pages - 1:
            continue
        try:
            page = _get(urllib.parse.urljoin(f"https://{domain}/", path), timeout)
        except Exception:
            continue
        chunks.append(_text_of(page))
        links.append(page)

    profile.paths = tuple(paths)
    profile.text = " ".join(chunks)[:200_000]
    profile.links = " ".join(links)[:400_000]
    profile.notes.append(f"probed {min(len(seen), max_pages - 1) + 1} pages")
    return profile


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

@dataclass
class Row:
    candidate: Candidate
    provider: Provider
    mx_host: str
    employees: int | None
    size_reason: str
    dev_score: float
    dev_reasons: tuple[str, ...]
    fit: float
    gate_notes: str
    probe_notes: str
    passed_gate: bool = True


def _hook_seed(hooks: dict[str, Any], segment: str, locale: str) -> str:
    try:
        return " ".join(hooks["segments"][segment][locale]["pain"].split())
    except KeyError:
        return ""


def run_market(market: str, *, probe: bool = True, use_ledger: bool = True,
               lists_dir: Path | None = None, run_date: str | None = None,
               workers: int = 6) -> dict[str, Any]:
    cfg = load_config(market)
    locale = LOCALE_BY_MARKET[market]
    hooks = yaml.safe_load(HOOKS_PATH.read_text(encoding="utf-8"))
    exclude = set(cfg.get("search", {}).get("exclude_domains", []))

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    cse_id = os.environ.get("GOOGLE_CSE_ID", "")
    if api_key and cse_id:
        candidates = from_search(market, cfg, api_key=api_key, cse_id=cse_id)
        mode = "live search"
    else:
        candidates = from_fixture(market)
        mode = "fixture (no GOOGLE_API_KEY, see BLOCKED.md B3)"

    # In-run dedup before anything expensive. One domain, one candidate.
    unique: dict[str, Candidate] = {}
    excluded = 0
    for cand in candidates:
        if not cand.domain or cand.domain in exclude:
            excluded += 1
            continue
        unique.setdefault(cand.domain, cand)

    # Hard gate 1: Microsoft 365 by MX. Real DNS on every run.
    #
    # Retried once on UNKNOWN. UNKNOWN is what a DNS timeout looks like, and
    # under concurrency a handful of lookups time out on any given run. Left
    # unretried, a qualified Microsoft 365 firm gets silently dropped from the
    # list because the resolver was busy, which is the worst kind of bug: no
    # error, no crash, just a smaller list than you should have had. A domain
    # that genuinely has no MX resolves to UNKNOWN twice and costs one extra
    # query.
    def mx(cand: Candidate):
        result = classify(cand.domain, timeout=8.0)
        if result.provider is Provider.UNKNOWN:
            result = classify(cand.domain, timeout=8.0)
        return cand, result

    passed_mx: list[tuple[Candidate, Any]] = []
    failed_mx: list[tuple[Candidate, Any]] = []
    with ThreadPoolExecutor(workers) as pool:
        for cand, result in pool.map(mx, unique.values()):
            (passed_mx if result.provider is Provider.MICROSOFT
             else failed_mx).append((cand, result))

    # Soft signals. Live, public, company level.
    profiles: dict[str, SiteProfile] = {}
    if probe and passed_mx:
        with ThreadPoolExecutor(workers) as pool:
            for profile in pool.map(lambda p: probe_site(p[0].domain),
                                    passed_mx):
                profiles[profile.domain] = profile

    rows: list[Row] = []
    for cand, mxr in passed_mx:
        profile = profiles.get(cand.domain) or SiteProfile(domain=cand.domain)
        if cand.snippet:
            profile.text = f"{cand.snippet} {profile.text}"
        dev_score, dev_reasons = dev_team_signal(profile)
        employees, size_reason = size_estimate(profile)

        firm = Firm(
            name=cand.company, domain=cand.domain, country=cand.country,
            vertical=SEGMENT_TO_VERTICAL[cand.segment],
            employees=employees, provider=mxr.provider,
            # Never asserted True from a heuristic. The gate hard-fails on True,
            # and a scored guess is not grounds for a hard fail. See signals.py.
            has_dev_team=False if dev_score < 0.5 else None,
            source=f"icp_finder:{market}",
        )
        verdict = evaluate(firm)
        rows.append(Row(
            candidate=cand, provider=mxr.provider,
            mx_host=mxr.hosts[0] if mxr.hosts else "",
            employees=employees, size_reason=size_reason,
            dev_score=dev_score, dev_reasons=dev_reasons,
            # The dev-team signal is a soft penalty on the gate's own score, at
            # half weight, because it is a heuristic over three noisy proxies.
            # A firm the gate hard-failed scores zero regardless.
            fit=0.0 if not verdict.passed
                else round(max(0.0, verdict.score - 0.5 * dev_score), 3),
            gate_notes="; ".join(verdict.reasons) if verdict.reasons else "clean",
            probe_notes="; ".join(profile.notes),
            passed_gate=verdict.passed,
        ))

    # Hard gate 2: not already in campaign.companies. Dedup via campaign_db.
    #
    # A firm the ICP gate hard-failed (under 10 seats, over the 200-seat
    # sovereignty ceiling, in-house developers, off-ICP vertical) is still
    # written to the ledger, deliberately, with stage `disqualified`. Writing it
    # is what stops the next run rediscovering it and the run after that. It is
    # kept out of the outreach CSV, which is the list a human works from.
    new_rows: list[Row] = []
    duplicates: list[Row] = []
    gate_rejects: list[Row] = []
    for row in rows:
        if not row.passed_gate:
            gate_rejects.append(row)
        if not use_ledger:
            if row.passed_gate:
                new_rows.append(row)
            continue
        cand = row.candidate
        stored = ledger.upsert_company(
            market=market,
            segment=cand.segment,
            company_name=cand.company,
            domain=cand.domain,
            country=cand.country,
            city="",
            mail_provider=row.provider.value,
            team_size=to_band(row.employees),
            employees_est=row.employees,
            dev_team_signal=row.dev_score,
            fit_score=row.fit,
            source=f"icp_finder:{market}",
            stage="discovered" if row.passed_gate else "disqualified",
            notes=f"MX={row.mx_host}; {row.gate_notes}",
        )
        # A ledger that does not report `created` is assumed to have created the
        # row. Dedup still holds at the database level because it is an upsert;
        # only this run's "new" count would over-report.
        if not row.passed_gate:
            continue
        (new_rows if stored.get("created", True) else duplicates).append(row)

    out_path = write_csv(market, new_rows, hooks, locale,
                         lists_dir=lists_dir, run_date=run_date)

    summary = {
        "market": market,
        "mode": mode,
        "ledger_backend": ledger.backend_name(),
        "probed": bool(probe),
        "candidates": len(candidates),
        "excluded_directories": excluded,
        "unique_domains": len(unique),
        "passed_mx_gate": len(passed_mx),
        "failed_mx_gate": len(failed_mx),
        # UNKNOWN is "we could not tell", not "not Microsoft". Reported apart so
        # a run with a bad resolver is visible rather than looking like a market
        # that simply has fewer Microsoft shops in it.
        "undecidable_mx": sum(
            1 for _, r in failed_mx if r.provider is Provider.UNKNOWN),
        "failed_icp_gate": len(gate_rejects),
        "new": len(new_rows),
        "already_in_ledger": len(duplicates),
        "csv": str(out_path),
        "mx_rejects": sorted(
            f"{c.domain} ({r.provider.value})" for c, r in failed_mx),
        "gate_rejects": sorted(
            f"{r.candidate.domain} ({r.gate_notes})" for r in gate_rejects),
    }
    return summary


def write_csv(market: str, rows: Iterable[Row], hooks: dict[str, Any],
              locale: str, *, lists_dir: Path | None = None,
              run_date: str | None = None) -> Path:
    lists_dir = Path(lists_dir or LISTS_DIR)
    lists_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_date or date.today().isoformat()
    path = lists_dir / f"{market}-{stamp}.csv"

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (-r.fit, r.candidate.domain)):
            cand = row.candidate
            writer.writerow({
                "date_added": stamp,
                "company": cand.company,
                "domain": cand.domain,
                "country": cand.country,
                "vertical": SEGMENT_TO_VERTICAL[cand.segment],
                "est_size": row.employees if row.employees is not None else "",
                "fit_score": row.fit,
                "hook_seed": _hook_seed(hooks, cand.segment, locale),
                "status": "new",
                "notes": f"MX={row.mx_host}; size {row.size_reason}; "
                         f"{row.gate_notes}; {row.probe_notes}",
                "market": market,
                "segment": cand.segment,
                "locale": locale,
                "team_size": to_band(row.employees) or "",
                "mail_provider": row.provider.value,
                "mx_host": row.mx_host,
                "dev_team_signal": row.dev_score,
                "dev_team_reasons": "; ".join(row.dev_reasons),
                "name_source": cand.name_source,
                "source": f"icp_finder:{market}",
            })
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="icp_finder")
    parser.add_argument("--market", choices=MARKETS)
    parser.add_argument("--all", action="store_true", help="run all three markets")
    parser.add_argument("--probe", dest="probe", action="store_true", default=True,
                        help="read each company's own public site for soft signals (default)")
    parser.add_argument("--no-probe", dest="probe", action="store_false",
                        help="skip the site probe; deterministic, used by the tests")
    parser.add_argument("--no-ledger", dest="ledger", action="store_false", default=True,
                        help="skip the campaign.companies dedup write")
    parser.add_argument("--lists-dir", type=Path, default=None)
    parser.add_argument("--date", dest="run_date", default=None,
                        help="override the dated CSV stamp, for reproducible runs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    if not args.all and not args.market:
        parser.error("pass --market {dk,lt,global} or --all")

    markets = MARKETS if args.all else (args.market,)
    for market in markets:
        s = run_market(market, probe=args.probe, use_ledger=args.ledger,
                       lists_dir=args.lists_dir, run_date=args.run_date)
        print(f"\n=== {s['market']} ===")
        print(f"  source            {s['mode']}")
        print(f"  ledger            {s['ledger_backend']}")
        print(f"  candidates        {s['candidates']} "
              f"({s['excluded_directories']} directory hits dropped)")
        print(f"  unique domains    {s['unique_domains']}")
        print(f"  M365 hard gate    {s['passed_mx_gate']} pass, "
              f"{s['failed_mx_gate']} rejected "
              f"({s['undecidable_mx']} of those undecidable, retry them)")
        print(f"  ICP gate          {s['failed_icp_gate']} hard-failed "
              f"(written to the ledger as disqualified, kept out of the CSV)")
        print(f"  new this run      {s['new']}")
        print(f"  already in ledger {s['already_in_ledger']}")
        print(f"  csv               {s['csv']}")
        if s["mx_rejects"]:
            print(f"  rejected by MX    {', '.join(s['mx_rejects'])}")
        for line in s["gate_rejects"]:
            print(f"  ICP reject        {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
