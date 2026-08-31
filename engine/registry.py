"""Official-registry clients. Public data, no scraping, no vendor lock-in.

Denmark is the strong side: Statistics Denmark's StatBank API is open and needs
no key, and the CVR register is filterable by industry code, employee band and
municipality. Lithuania has no equivalent open API - rekvizitai.lt and the Bank
of Lithuania register are the practical sources, and the LT path is deliberately
left as an explicit gap rather than a fake implementation.
"""

from __future__ import annotations

import json
import urllib.request

STATBANK = "https://api.statbank.dk/v1/data"

# DB07 / NACE codes for the three locked verticals.
NACE = {
    "accounting": "692000",       # incl. audit + tax consultancy; 69002 = bookkeeping only
    "administrative": "821100",   # combined office administrative services
    "insurance": "662200",        # insurance agents and brokers
}

# Sector groupings used for the size distribution (table GF13).
SECTOR = {"accounting": "M", "administrative": "N", "insurance": "K"}


def dk_firm_counts(year: str = "2023", municipality: str = "000") -> dict[str, int]:
    """Number of Danish enterprises per locked vertical. Authoritative.

    municipality "000" = all Denmark. Table GF12.
    """
    body = {
        "table": "GF12", "format": "JSONSTAT", "lang": "en",
        "variables": [
            {"code": "KOMK", "values": [municipality]},
            {"code": "BRANCHEDB0710TIL127", "values": list(NACE.values())},
            {"code": "Tid", "values": [year]},
        ],
    }
    req = urllib.request.Request(
        STATBANK,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    ds = payload["dataset"]
    cat = ds["dimension"]["BRANCHEDB0710TIL127"]["category"]
    inverse = {v: k for k, v in cat["index"].items()}
    by_code = {inverse[i]: v for i, v in enumerate(ds["value"])}
    return {name: by_code.get(code, 0) for name, code in NACE.items()}


def dk_size_distribution(sector: str, year: str = "2023") -> dict[str, int]:
    """Enterprise counts by employee band for a DB07 19-grouping sector.

    The finest split DST publishes publicly is "<10" vs "10-49" - it cannot
    separate 5-9 from 1-4. Exact per-code, per-band counts need CVR API
    credentials (free, from the Danish Business Authority). Until then any
    10+ figure derived from this is an estimate and must be labelled as one.
    """
    body = {
        "table": "GF13", "format": "JSONSTAT", "lang": "en",
        "variables": [
            {"code": "BRANCHEDB0738", "values": [sector]},
            {"code": "ENHED", "values": ["AFI"]},
            {"code": "FIRMSTR", "values": ["TOT", "0000", "010", "101", "102", "103"]},
            {"code": "Tid", "values": [year]},
        ],
    }
    req = urllib.request.Request(
        STATBANK,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    ds = payload["dataset"]
    cat = ds["dimension"]["FIRMSTR"]["category"]
    inverse = {v: k for k, v in cat["index"].items()}
    return {cat["label"][inverse[i]]: v for i, v in enumerate(ds["value"])}


def lt_sources() -> dict[str, str]:
    """Lithuania has no open equivalent. These are the real routes.

    Not implemented as fetchers on purpose: a stub that returns plausible
    numbers is worse than an honest gap, because the numbers get quoted.
    """
    return {
        "rekvizitai": "https://rekvizitai.vz.lt - free company search, the practical tool",
        "jar": "https://www.registrucentras.lt - official register, formal extracts",
        "insurance": (
            "https://www.lb.lt/en/sfi-financial-market-participants - Bank of "
            "Lithuania. For insurance this is not a lead source, it is the "
            "ENTIRE market: 105 licensed intermediaries, enumerable by hand."
        ),
    }
