"""The seam between this repo and the campaign ledger.

Batch B owns `campaign_db.py` and it lives in the `campaign-ledger` repo, which
this session cannot see or write to. So every ledger call in this repo goes
through here, and here alone.

The import is defensive on purpose. If `campaign_db` is importable we delegate to
it and nothing in this module runs. If it is not, a shim takes over that logs the
exact call it would have made and keeps just enough local state for dedup to
behave the way the real ledger would. Either way the finders, loaders and tests
run, which is the point: Batch C must not be blocked on Batch B finishing.

Wiring the real thing in is one step: put `campaign_db.py` on the import path.
No edit here. `using_real_ledger()` reports which half is live.

The eleven function names below are fixed by Batch B and are not negotiable:

    upsert_company, upsert_contact, log_touch, record_reply, insert_lead,
    upsert_content, snapshot_content_stats, snapshot_ad_stats,
    get_market_funnel, get_channel_funnel, get_content_perf
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("ledger")

ROOT = Path(__file__).resolve().parent.parent

# Where the shim keeps its state. Gitignored: it stands in for a database, and a
# database does not belong in git. Dedup across two runs of the finder is proved
# against this store when the real ledger is absent.
SHIM_DIR = Path(os.environ.get("LEDGER_SHIM_DIR", ROOT / ".ledger-shim"))


# --------------------------------------------------------------------------
# Column names.
#
# HONESTY NOTE. The batch instructions said these lists are in the Batch C spec.
# They are not: `C-outreach-engine.md` names `campaign.companies`,
# `campaign.contacts` and `campaign.touches` but never enumerates their columns,
# and this session was restricted to two spec files, so the real lists could not
# be read from `B-ledger.md` either. See BLOCKED.md B12.
#
# What is below is therefore derived from three things that ARE in the specs:
# the shared qualifier payload contract in `00-START-HERE.md` (market, locale,
# utm, team_size, email_client, role and their exact enum values), the two
# column names the Batch C spec states outright for `campaign.touches`
# (`replied_at` and `reply_sentiment`), and the gates this repo already encodes.
#
# They live in one dict each so reconciling with Batch B is a single edit here
# and nothing downstream changes.
# --------------------------------------------------------------------------

COMPANY_COLUMNS = (
    "market",            # dk | lt | global
    "segment",           # accounting | insurance | housing_admin
    "company_name",
    "domain",
    "country",           # ISO-3166 alpha-2
    "city",
    "mail_provider",     # microsoft | google | other | unknown
    "team_size",         # 1-9 | 10-24 | 25-49 | 50+ , from the qualifier contract
    "employees_est",     # integer best guess behind the band, null when unknown
    "dev_team_signal",   # 0.0 clean to 1.0 almost certainly has developers
    "fit_score",         # 0.0 to 1.0, the gate's own score
    "source",            # icp_finder:<market>
    "stage",             # discovered | queued | contacted | qualified | too_small | disqualified
    "notes",
    "first_seen_at",
    "updated_at",
)

CONTACT_COLUMNS = (
    "company_domain",    # the join key the finder can actually supply
    "first_name",
    "last_name",
    "role",              # owner_partner | ops_office_manager | it_admin | other
    "title",
    "work_email",
    "phone",
    "linkedin_url",
    "market",
    "locale",            # en | da | lt
    "email_ok",          # false for every dk contact, permanently. See load_instantly.py
    "created_at",
)

TOUCH_COLUMNS = (
    "company_domain",
    "work_email",
    "channel",           # linkedin | email | phone
    "step",              # 1..4
    "sequence_id",       # e.g. linkedin_da
    "market",
    "locale",
    "utm_content",       # {market}_{step}
    "status",            # planned | sent | bounced | skipped
    "sent_at",
    "replied_at",        # stated in the Batch C spec
    "reply_sentiment",   # stated in the Batch C spec, one of the six taxonomy values
    "created_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# The defensive import
# --------------------------------------------------------------------------

try:  # pragma: no cover - depends on whether Batch B has landed
    import campaign_db as _real  # type: ignore
except ImportError:
    _real = None


def using_real_ledger() -> bool:
    """True when Batch B's campaign_db is importable and being delegated to."""
    return _real is not None


def backend_name() -> str:
    return "campaign_db" if using_real_ledger() else "shim"


# --------------------------------------------------------------------------
# The shim
# --------------------------------------------------------------------------

class _Shim:
    """Stands in for campaign_db. Logs every call, persists just enough for dedup.

    It is not a database and does not pretend to be one. It keeps a domain index
    so `upsert_company` is genuinely idempotent, which is what makes "run the
    list builder twice and nothing is added" a real test rather than a hopeful
    one, and it appends every call to a JSONL trail so a dry run can be read
    back afterwards.
    """

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "companies.json"
        self.trail_path = self.dir / "calls.jsonl"
        self.companies: dict[str, dict[str, Any]] = {}
        if self.index_path.exists():
            try:
                self.companies = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # A truncated index must not take the run down. Start clean and
                # say so; worst case is one duplicate write, not a crash.
                log.warning("ledger shim index was unreadable, starting empty")
                self.companies = {}

    def _record(self, fn: str, payload: dict[str, Any]) -> None:
        line = json.dumps({"at": _now(), "fn": fn, "payload": payload},
                          ensure_ascii=False, sort_keys=True)
        with self.trail_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        log.info("[shim] %s %s", fn, json.dumps(payload, ensure_ascii=False)[:200])

    def _flush(self) -> None:
        self.index_path.write_text(
            json.dumps(self.companies, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def upsert_company(self, **row: Any) -> dict[str, Any]:
        domain = (row.get("domain") or "").strip().lower()
        if not domain:
            raise ValueError("upsert_company needs a domain, it is the identity")
        created = domain not in self.companies
        existing = self.companies.get(domain, {})
        merged = {**existing, **row}
        merged.setdefault("first_seen_at", _now())
        merged["updated_at"] = _now()
        self.companies[domain] = merged
        self._flush()
        self._record("upsert_company", {"domain": domain, "created": created})
        return {**merged, "created": created}

    def __getattr__(self, name: str):
        # Every other ledger function logs and returns something harmless.
        # Readers return empty, writers return an ack. Nothing raises, because a
        # missing ledger must degrade the run, not end it.
        def _call(*args: Any, **kwargs: Any):
            payload = {"args": [str(a)[:120] for a in args], "kwargs": kwargs}
            self._record(name, payload)
            if name.startswith("get_"):
                return []
            return {"ok": True, "backend": "shim", "fn": name}
        return _call


_shim = _Shim(SHIM_DIR)


def _dispatch(name: str, *args: Any, **kwargs: Any):
    target = getattr(_real, name) if _real is not None else getattr(_shim, name)
    return target(*args, **kwargs)


# --------------------------------------------------------------------------
# The eleven. Names fixed by Batch B.
# --------------------------------------------------------------------------

def upsert_company(**row: Any) -> dict[str, Any]:
    """Write or update one `campaign.companies` row. Idempotent on `domain`.

    Returns the stored row plus `created`, which is True only the first time a
    domain is seen. The finder uses that flag for its dedup count.
    """
    return _dispatch("upsert_company", **row)


def upsert_contact(**row: Any) -> dict[str, Any]:
    return _dispatch("upsert_contact", **row)


def log_touch(**row: Any) -> dict[str, Any]:
    return _dispatch("log_touch", **row)


def record_reply(**row: Any) -> dict[str, Any]:
    return _dispatch("record_reply", **row)


def insert_lead(**row: Any) -> dict[str, Any]:
    return _dispatch("insert_lead", **row)


def upsert_content(**row: Any) -> dict[str, Any]:
    return _dispatch("upsert_content", **row)


def snapshot_content_stats(**row: Any) -> dict[str, Any]:
    return _dispatch("snapshot_content_stats", **row)


def snapshot_ad_stats(**row: Any) -> dict[str, Any]:
    return _dispatch("snapshot_ad_stats", **row)


def get_market_funnel(*args: Any, **kwargs: Any):
    return _dispatch("get_market_funnel", *args, **kwargs)


def get_channel_funnel(*args: Any, **kwargs: Any):
    return _dispatch("get_channel_funnel", *args, **kwargs)


def get_content_perf(*args: Any, **kwargs: Any):
    return _dispatch("get_content_perf", *args, **kwargs)


def reset_shim() -> None:
    """Wipe the shim's local state. Tests only. No effect on a real ledger."""
    if using_real_ledger():
        raise RuntimeError("reset_shim() must never run against the real ledger")
    _shim.companies = {}
    _shim._flush()
    if _shim.trail_path.exists():
        _shim.trail_path.unlink()
