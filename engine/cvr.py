"""CVR company-register client - the route from a registry count to real firms.

`registry.py` answers "how many accounting firms are there in Denmark?" from
Statistics Denmark. This module answers "which ones?", which is the question
list building actually needs.

The only official route that filters companies by industry code, employee band
and municipality is the Danish Business Authority's system-to-system CVR API:

    POST http://distribution.virk.dk/cvr-permanent/virksomhed/_search

It is free but **credentialed** (HTTP Basic, realm "Beskyttet adgang"). See
`docs/CVR-ACCESS.md` for how to get a username and password - it is an email to
Erhvervsstyrelsen and a signed declaration, not a purchase.

Two things this module refuses to do, both deliberate:

* **No fallback data source.** With no credentials it raises. It does not fall
  back to a scraper, a third-party API or an estimate. The same reasoning as
  `registry.lt_sources()`: a plausible-looking list is worse than an honest
  gap, because the list gets emailed.
* **No advertising-protected firms.** CVR marks firms that have opted out of
  marketing approaches with `reklamebeskyttet`. They are dropped here, before
  the gate ever sees them, and the drop is counted so it shows up in the
  report. This is a condition of the data access, not a preference.

Field paths follow the published CVR Vrvirksomhed schema. They have not been
exercised against a live response - see the note in docs/CVR-ACCESS.md.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator

from engine.model import Firm

CVR_SEARCH_URL = "http://distribution.virk.dk/cvr-permanent/virksomhed/_search"

# Vrvirksomhed field paths, as published in the CVR schema.
_META = "Vrvirksomhed.virksomhedMetadata"
F_BRANCHEKODE = f"{_META}.nyesteHovedbranche.branchekode"
F_STATUS = f"{_META}.sammensatStatus"
F_KOMMUNE = f"{_META}.nyesteBeliggenhedsadresse.kommune.kommuneKode"
F_BAND_YEAR = f"{_META}.nyesteAarsbeskaeftigelse.intervalKodeAntalAnsatte"
F_BAND_MONTH = f"{_META}.nyesteErstMaanedsbeskaeftigelse.intervalKodeAntalAnsatte"

# CVR employee interval codes -> (low, high). high None = open-ended.
# CVR reports a band far more often than an exact headcount, so the band is the
# real filter; the exact count, when present, is preferred downstream.
EMPLOYEE_BANDS: dict[str, tuple[int, int | None]] = {
    "ANTAL_0_0": (0, 0),
    "ANTAL_1_1": (1, 1),
    "ANTAL_2_4": (2, 4),
    "ANTAL_5_9": (5, 9),
    "ANTAL_10_19": (10, 19),
    "ANTAL_20_49": (20, 49),
    "ANTAL_50_99": (50, 99),
    "ANTAL_100_199": (100, 199),
    "ANTAL_200_499": (200, 499),
    "ANTAL_500_999": (500, 999),
    "ANTAL_1000_": (1000, None),
}


def bands_within(min_seats: int, max_seats: int) -> list[str]:
    """Interval codes wholly inside [min_seats, max_seats].

    Wholly, not overlapping: ANTAL_5_9 is excluded from a 10+ list because some
    of its firms are under the G4 floor, and ANTAL_200_499 is excluded from a
    200-ceiling list because some of its firms are over the G7 ceiling. Taking
    a partially-overlapping band would put firms in the campaign that the gate
    exists to keep out, and CVR gives no way to split a band.
    """
    out = []
    for code, (low, high) in EMPLOYEE_BANDS.items():
        if low >= min_seats and high is not None and high <= max_seats:
            out.append(code)
    return out


class MissingCredentials(RuntimeError):
    """No CVR credentials. Raised rather than silently degrading the source."""


@dataclass(frozen=True)
class Credentials:
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "Credentials":
        user = os.environ.get("CVR_USER", "").strip()
        password = os.environ.get("CVR_PASSWORD", "").strip()
        if not user or not password:
            raise MissingCredentials(
                "CVR_USER / CVR_PASSWORD are not set.\n"
                "The CVR company index is free but credentialed. To get access, "
                "email cvrselvbetjening@erst.dk and sign the declaration they "
                "send back. Full instructions: docs/CVR-ACCESS.md\n"
                "There is no sanctioned unauthenticated route to per-company "
                "records, and this engine will not substitute one."
            )
        return cls(user, password)

    @property
    def basic_auth(self) -> str:
        raw = f"{self.user}:{self.password}".encode()
        return "Basic " + base64.b64encode(raw).decode()


def build_query(
    branchekode: str,
    bands: list[str],
    *,
    kommune_koder: list[str] | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    """The Elasticsearch query for one vertical at one seat range."""
    must: list[dict[str, Any]] = [
        {"term": {F_BRANCHEKODE: branchekode}},
        # A firm's band may be recorded annually or monthly; either qualifies.
        {"bool": {"minimum_should_match": 1, "should": [
            {"terms": {F_BAND_YEAR: bands}},
            {"terms": {F_BAND_MONTH: bands}},
        ]}},
    ]
    if active_only:
        must.append({"term": {F_STATUS: "NORMAL"}})
    if kommune_koder:
        must.append({"terms": {F_KOMMUNE: kommune_koder}})
    return {"query": {"bool": {"must": must}}}


@dataclass
class Harvest:
    """What a search returned, including what it threw away and why.

    The drop counts are reportable output, not diagnostics. A list of 300 firms
    means something different if 40 were dropped for advertising protection.
    """
    firms: list[Firm] = field(default_factory=list)
    seen: int = 0
    dropped_reklamebeskyttet: int = 0
    dropped_no_domain: int = 0
    emails: dict[str, str] = field(default_factory=dict)   # domain -> CVR email

    @property
    def dropped(self) -> int:
        return self.dropped_reklamebeskyttet + self.dropped_no_domain


def _current(entries: Any) -> str:
    """Latest still-valid, non-secret value from a CVR contact-info list.

    CVR keeps contact details as a history: each entry carries a validity
    period and a `hemmelig` (secret) flag. Only an entry that is both current
    and not marked secret may be used.
    """
    if not isinstance(entries, list):
        return ""
    for e in reversed(entries):
        if not isinstance(e, dict) or e.get("hemmelig"):
            continue
        period = e.get("periode") or {}
        if period.get("gyldigTil") is not None:
            continue
        value = (e.get("kontaktoplysning") or "").strip()
        if value:
            return value
    return ""


def to_domain(website: str) -> str:
    """Bare registrable host from whatever CVR holds as a website.

    CVR's `hjemmeside` is free text - it holds 'www.x.dk', 'http://x.dk/kontakt'
    and 'x.dk' interchangeably. The MX lookup in enrich.py needs the bare host.
    """
    s = (website or "").strip().lower()
    if not s:
        return ""
    for scheme in ("https://", "http://"):
        s = s.removeprefix(scheme)
    s = s.split("/")[0].split("?")[0].split("@")[-1]
    s = s.removeprefix("www.").strip(".")
    return s if "." in s and " " not in s else ""


def _employees(meta: dict[str, Any]) -> int | None:
    """Exact headcount when CVR has one, else the band's lower bound.

    The lower bound is the conservative choice: it can only push a firm below
    the G4 floor, never fabricate its way over it. It is only ever reached for
    a band already filtered to sit wholly inside the seat range, so it cannot
    smuggle an under-10 firm in. Returning None where CVR is silent is
    deliberate - the gate treats unknown as a soft downrank, not as zero.
    """
    for key in ("nyesteAarsbeskaeftigelse", "nyesteErstMaanedsbeskaeftigelse"):
        block = meta.get(key) or {}
        exact = block.get("antalAnsatte")
        if isinstance(exact, int) and exact > 0:
            return exact
    for key in ("nyesteAarsbeskaeftigelse", "nyesteErstMaanedsbeskaeftigelse"):
        block = meta.get(key) or {}
        band = EMPLOYEE_BANDS.get(block.get("intervalKodeAntalAnsatte") or "")
        if band:
            return band[0]
    return None


def to_firm(source: dict[str, Any], vertical: str) -> tuple[Firm | None, str]:
    """Map one CVR hit to a Firm. Returns (firm, drop_reason).

    `has_dev_team` is left None on purpose. CVR cannot answer G6 - it is a
    judgement call from the firm's own site and job ads - and guessing False
    would turn an unassessed gate into a passed one.
    """
    v = source.get("Vrvirksomhed") or source
    meta = v.get("virksomhedMetadata") or {}

    if v.get("reklamebeskyttet"):
        return None, "reklamebeskyttet"

    domain = to_domain(_current(v.get("hjemmeside")))
    if not domain:
        return None, "no domain in CVR"

    address = meta.get("nyesteBeliggenhedsadresse") or {}
    branch = meta.get("nyesteHovedbranche") or {}
    code = str(branch.get("branchekode") or "")

    firm = Firm(
        name=(meta.get("nyesteNavn") or {}).get("navn", "") or "",
        domain=domain,
        country="DK",
        vertical=vertical,
        nace=f"{code[:2]}.{code[2:4]}" if len(code) >= 4 else code,
        employees=_employees(meta),
        city=address.get("postdistrikt", "") or "",
        registry_id=f"DK{v.get('cvrNummer', '')}",
        has_dev_team=None,
        source="CVR cvr-permanent/virksomhed",
    )
    return firm, ""


def _post(query: dict[str, Any], creds: Credentials, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        CVR_SEARCH_URL,
        data=json.dumps(query).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": creds.basic_auth},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise MissingCredentials(
                "CVR rejected the credentials (401). Check CVR_USER / "
                "CVR_PASSWORD, and that the access has been activated. "
                "See docs/CVR-ACCESS.md"
            ) from e
        raise


def iter_hits(
    query: dict[str, Any],
    creds: Credentials,
    *,
    page: int = 100,
    timeout: float = 60.0,
) -> Iterator[dict[str, Any]]:
    """Page through a CVR search.

    Sorted by CVR number and paged with `search_after` rather than `from`,
    which keeps paging stable and stays clear of the 10,000-hit deep-paging
    ceiling. Erhvervsstyrelsen reserves the right to block inefficient clients,
    so this is the polite shape as well as the correct one.
    """
    after: list[Any] | None = None
    while True:
        body = dict(query)
        body["size"] = page
        body["sort"] = [{"Vrvirksomhed.cvrNummer": "asc"}]
        if after is not None:
            body["search_after"] = after

        hits = (_post(body, creds, timeout).get("hits") or {}).get("hits") or []
        if not hits:
            return
        for hit in hits:
            yield hit.get("_source") or {}
        after = hits[-1].get("sort")
        if after is None:
            return


def harvest(
    branchekode: str,
    vertical: str,
    *,
    min_seats: int,
    max_seats: int,
    kommune_koder: list[str] | None = None,
    creds: Credentials | None = None,
) -> Harvest:
    """Fetch every firm in one vertical inside a seat range. Needs credentials."""
    creds = creds or Credentials.from_env()
    bands = bands_within(min_seats, max_seats)
    if not bands:
        raise ValueError(f"no CVR employee band sits inside {min_seats}-{max_seats}")

    query = build_query(branchekode, bands, kommune_koder=kommune_koder)
    result = Harvest()
    for source in iter_hits(query, creds):
        result.seen += 1
        firm, reason = to_firm(source, vertical)
        if firm is None:
            if reason == "reklamebeskyttet":
                result.dropped_reklamebeskyttet += 1
            else:
                result.dropped_no_domain += 1
            continue
        result.firms.append(firm)
        email = _current((source.get("Vrvirksomhed") or source).get("elektroniskPost"))
        if email:
            result.emails[firm.domain] = email
    return result
