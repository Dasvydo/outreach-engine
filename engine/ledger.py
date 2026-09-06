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

WHAT THIS MODULE TRANSLATES, AND WHY IT HAS TO
----------------------------------------------
This repo and the ledger were built in parallel and do not speak the same
dialect. This repo says `company_name`, `employees_est`, `mail_provider`,
`dev_team_signal`, `locale`, `step`; Batch B's `campaign_db.py` says `name`,
`est_size`, `uses_m365`, `has_dev_team`, `language`, `sequence_step`. Calling
B's functions with this repo's argument names is a TypeError on the first real
connection, and it was invisible while the shim - which accepts anything - was
the only backend anyone ran against.

So this file is a translator, not a passthrough. The `*_kwargs` builders map
one vocabulary onto the other; the shim still receives the untranslated row,
because its job is to be a readable record of what this repo meant. Four
company fields (`city`, `team_size`, `stage`, `notes`) and five touch fields
have no column on B's side and are folded into the `hook_seed` and `notes` text
columns rather than dropped - see BLOCKED.md C-B1 and C-B2 for the columns B
would need for them to be queryable again.

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
from typing import Any, Mapping

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
    "reply_sentiment",   # one of the six canonical values in SENTIMENTS below
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


# ==========================================================================
# THE TRANSLATION LAYER
#
# Reconciled against Batch B's real `campaign_db.py` and `001_schema.sql` on
# 2026-09-03. Before that reconciliation this repo called B's functions by the
# right NAMES with the wrong ARGUMENTS - `company_name=` where B wants `name=`,
# `employees_est=` where B wants `est_size=`, a whole `log_touch` payload with
# no `contact_id` in it at all. The shim accepted every one of them, so the
# suite was green and the first real call would have been a TypeError.
#
# The rule from here on: this repo keeps its own richer vocabulary (the
# COMPANY_COLUMNS / TOUCH_COLUMNS above, which carry city, stage, status and a
# scored dev-team signal that B has no column for), and everything is mapped to
# B's contract HERE, at the boundary, in the `*_kwargs` builders below. Those
# builders are pure functions on purpose: `tests/test_ledger_contract.py` binds
# their output against `inspect.signature` of B's real functions, loaded from
# the campaign-ledger repo by file path, so this class of drift cannot come
# back silently.
# ==========================================================================

# C says `housing_admin`; B's campaign.segment enum says `admin`. Same thing.
SEGMENT_TO_B = {
    "accounting": "accounting",
    "insurance": "insurance",
    "housing_admin": "admin",
    "admin": "admin",
}

# C says `linkedin` and lets `step` say which kind. B's campaign.touch_channel
# splits the connection request from the conversation that follows it, which is
# the more useful split - a connect that is never accepted and a DM that is
# never answered are different failures.
_B_CHANNELS = ("linkedin_connect", "linkedin_dm", "email", "phone")
_B_COMPANY_SOURCES = ("icp_finder", "linkedin", "inbound")
_B_MARKETS = ("dk", "lt", "global")
_B_LANGS = ("en", "da", "lt")

# The reply sentiment taxonomy. CANONICAL campaign-wide since 2026-09-06: these
# six ids are the ones in config/reply_taxonomy.yaml, and the ledger's
# campaign.reply_sentiment enum carries exactly the same six, so a sentiment
# crosses this seam as itself. No mapping, no renaming. The only thing done here
# is to refuse anything outside the six before it reaches the ledger, so a typo
# in a classifier fails with a readable message rather than as a Postgres enum
# cast error. `tests/test_ledger_contract.py` asserts the ledger client agrees.
# (BLOCKED.md B5 and C-B4, both resolved.)
SENTIMENTS = ("interested", "not_now", "not_a_fit", "referred", "objection",
              "unsubscribe")


class LedgerVocabularyMismatch(RuntimeError):
    """A value this repo uses is outside one of the shared enums."""


class LedgerContactUnresolved(RuntimeError):
    """Raised when a touch or a reply cannot be tied to a `campaign.contacts` row.

    B keys `campaign.touches` on `(contact_id, channel, sequence_step)` and the
    column is NOT NULL with a foreign key. This repo works from company domains
    and work emails, so the id has to be resolved or created first. When it
    cannot be - no domain, or no company name to create the firm under - the
    call stops here with this error instead of reaching B and failing as an
    opaque foreign-key violation, and instead of being dropped on the floor.
    """


# Domain -> campaign.companies.id, filled in by `upsert_company` as it goes so a
# later `log_touch` in the same process does not have to re-derive it. Empty in
# a fresh process, which is why `_resolve_contact_id` can also create the firm.
_COMPANY_IDS: dict[str, str] = {}


def _norm_domain(domain: Any) -> str:
    """B's `_normalise_domain`, kept in step so the cache keys agree with it."""
    if not domain:
        return ""
    value = str(domain).strip().lower()
    value = value.split("://")[-1].split("/")[0].split("?")[0]
    if "@" in value:
        value = value.rsplit("@", 1)[1]
    return value[4:] if value.startswith("www.") else value


def uses_m365(mail_provider: Any) -> bool | None:
    """`mail_provider` -> B's boolean `uses_m365`, by the repo's own MX gate.

    The gate in `icp_finder.run()` passes a firm when
    `result.provider is Provider.MICROSOFT` and nothing else, so that is exactly
    the test here. UNKNOWN is the one value that must not become False: it means
    NXDOMAIN, no MX, or a failed lookup - "we could not tell", not "not
    Microsoft" - and B's column is nullable precisely so that stays sayable.
    """
    if mail_provider is None:
        return None
    try:  # the enum when it is available, its string value when it is not
        from engine.enrich import Provider
        microsoft, unknown = Provider.MICROSOFT.value, Provider.UNKNOWN.value
    except Exception:  # pragma: no cover - only if dnspython is missing
        microsoft, unknown = "microsoft", "unknown"
    value = getattr(mail_provider, "value", mail_provider)
    value = str(value).strip().lower()
    if not value or value == unknown:
        return None
    return value == microsoft


def has_dev_team(dev_team_signal: Any) -> bool | None:
    """C's 0.0-1.0 score -> B's nullable boolean, by `icp_finder`'s own rule.

    `icp_finder` already refuses to assert True from a heuristic, because the
    gate hard-fails on True and a scored guess is not grounds for a hard fail:
    `has_dev_team=False if dev_score < 0.5 else None`. The same line, here, so
    the ledger and the gate cannot disagree about a firm. The number itself is
    not thrown away - when it is too high to say False it is written into
    `hook_seed` as `dev_signal=`, see `_hook_seed_with_overflow`.
    """
    if dev_team_signal is None:
        return None
    return False if float(dev_team_signal) < 0.5 else None


def fit_score(value: Any) -> int | None:
    """C scores 0.0-1.0; B's column is `integer` with a 0..100 check constraint."""
    if value is None or value == "":
        return None
    number = float(value)
    if number <= 1.0:
        number *= 100
    return max(0, min(100, int(round(number))))


def _hook_seed_with_overflow(row: Mapping[str, Any]) -> str | None:
    """Fold the fields B has no column for into the `hook_seed` text column.

    `campaign.companies` has no `city`, no `team_size`, no `stage` and no
    `notes`. Dropping them silently would lose the MX host and the gate's own
    verdict, which is the only record of WHY a firm was disqualified. Inventing
    columns is not this repo's call to make. So they go into the one free-text
    column that exists, in a readable `key=value` form, and the gap is named in
    BLOCKED.md C-B1 so it can be closed properly rather than forgotten.
    """
    parts: list[str] = []
    seed = (row.get("hook_seed") or "").strip()

    def add(key: str, value: Any) -> None:
        if value is None or value == "":
            return
        parts.append(f"{key}={value}")

    add("city", (row.get("city") or "").strip())
    add("team_size", row.get("team_size"))
    add("stage", row.get("stage"))
    # Only when the boolean could not carry it, see `has_dev_team`.
    signal = row.get("dev_team_signal")
    if signal is not None and float(signal) >= 0.5:
        add("dev_signal", round(float(signal), 3))
    add("notes", (row.get("notes") or "").strip())

    if not parts:
        return seed or None
    overflow = "; ".join(parts)
    return f"{seed} -- {overflow}" if seed else overflow


def company_kwargs(**row: Any) -> dict[str, Any]:
    """C's company vocabulary -> the exact keyword arguments B's
    `upsert_company(name, domain, market, *, segment, country, est_size,
    uses_m365, has_dev_team, fit_score, hook_seed, source, dsd_company_id)`
    accepts. Pure: no I/O, no ledger, safe to bind against in a test."""
    segment = row.get("segment")
    if segment is not None:
        segment = SEGMENT_TO_B.get(str(segment), str(segment))

    # C tags the source with the market it came from ("icp_finder:lt"); B's
    # campaign.company_source enum has three bare values, and the market is
    # already a column of its own, so the tag loses nothing.
    source = str(row.get("source") or "icp_finder").split(":")[0]
    if source not in _B_COMPANY_SOURCES:
        source = "icp_finder"

    out: dict[str, Any] = {
        "name": row.get("company_name") or row.get("name") or "",
        "domain": row.get("domain") or "",
        "market": row.get("market"),
        "segment": segment,
        "country": row.get("country") or None,
        "est_size": row.get("employees_est", row.get("est_size")),
        "uses_m365": uses_m365(row.get("mail_provider", row.get("uses_m365"))),
        "has_dev_team": has_dev_team(row.get("dev_team_signal",
                                             row.get("has_dev_team"))),
        "fit_score": fit_score(row.get("fit_score")),
        "hook_seed": _hook_seed_with_overflow(row),
        "source": source,
    }
    if row.get("dsd_company_id"):
        out["dsd_company_id"] = row["dsd_company_id"]
    return out


def touch_channel(channel: Any, step: Any = 1) -> str:
    """C's `linkedin` -> B's `linkedin_connect` (step 1) or `linkedin_dm`."""
    value = str(channel or "").strip().lower()
    if value in _B_CHANNELS:
        return value
    if value == "linkedin":
        return "linkedin_connect" if int(step or 1) <= 1 else "linkedin_dm"
    return value  # let B's own _check name the field in its error


def _touch_notes(row: Mapping[str, Any]) -> str | None:
    """Fold the touch fields B has no column for into `touches.notes`.

    `campaign.touches` is (contact_id, channel, sequence_step, language,
    sent_at, replied_at, reply_sentiment, notes). It has no `sequence_id`, no
    `utm_content`, no `status`, no `market` and no `work_email`. Every one of
    those is needed to read a funnel back - `utm_content` is the only link
    between a touch and the landing-page hit it produced - so they are written
    into `notes` rather than dropped, and named in BLOCKED.md C-B2.
    """
    parts: list[str] = []
    for key in ("sequence_id", "utm_content", "status", "market",
                "company_domain", "work_email", "ledger_stage", "classifier",
                "classifier_note"):
        value = row.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    existing = (row.get("notes") or "").strip()
    overflow = "; ".join(parts)
    if existing and overflow:
        return f"{existing} -- {overflow}"
    return existing or overflow or None


def touch_kwargs(contact_id: str, **row: Any) -> dict[str, Any]:
    """C's touch vocabulary -> B's `log_touch(contact_id, channel, language, *,
    sequence_step, sent_at, notes)`. Pure."""
    return {
        "contact_id": contact_id,
        "channel": touch_channel(row.get("channel"), row.get("step", 1)),
        # B calls it `language`; this repo calls it `locale` everywhere, and
        # both are the same three values en | da | lt.
        "language": row.get("locale") or row.get("language"),
        "sequence_step": int(row.get("step", row.get("sequence_step", 1)) or 1),
        "sent_at": row.get("sent_at"),
        "notes": _touch_notes(row),
    }


def reply_kwargs(contact_id: str, **row: Any) -> dict[str, Any]:
    """C's reply vocabulary -> B's `record_reply(contact_id, channel, sentiment,
    *, sequence_step, replied_at, notes, touch_id)`. Pure.

    `sync_replies.py` also carries `ledger_stage`, `classifier` and
    `classifier_note`. B has no column for any of them; they go into `notes`,
    which is the honest place for "a model said this, and here is which model".
    """
    sentiment = row.get("reply_sentiment") or row.get("sentiment")
    if sentiment is not None and sentiment not in SENTIMENTS:
        raise LedgerVocabularyMismatch(
            f"reply_sentiment={sentiment!r} is not one of the six canonical "
            f"reply values ({', '.join(SENTIMENTS)}). The list lives in "
            "config/reply_taxonomy.yaml and the ledger's campaign.reply_sentiment "
            "enum carries the same six; nothing outside it is written.")

    out = {
        "contact_id": contact_id,
        "channel": touch_channel(row.get("channel"), row.get("step", 1)),
        "sentiment": sentiment,
        "sequence_step": int(row.get("step", row.get("sequence_step", 1)) or 1),
        "replied_at": row.get("replied_at"),
        "notes": _touch_notes(row),
    }
    if row.get("touch_id"):
        out["touch_id"] = row["touch_id"]
    return out


def _resolve_contact_id(row: Mapping[str, Any]) -> str:
    """Find, or create, the `campaign.contacts` row this touch belongs to.

    Only ever called when the real ledger is live. Order:

      1. an explicit `contact_id`, if the caller already has one;
      2. an explicit `company_id`, or one this process cached when it upserted
         the firm, plus the work email -> `upsert_contact`;
      3. the company name and domain the contact row already carries ->
         `upsert_company` (idempotent on domain, so this is a merge and not a
         second row) -> `upsert_contact`.

    If none of those is possible it raises `LedgerContactUnresolved` naming what
    was missing. It never guesses an id and never returns None: a touch with a
    made-up contact would be worse than a touch that was never written.
    """
    if row.get("contact_id"):
        return str(row["contact_id"])

    domain = _norm_domain(row.get("company_domain") or row.get("domain")
                          or row.get("work_email"))
    market = row.get("market")
    email = (row.get("work_email") or row.get("email") or "").strip().lower()
    full_name = (row.get("full_name") or " ".join(
        p for p in (row.get("first_name") or "", row.get("last_name") or "")
        if p).strip()) or None
    linkedin_url = row.get("linkedin_url") or None

    if not (email or linkedin_url or full_name):
        raise LedgerContactUnresolved(
            "cannot log a touch: campaign.touches.contact_id is NOT NULL and "
            "this call carries no work_email, no linkedin_url and no name, so "
            "there is nothing to identify or create a contact with. Pass "
            "contact_id=, or a work_email. See BLOCKED.md C-B3.")

    company_id = row.get("company_id") or _COMPANY_IDS.get(domain)
    if not company_id:
        company_name = (row.get("company_name") or "").strip()
        if not (domain and company_name and market):
            raise LedgerContactUnresolved(
                "cannot log a touch: no contact_id and no company_id, and the "
                f"firm cannot be resolved either (domain={domain!r}, "
                f"company_name={company_name!r}, market={market!r}). "
                "campaign_db exposes no company reader, so the domain alone is "
                "not enough - pass company_name and market so the firm can be "
                "upserted, or pass contact_id. See BLOCKED.md C-B3.")
        stored = _real.upsert_company(**company_kwargs(
            company_name=company_name, domain=domain, market=market,
            segment=row.get("segment"), country=row.get("country"),
            source=row.get("source") or "icp_finder"))
        company_id = stored.get("id")
        if not company_id:
            raise LedgerContactUnresolved(
                f"upsert_company returned no id for {domain!r}, so no contact "
                "can be attached to it")
        _COMPANY_IDS[domain] = company_id

    contact = _real.upsert_contact(
        company_id, market,
        full_name=full_name,
        role_guess=row.get("role") or row.get("title") or None,
        linkedin_url=linkedin_url,
        email=email or None,
        email_source=row.get("email_source"),
    )
    contact_id = contact.get("id")
    if not contact_id:
        raise LedgerContactUnresolved(
            f"upsert_contact returned no id for {email or full_name!r}")
    return str(contact_id)


# --------------------------------------------------------------------------
# The eleven. Names fixed by Batch B.
#
# Each one takes this repo's vocabulary and, when the real ledger is live,
# hands B exactly the arguments B declares. When it is not, the shim gets the
# untranslated row, because the shim's whole job is to be a readable record of
# what this repo meant.
# --------------------------------------------------------------------------


def upsert_company(**row: Any) -> dict[str, Any]:
    """Write or update one `campaign.companies` row. Idempotent on `domain`.

    Returns the stored row plus `created`, which is True only the first time a
    domain is seen. The finder uses that flag for its dedup count. B does not
    report `created` - it is an upsert and PostgREST returns the row either way
    - so against the real ledger the finder's "new" count is the upsert count.
    """
    if _real is None:
        return _shim.upsert_company(**row)
    stored = _real.upsert_company(**company_kwargs(**row))
    if stored.get("id") and stored.get("domain"):
        _COMPANY_IDS[_norm_domain(stored["domain"])] = stored["id"]
    return stored


def upsert_contact(**row: Any) -> dict[str, Any]:
    if _real is None:
        return _shim.upsert_contact(**row)
    company_id = row.get("company_id") or _COMPANY_IDS.get(
        _norm_domain(row.get("company_domain")))
    if not company_id:
        raise LedgerContactUnresolved(
            "upsert_contact needs a company_id; campaign.contacts.company_id "
            "is NOT NULL and campaign_db has no company reader to look one up "
            "by domain. See BLOCKED.md C-B3.")
    return _real.upsert_contact(
        company_id, row.get("market"),
        full_name=row.get("full_name") or " ".join(
            p for p in (row.get("first_name") or "",
                        row.get("last_name") or "") if p).strip() or None,
        role_guess=row.get("role") or row.get("title") or None,
        linkedin_url=row.get("linkedin_url") or None,
        email=(row.get("work_email") or row.get("email") or "").strip().lower()
        or None,
        email_source=row.get("email_source"),
    )


def log_touch(**row: Any) -> dict[str, Any]:
    """Record one outbound action against `campaign.touches`.

    Against the real ledger this resolves (or creates) the contact first,
    because B keys the table on `contact_id` and this repo works from domains
    and email addresses. If a caller also passes `replied_at` /
    `reply_sentiment` - B's `log_touch` accepts neither, they belong to
    `record_reply` - the reply is forwarded to `record_reply` afterwards rather
    than being dropped.
    """
    if _real is None:
        return _shim.log_touch(**row)
    contact_id = _resolve_contact_id(row)
    stored = _real.log_touch(**touch_kwargs(contact_id, **row))
    if row.get("replied_at") or row.get("reply_sentiment"):
        _real.record_reply(**reply_kwargs(contact_id, **row))
    return stored


def record_reply(**row: Any) -> dict[str, Any]:
    if _real is None:
        return _shim.record_reply(**row)
    return _real.record_reply(**reply_kwargs(_resolve_contact_id(row), **row))


def insert_lead(**row: Any) -> dict[str, Any]:
    """B takes the shared qualifier payload as one mapping, not as kwargs."""
    if _real is None:
        return _shim.insert_lead(**row)
    payload = row.get("payload") or {
        k: v for k, v in row.items()
        if k not in ("payload", "company_id", "stage")}
    return _real.insert_lead(payload, company_id=row.get("company_id"),
                             stage=row.get("stage"))


def upsert_content(**row: Any) -> dict[str, Any]:
    """Not written by this repo - Batch D owns campaign.content. Kept so the
    eleven names are all present, and mapped so it cannot be called wrongly."""
    if _real is None:
        return _shim.upsert_content(**row)
    return _real.upsert_content(
        row.get("kind"), row.get("lane"), row.get("language"),
        row.get("hook"),
        **{k: row[k] for k in ("script_path", "asset_path", "platforms",
                               "published_at", "buffer_id") if k in row})


def snapshot_content_stats(**row: Any) -> dict[str, Any]:
    if _real is None:
        return _shim.snapshot_content_stats(**row)
    return _real.snapshot_content_stats(
        row.get("content_id"), row.get("platform"), row.get("captured_on"),
        **{k: row[k] for k in ("views", "likes", "comments", "saves", "clicks")
           if k in row})


def snapshot_ad_stats(**row: Any) -> dict[str, Any]:
    if _real is None:
        return _shim.snapshot_ad_stats(**row)
    return _real.snapshot_ad_stats(
        row.get("campaign_name"), row.get("ad_set_name"), row.get("captured_on"),
        **{k: row[k] for k in ("creative_content_id", "spend_eur",
                               "impressions", "clicks", "leads") if k in row})


def _filtered(rows: Any, market: Any) -> Any:
    """B's funnel views take no arguments - they return one row per market or
    per channel and the caller narrows. This repo asks for one market, so the
    narrowing happens here instead of being a TypeError."""
    if not market or not isinstance(rows, list):
        return rows
    return [r for r in rows if isinstance(r, dict)
            and market in (r.get("market"), r.get("source"), r.get("channel"))]


def get_market_funnel(market: Any = None, *args: Any, **kwargs: Any):
    if _real is None:
        return _shim.get_market_funnel(market, *args, **kwargs)
    return _filtered(_real.get_market_funnel(), market or kwargs.get("market"))


def get_channel_funnel(channel: Any = None, *args: Any, **kwargs: Any):
    if _real is None:
        return _shim.get_channel_funnel(channel, *args, **kwargs)
    return _filtered(_real.get_channel_funnel(), channel or kwargs.get("channel"))


def get_content_perf(*args: Any, **kwargs: Any):
    if _real is None:
        return _shim.get_content_perf(*args, **kwargs)
    return _real.get_content_perf(limit=kwargs.get("limit"))


def use_shim_dir(directory) -> None:
    """Point the shim at a different directory. Tests only.

    Lets a test get a clean, isolated ledger without touching the one the real
    runs write to, which is what makes the dedup test meaningful instead of
    order-dependent.
    """
    global _shim
    if using_real_ledger():
        raise RuntimeError("use_shim_dir() must never run against the real ledger")
    _shim = _Shim(Path(directory))


def reset_shim() -> None:
    """Wipe the shim's local state. Tests only. No effect on a real ledger."""
    if using_real_ledger():
        raise RuntimeError("reset_shim() must never run against the real ledger")
    _shim.companies = {}
    _shim._flush()
    if _shim.trail_path.exists():
        _shim.trail_path.unlink()
