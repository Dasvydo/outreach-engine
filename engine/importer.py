"""Ingest a third-party lead export into this repo's column contract.

Lead discovery moved out of this repo to AI Arc. `engine/icp_finder.py` is dead -
Google Custom Search can no longer search the open web - so this module is now
the front door: whatever AI Arc emits has to arrive here and leave in the shape
the rest of the pipeline reads.

WHY THIS IS ALIAS-DRIVEN RATHER THAN HARD-CODED
-----------------------------------------------
No AI Arc export has been seen yet. Rather than invent its column names and be
wrong, the importer resolves columns through an alias table and reports what it
could not place, so the first real file is a config edit rather than a rewrite.
`--mapping` overrides any of it from a YAML file when auto-detection misses.

WHAT IT GUARANTEES
------------------
Nothing is dropped silently. Every input row leaves through exactly one of four
outputs, and the counts always reconcile:

    leads     - canonical ten-column contract, ICP, in an allowed country
    contacts  - the person rows behind those leads, when the source carries them
    review    - could not be decided: ambiguous vertical, gateway-fronted domain,
                unresolved provider. NOT rejects. These are worth a second look.
    rejected  - out of ICP, out of market, or unusable, each with a named reason

THE TWO TRAPS MEASURED IN THE REAL FILES
----------------------------------------
Both come from Dovy's own Drive exports, read 2026-09-14.

1. `fit_score` scale. Those files score integer 1-5. This repo scores float
   0.0-1.0. `engine/ledger.py::fit_score` multiplies by 100 either way, so a
   5-of-5 lead would land in the ledger as 5% fit and every downstream ranking
   would invert, with no error raised anywhere. `1.0` is valid on both scales, so
   no per-value check can tell them apart - the scale is detected per FILE from
   the observed maximum and normalised here, at the boundary, which is the only
   place it can be done safely.

2. `real estate`. Not in VERTICALS, so `engine/gate.py` hard-rejects it - 7 of 12
   rows in one real file, 8 of 15 in the other. It is a vocabulary mismatch
   (`dacas.dk` is `administrative` here and `real estate` there) but the label
   also covers estate agents, who are genuinely off-ICP. So it is resolved by
   keyword against `config/vertical_map.yaml` and anything undecided goes to
   review rather than being guessed either way.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERTICAL_MAP = ROOT / "config" / "vertical_map.yaml"

# The canonical contract. The first ten are the leads_*.csv columns verified
# against two real Drive exports; see docs/IMPORT-CONTRACT.md.
LEAD_COLUMNS = [
    "date_added", "company", "domain", "country", "vertical", "est_size",
    "fit_score", "hook_seed", "status", "notes",
    # campaign additions, derived here
    "market", "segment", "locale", "team_size", "mail_provider", "mx_host",
    "dev_team_signal", "dev_team_reasons", "name_source", "source",
]

CONTACT_COLUMNS = [
    "company_domain", "company_name", "first_name", "last_name", "role",
    "title", "work_email", "phone", "linkedin_url", "market", "locale",
    "segment", "country",
]

# Countries that may receive cold email, set by Dovy 2026-09-14. The US is
# excluded by choice - too contested - and Denmark is excluded by law elsewhere
# and independently, in load_instantly.py, which is the control that actually
# matters and must not be weakened here or anywhere.
EMAIL_COUNTRIES = ("LT", "GB", "NL")

# Country spellings an external source might use.
_COUNTRY_ALIASES = {
    "UK": "GB", "UNITED KINGDOM": "GB", "GREAT BRITAIN": "GB", "ENGLAND": "GB",
    "SCOTLAND": "GB", "WALES": "GB", "NORTHERN IRELAND": "GB",
    "LITHUANIA": "LT", "LIETUVA": "LT",
    "NETHERLANDS": "NL", "THE NETHERLANDS": "NL", "HOLLAND": "NL", "NEDERLAND": "NL",
    "DENMARK": "DK", "DANMARK": "DK",
    "UNITED STATES": "US", "USA": "US", "U.S.": "US", "U.S.A.": "US",
}

# Ledger-compatible markets. engine/ledger.py validates against Batch B's enum
# ("dk", "lt", "global"), so GB and NL ride under "global" and keep their real
# identity in the country column rather than inventing a market B would reject.
_MARKET_BY_COUNTRY = {"DK": "dk", "LT": "lt"}
_LOCALE_BY_MARKET = {"dk": "da", "lt": "lt", "global": "en"}

_SEGMENT_BY_VERTICAL = {
    "accounting": "accounting",
    "insurance": "insurance",
    "administrative": "housing_admin",
}

# Source column name -> canonical name. Lowercased, non-alphanumerics stripped,
# so "Company Name", "company_name" and "companyName" all collapse together.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "company": ("company", "companyname", "name", "organisation", "organization",
                "firm", "business", "accountname", "employer"),
    "domain": ("domain", "website", "url", "companydomain", "websiteurl",
               "webdomain", "site", "homepage", "companywebsite"),
    "country": ("country", "countrycode", "companycountry", "location",
                "countryname", "hqcountry"),
    "vertical": ("vertical", "industry", "segment", "sector", "category",
                 "naicsdescription", "industryname", "sic"),
    "est_size": ("estsize", "employees", "employeecount", "headcount", "size",
                 "companysize", "numemployees", "staff", "employeerange"),
    "fit_score": ("fitscore", "score", "fit", "rating", "matchscore", "priority"),
    "hook_seed": ("hookseed", "hook", "angle", "personalisation", "personalization",
                  "icebreaker", "opener", "insight"),
    "notes": ("notes", "note", "comment", "comments", "description", "summary"),
    "city": ("city", "town", "companycity", "locality"),
    "date_added": ("dateadded", "date", "createdat", "created", "exportdate",
                   "foundat", "timestamp"),
    # contact-level
    "first_name": ("firstname", "givenname", "fname", "contactfirstname"),
    "last_name": ("lastname", "surname", "familyname", "lname", "contactlastname"),
    "full_name": ("fullname", "contactname", "personname", "contact"),
    "title": ("title", "jobtitle", "position", "role", "jobrole", "designation"),
    "work_email": ("workemail", "email", "emailaddress", "businessemail",
                   "contactemail", "primaryemail", "mail"),
    "phone": ("phone", "phonenumber", "telephone", "mobile", "tel", "contactphone"),
    "linkedin_url": ("linkedinurl", "linkedin", "linkedinprofile", "li",
                     "linkedinlink", "profileurl"),
}

# Job titles -> the shared qualifier contract's four roles.
_ROLE_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("owner_partner", ("owner", "partner", "founder", "ceo", "managing director",
                       "director", "principal", "president", "indehaver",
                       "direktorius", "vadovas", "eigenaar", "directeur")),
    ("it_admin", ("it ", "information technology", "systems", "cto", "sysadmin",
                  "infrastructure", "it-chef", "it manager")),
    ("ops_office_manager", ("office manager", "operations", "ops", "administrator",
                            "kontorchef", "administrationschef", "practice manager",
                            "office lead", "kantoormanager", "biuro vadov")),
)


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _norm_label(value: Any) -> str:
    s = re.sub(r"[\s_\-]+", " ", str(value or "").strip().lower())
    return s.strip()


@dataclass
class Rejection:
    row: int
    company: str
    domain: str
    reason: str


@dataclass
class ImportReport:
    total_rows: int = 0
    leads: int = 0
    contacts: int = 0
    review: int = 0
    rejected: int = 0
    fit_scale: str = "unknown"
    unmapped_columns: list[str] = field(default_factory=list)
    resolved_columns: dict[str, str] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)

    def reconciles(self) -> bool:
        return self.total_rows == self.leads + self.review + self.rejected

    def render(self) -> str:
        lines = [
            f"rows in            {self.total_rows}",
            f"  leads            {self.leads}",
            f"  review           {self.review}",
            f"  rejected         {self.rejected}",
            f"  contacts         {self.contacts}",
            f"fit_score scale    {self.fit_scale}",
        ]
        if self.missing_required:
            lines.append(f"MISSING REQUIRED   {', '.join(self.missing_required)}")
        if self.resolved_columns:
            lines.append("columns resolved:")
            for canon, src in sorted(self.resolved_columns.items()):
                lines.append(f"    {canon:14} <- {src}")
        if self.unmapped_columns:
            lines.append(f"columns ignored:   {', '.join(self.unmapped_columns)}")
        if self.reasons:
            lines.append("reasons:")
            for reason, n in sorted(self.reasons.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {n:5}  {reason}")
        if not self.reconciles():
            lines.append("!! counts do not reconcile - a row was lost")
        return "\n".join(lines)


def resolve_columns(
    fieldnames: Iterable[str], overrides: dict[str, str] | None = None
) -> tuple[dict[str, str], list[str]]:
    """Map source column names onto canonical names.

    Returns (canonical -> source name, unmapped source names). Overrides are
    applied first and win outright, so a `--mapping` file can always break a tie
    auto-detection gets wrong.
    """
    fieldnames = [f for f in fieldnames if f]
    resolved: dict[str, str] = {}
    taken: set[str] = set()

    for canon, src in (overrides or {}).items():
        if src in fieldnames:
            resolved[canon] = src
            taken.add(src)

    by_key = {}
    for f in fieldnames:
        by_key.setdefault(_norm_key(f), f)

    for canon, aliases in COLUMN_ALIASES.items():
        if canon in resolved:
            continue
        for alias in aliases:
            hit = by_key.get(alias)
            if hit and hit not in taken:
                resolved[canon] = hit
                taken.add(hit)
                break

    unmapped = [f for f in fieldnames if f not in taken]
    return resolved, unmapped


def detect_fit_scale(values: Iterable[Any]) -> str:
    """Decide a file's fit_score scale from its observed maximum.

    Per FILE, never per row: 1.0 is a legitimate value on both the 0-1 and the
    1-5 scale, so a row in isolation carries no information about which is meant.
    """
    seen: list[float] = []
    for v in values:
        try:
            seen.append(float(str(v).strip().replace(",", ".")))
        except (TypeError, ValueError):
            continue
    if not seen:
        return "unknown"
    top = max(seen)
    if top <= 1.0:
        return "unit"       # already 0.0-1.0
    if top <= 5.0:
        return "one_to_five"
    if top <= 100.0:
        return "percent"
    return "unknown"


def normalise_fit(value: Any, scale: str) -> float | None:
    """Put a fit score on this repo's 0.0-1.0 scale."""
    try:
        n = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if scale == "unit":
        out = n
    elif scale == "one_to_five":
        out = (n - 1.0) / 4.0        # 1 -> 0.0, 5 -> 1.0
    elif scale == "percent":
        out = n / 100.0
    else:
        return None
    return round(min(1.0, max(0.0, out)), 3)


def normalise_country(value: Any) -> str:
    raw = str(value or "").strip().upper().rstrip(".")
    if not raw:
        return ""
    if raw in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[raw]
    return raw[:2] if len(raw) >= 2 else ""


def market_for(country: str) -> str:
    return _MARKET_BY_COUNTRY.get(country, "global")


def locale_for(market: str) -> str:
    return _LOCALE_BY_MARKET.get(market, "en")


def load_vertical_map(path: Path | str | None = None) -> dict[str, Any]:
    path = Path(path or VERTICAL_MAP)
    if not path.exists():
        return {"direct": {}, "ambiguous": {}, "reject": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_vertical(
    label: Any, context: str = "", vmap: dict[str, Any] | None = None
) -> tuple[str | None, str]:
    """Map a source vertical label onto a canonical vertical.

    Returns (vertical or None, reason). None with a reason starting 'review:'
    means undecided rather than rejected - the caller must route it to review,
    not to the bin.
    """
    vmap = vmap if vmap is not None else load_vertical_map()
    key = _norm_label(label)
    if not key:
        return None, "review: no vertical on the row"

    direct = {_norm_label(k): v for k, v in (vmap.get("direct") or {}).items()}
    if key in direct:
        return direct[key], ""

    rejects = {_norm_label(x) for x in (vmap.get("reject") or [])}
    if key in rejects:
        return None, f"off-ICP vertical: {key!r}"

    ambiguous = {_norm_label(k): v for k, v in (vmap.get("ambiguous") or {}).items()}
    if key in ambiguous:
        rule = ambiguous[key] or {}
        haystack = _norm_label(f"{label} {context}")
        signals = rule.get("signals") or {}
        for kw in signals.get("exclude") or []:
            if _norm_label(kw) in haystack:
                return None, f"off-ICP: {key!r} matched exclude signal {kw!r}"
        for target, keywords in signals.items():
            if target == "exclude":
                continue
            for kw in keywords or []:
                if _norm_label(kw) in haystack:
                    return target, ""
        if (rule.get("default") or "review") == "review":
            return None, f"review: {key!r} is ambiguous and no signal matched"
        return rule["default"], ""

    return None, f"unknown vertical: {key!r}"


def split_name(first: str, last: str, full: str) -> tuple[str, str]:
    first, last, full = (first or "").strip(), (last or "").strip(), (full or "").strip()
    if first or last:
        return first, last
    if not full:
        return "", ""
    parts = full.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def guess_role(title: Any) -> str:
    t = _norm_label(title)
    if not t:
        return "other"
    for role, signals in _ROLE_SIGNALS:
        for s in signals:
            if s.strip() in t:
                return role
    return "other"


def clean_domain(value: Any) -> str:
    d = str(value or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split("?")[0].strip()
    d = d.removeprefix("www.")
    return d.strip(". ")


# --------------------------------------------------------------------------
# The import itself
# --------------------------------------------------------------------------

def _mx_lookup(domains: list[str], workers: int = 12, timeout: float = 6.0
               ) -> dict[str, Any]:
    """Resolve MX for many domains concurrently.

    Concurrency is bounded because this is a public resolver and a list run is
    thousands of domains; 12 is deliberately conservative. `engine/enrich.py`
    never raises, so a failure arrives as an UNKNOWN with a reason rather than
    killing the run.
    """
    from concurrent.futures import ThreadPoolExecutor
    from engine.enrich import classify, resolve_gateway

    def look(d: str):
        # The gateway second look costs one extra DNS query and is paid only by
        # the domains the MX could not place, so it is done here rather than
        # inside classify(). It can only promote to Microsoft; a domain it
        # cannot confirm stays parked for review.
        return resolve_gateway(classify(d, timeout=timeout), timeout=timeout)

    unique = sorted({d for d in domains if d})
    out: dict[str, Any] = {}
    if not unique:
        return out
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for domain, result in zip(unique, pool.map(look, unique)):
            out[domain] = result
    return out


def run_import(
    source: Path | str,
    outdir: Path | str,
    *,
    run_date: str,
    mapping: dict[str, str] | None = None,
    vmap: dict[str, Any] | None = None,
    check_mx: bool = True,
    mx_workers: int = 12,
    countries: tuple[str, ...] = EMAIL_COUNTRIES,
    source_tag: str = "ai_arc",
) -> ImportReport:
    """Read an arbitrary lead export and write the canonical four outputs.

    `run_date` is required rather than defaulted to today, so that a re-run
    reproduces the same filenames and the same `date_added`.
    """
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    vmap = vmap if vmap is not None else load_vertical_map()
    report = ImportReport()

    with source.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0].keys()) if rows else []

    report.total_rows = len(rows)
    resolved, unmapped = resolve_columns(fieldnames, mapping)
    report.resolved_columns = dict(resolved)
    report.unmapped_columns = unmapped
    report.missing_required = [c for c in ("company", "domain") if c not in resolved]

    def get(row: dict[str, str], canon: str) -> str:
        src = resolved.get(canon)
        return (row.get(src) or "").strip() if src else ""

    report.fit_scale = detect_fit_scale(get(r, "fit_score") for r in rows)

    # One batched DNS pass, rather than a lookup buried in the row loop.
    mx: dict[str, Any] = {}
    if check_mx and not report.missing_required:
        mx = _mx_lookup([clean_domain(get(r, "domain")) for r in rows], mx_workers)

    leads: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rejected: list[Rejection] = []

    def note(reason: str) -> None:
        key = reason.split(":")[0].strip() if ":" in reason else reason
        report.reasons[key] = report.reasons.get(key, 0) + 1

    for i, row in enumerate(rows, start=1):
        company = get(row, "company")
        domain = clean_domain(get(row, "domain"))
        notes = get(row, "notes")

        if report.missing_required:
            rejected.append(Rejection(i, company, domain, "source is missing a required column"))
            note("missing required column")
            continue
        if not domain:
            rejected.append(Rejection(i, company, domain, "no domain - cannot enrich or contact"))
            note("no domain")
            continue

        country = normalise_country(get(row, "country"))
        if country not in countries:
            reason = (f"country {country or '??'} is not in the email allowlist "
                      f"({', '.join(countries)})")
            rejected.append(Rejection(i, company, domain, reason))
            note("country not in allowlist")
            continue

        vertical, why = resolve_vertical(get(row, "vertical"), f"{company} {notes}", vmap)
        market = market_for(country)
        locale = locale_for(market)

        base = {
            "date_added": get(row, "date_added") or run_date,
            "company": company,
            "domain": domain,
            "country": country,
            "est_size": get(row, "est_size"),
            "hook_seed": get(row, "hook_seed"),
            "notes": notes,
            "market": market,
            "locale": locale,
            "source": f"{source_tag}:{market}",
        }

        if vertical is None:
            if why.startswith("review:"):
                review.append({**base, "vertical": get(row, "vertical"),
                               "review_reason": why})
                note(why)
            else:
                rejected.append(Rejection(i, company, domain, why))
                note(why)
            continue

        result = mx.get(domain)
        provider = result.provider.value if result else "unknown"
        mx_host = result.hosts[0] if result and result.hosts else ""

        if check_mx and result is not None and result.needs_review:
            detail = result.vendor or result.reason.value or provider
            review.append({**base, "vertical": vertical, "mail_provider": provider,
                           "mx_host": mx_host,
                           "review_reason": f"review: provider unresolved ({detail})"})
            note(f"review: provider unresolved ({provider})")
            continue

        if check_mx and provider != "microsoft":
            rejected.append(Rejection(i, company, domain,
                                      f"not Microsoft 365 (mail provider: {provider})"))
            note("not Microsoft 365")
            continue

        fit = normalise_fit(get(row, "fit_score"), report.fit_scale)
        try:
            est = int(float(get(row, "est_size") or 0)) or None
        except (TypeError, ValueError):
            est = None

        from engine.signals import to_band
        leads.append({
            **base,
            "vertical": vertical,
            "fit_score": "" if fit is None else fit,
            "status": "new",
            "segment": _SEGMENT_BY_VERTICAL.get(vertical, vertical),
            "team_size": to_band(est) or "",
            "mail_provider": provider,
            "mx_host": mx_host,
            "dev_team_signal": "",
            "dev_team_reasons": "",
            "name_source": "ai_arc",
        })

        email = get(row, "work_email")
        if email and "@" in email:
            first, last = split_name(get(row, "first_name"), get(row, "last_name"),
                                     get(row, "full_name"))
            contacts.append({
                "company_domain": domain,
                "company_name": company,
                "first_name": first,
                "last_name": last,
                "role": guess_role(get(row, "title")),
                "title": get(row, "title"),
                "work_email": email,
                "phone": get(row, "phone"),
                "linkedin_url": get(row, "linkedin_url"),
                "market": market,
                "locale": locale,
                "segment": _SEGMENT_BY_VERTICAL.get(vertical, vertical),
                "country": country,
            })

    def write(path: Path, columns: list[str], data: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            for d in data:
                w.writerow({c: d.get(c, "") for c in columns})

    write(outdir / f"leads_{run_date}.csv", LEAD_COLUMNS, leads)
    write(outdir / f"contacts_{run_date}.csv", CONTACT_COLUMNS, contacts)
    write(outdir / f"review_{run_date}.csv",
          LEAD_COLUMNS + ["review_reason"], review)
    with (outdir / f"rejected_{run_date}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "company", "domain", "reason"])
        for r in rejected:
            w.writerow([r.row, r.company, r.domain, r.reason])

    report.leads = len(leads)
    report.contacts = len(contacts)
    report.review = len(review)
    report.rejected = len(rejected)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="import_leads",
        description="Ingest a third-party lead export into the leads_*.csv contract.")
    p.add_argument("source", help="the export CSV to read")
    p.add_argument("--outdir", default=str(ROOT / "lists"), help="where to write")
    p.add_argument("--run-date", required=True, help="YYYY-MM-DD, stamps the filenames")
    p.add_argument("--mapping", help="YAML of canonical->source column overrides")
    p.add_argument("--no-mx", action="store_true",
                   help="skip the MX gate (offline dry run; nothing is Microsoft-filtered)")
    p.add_argument("--workers", type=int, default=12, help="concurrent DNS lookups")
    p.add_argument("--countries", default=",".join(EMAIL_COUNTRIES),
                   help="comma-separated country allowlist")
    args = p.parse_args(argv)

    overrides = {}
    if args.mapping:
        overrides = yaml.safe_load(Path(args.mapping).read_text(encoding="utf-8")) or {}

    report = run_import(
        args.source, args.outdir,
        run_date=args.run_date,
        mapping=overrides,
        check_mx=not args.no_mx,
        mx_workers=args.workers,
        countries=tuple(c.strip().upper() for c in args.countries.split(",") if c.strip()),
    )
    print(report.render())
    if report.missing_required:
        return 2
    return 0 if report.reconciles() else 1


if __name__ == "__main__":
    raise SystemExit(main())
