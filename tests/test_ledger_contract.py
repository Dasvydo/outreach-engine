"""The seam is checked against Batch B's real signatures, not against a memory.

This file exists because of a specific, expensive class of bug. Batches B and C
were built in parallel and could not see each other. C called B's functions by
the right NAMES with the wrong ARGUMENTS - `company_name=` where B declares
`name=`, `employees_est=` where B declares `est_size=`, and a whole `log_touch`
payload with no `contact_id` in it at all. C's own shim accepts any keyword, so
the suite was green, the dry runs printed, and the mismatch was invisible right
up until the first real connection, where it becomes a TypeError.

A test that asserts against a list of argument names copied into this repo would
have had exactly the same blind spot, because the list would have been copied
from the same guess. So these tests load Batch B's `campaign_db.py` from disk
and bind against `inspect.signature` of the real functions. If B renames a
parameter, or C drifts back into its own vocabulary, this file fails on the next
run instead of on the first connection.

Nothing here connects to anything. `campaign_db` builds its PostgREST client
lazily on first call, so importing the module and reading its signatures needs
no credentials and touches no network - and none of B's functions is ever
actually invoked here, only its signature.
"""

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import ledger                       # noqa: E402
from engine.enrich import Provider              # noqa: E402


# --------------------------------------------------------------------------
# Loading Batch B's module by file path
# --------------------------------------------------------------------------

def _campaign_db_path() -> Path | None:
    override = os.environ.get("CAMPAIGN_DB_PATH")
    candidates = [Path(override)] if override else []
    candidates += [
        ROOT.parent / "campaign-ledger" / "src" / "campaign_db.py",
        ROOT.parent / "campaign-ledger" / "campaign_db.py",
    ]
    return next((p for p in candidates if p.is_file()), None)


@pytest.fixture(scope="module")
def campaign_db():
    """Batch B's real client, imported from the campaign-ledger repo by path.

    Skipped rather than failed when that repo is not checked out beside this
    one: a developer with only this repo should still get a green suite. Set
    CAMPAIGN_DB_PATH to point at it from anywhere else.
    """
    path = _campaign_db_path()
    if path is None:
        pytest.skip("campaign-ledger is not checked out beside this repo; "
                    "set CAMPAIGN_DB_PATH to run the contract tests")
    spec = importlib.util.spec_from_file_location("_batch_b_campaign_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binds(function, kwargs) -> inspect.BoundArguments:
    """Bind kwargs against a signature. Raises TypeError on any drift."""
    return inspect.signature(function).bind(**kwargs)


# --------------------------------------------------------------------------
# The arguments the real call sites actually build
# --------------------------------------------------------------------------

# Copied from engine/icp_finder.py's ledger.upsert_company() call, verbatim.
FINDER_CALL = dict(
    market="dk",
    segment="housing_admin",
    company_name="Eksempel Boligadministration",
    domain="eksempel-bolig.dk",
    country="DK",
    city="Aarhus",
    mail_provider="microsoft",
    team_size="10-24",
    employees_est=18,
    dev_team_signal=0.0,
    fit_score=0.82,
    source="icp_finder:dk",
    stage="discovered",
    notes="MX=eksempel-bolig-dk.mail.protection.outlook.com; clean",
)

# Copied from load_instantly.py's ledger.log_touch() call, verbatim.
LOADER_CALL = dict(
    company_domain="example-accounting.com",
    work_email="sarah@example-accounting.com",
    channel="email",
    step=1,
    sequence_id="email_en",
    market="global",
    locale="en",
    utm_content="global_1",
    status="planned",
    sent_at=None,
    replied_at=None,
    reply_sentiment=None,
    created_at="2026-09-03T09:00:00+00:00",
    company_name="Example Accounting Partners",
    first_name="Sarah",
    last_name="Miller",
    linkedin_url="https://www.linkedin.com/in/example-sarah/",
    role="owner_partner",
    segment="accounting",
    country="GB",
    email_source="instantly_finder",
)

REPLY_CALL = dict(
    company_domain="example-accounting.com",
    work_email="sarah@example-accounting.com",
    channel="email",
    step=1,
    market="global",
    replied_at="2026-09-24T09:12:00Z",
    reply_sentiment="hot_pain",
    ledger_stage="qualified",
    classifier="keyword",
    classifier_note="matched en:'sounds good'",
    company_name="Example Accounting Partners",
)


# --------------------------------------------------------------------------
# The bind tests. These are the ones that catch the bug for good.
# --------------------------------------------------------------------------

def test_upsert_company_arguments_bind_to_batch_bs_signature(campaign_db):
    binds(campaign_db.upsert_company, ledger.company_kwargs(**FINDER_CALL))


def test_log_touch_arguments_bind_to_batch_bs_signature(campaign_db):
    binds(campaign_db.log_touch,
          ledger.touch_kwargs("11111111-2222-3333-4444-555555555555",
                              **LOADER_CALL))


def test_record_reply_arguments_bind_to_batch_bs_signature(campaign_db):
    binds(campaign_db.record_reply,
          ledger.reply_kwargs("11111111-2222-3333-4444-555555555555",
                              **REPLY_CALL))


def test_the_untranslated_call_would_not_have_bound(campaign_db):
    """The defect this file exists to stop, asserted as a defect.

    If this ever starts passing, either B has grown C's vocabulary or someone
    has quietly widened a signature with **kwargs, and the translation below is
    no longer doing anything.
    """
    with pytest.raises(TypeError):
        binds(campaign_db.upsert_company, FINDER_CALL)
    with pytest.raises(TypeError):
        binds(campaign_db.log_touch, LOADER_CALL)


# --------------------------------------------------------------------------
# Field by field
# --------------------------------------------------------------------------

def test_the_names_batch_b_actually_declares():
    out = ledger.company_kwargs(**FINDER_CALL)
    assert out["name"] == "Eksempel Boligadministration"   # not company_name
    assert out["est_size"] == 18                           # not employees_est
    assert out["domain"] == "eksempel-bolig.dk"
    assert out["market"] == "dk"
    assert out["country"] == "DK"


def test_housing_admin_becomes_the_admin_of_bs_segment_enum(campaign_db):
    assert ledger.company_kwargs(**FINDER_CALL)["segment"] == "admin"
    assert "admin" in campaign_db._SEGMENTS
    assert "housing_admin" not in campaign_db._SEGMENTS


def test_the_market_tag_is_stripped_off_the_source_enum(campaign_db):
    assert ledger.company_kwargs(**FINDER_CALL)["source"] == "icp_finder"
    assert "icp_finder:dk" not in campaign_db._COMPANY_SOURCES


def test_mail_provider_becomes_uses_m365_the_way_the_mx_gate_decides():
    """The gate passes a firm when the provider is MICROSOFT and nothing else.
    UNKNOWN means the lookup failed, which is not the same as 'not Microsoft',
    and B's column is nullable so that stays sayable."""
    assert ledger.uses_m365(Provider.MICROSOFT) is True
    assert ledger.uses_m365(Provider.MICROSOFT.value) is True
    assert ledger.uses_m365(Provider.GOOGLE) is False
    assert ledger.uses_m365(Provider.OTHER) is False
    assert ledger.uses_m365(Provider.UNKNOWN) is None
    assert ledger.uses_m365(None) is None
    assert ledger.company_kwargs(**FINDER_CALL)["uses_m365"] is True


def test_the_dev_team_score_never_asserts_true_from_a_heuristic():
    """Same rule as engine/icp_finder.py: the gate hard-fails on True, and a
    scored guess is not grounds for a hard fail."""
    assert ledger.has_dev_team(0.0) is False
    assert ledger.has_dev_team(0.49) is False
    assert ledger.has_dev_team(0.5) is None
    assert ledger.has_dev_team(1.0) is None
    assert ledger.has_dev_team(None) is None


def test_a_high_dev_score_is_kept_in_hook_seed_instead_of_being_lost():
    out = ledger.company_kwargs(**{**FINDER_CALL, "dev_team_signal": 0.7})
    assert out["has_dev_team"] is None
    assert "dev_signal=0.7" in out["hook_seed"]


def test_fit_score_is_rescaled_to_bs_integer_percent(campaign_db):
    """C scores 0.0-1.0. B's column is integer with a 0..100 check constraint,
    so 0.82 has to arrive as 82 and not as 0."""
    out = ledger.company_kwargs(**FINDER_CALL)
    assert out["fit_score"] == 82
    assert isinstance(out["fit_score"], int)
    assert ledger.fit_score(0.0) == 0
    assert ledger.fit_score(1.0) == 100
    assert ledger.fit_score(None) is None


def test_the_step_becomes_bs_sequence_step_and_locale_becomes_language():
    out = ledger.touch_kwargs("cid", **LOADER_CALL)
    assert out["sequence_step"] == 1
    assert out["language"] == "en"
    assert "step" not in out and "locale" not in out


def test_a_linkedin_touch_picks_the_right_half_of_bs_channel_enum(campaign_db):
    """C says `linkedin`; B splits the connection request from the DM that
    follows it, which is the more useful split."""
    assert ledger.touch_channel("linkedin", 1) == "linkedin_connect"
    assert ledger.touch_channel("linkedin", 2) == "linkedin_dm"
    assert ledger.touch_channel("email", 1) == "email"
    assert ledger.touch_channel("phone", 3) == "phone"
    for value in ("linkedin_connect", "linkedin_dm", "email", "phone"):
        assert value in campaign_db._TOUCH_CHANNELS


# --------------------------------------------------------------------------
# Nothing is dropped on the floor
# --------------------------------------------------------------------------

# campaign.companies has no column for these four. They are folded into the
# hook_seed text column and named in BLOCKED.md C-B1.
COMPANY_ORPHANS = ("city", "team_size", "stage", "notes")
# campaign.touches has no column for these. They go into notes; BLOCKED.md C-B2.
TOUCH_ORPHANS = ("sequence_id", "utm_content", "status", "market",
                 "company_domain", "work_email")


# The renames, written out. Everything else in FINDER_CALL keeps its own name.
COMPANY_RENAMES = {
    "company_name": "name",
    "employees_est": "est_size",
    "mail_provider": "uses_m365",
    "dev_team_signal": "has_dev_team",
}


def test_every_company_field_this_repo_writes_has_somewhere_to_go(campaign_db):
    """No silent drops. Every field this repo sends is either a parameter B
    declares - under its own name or a renamed one - or is folded into
    hook_seed and named as a schema gap in BLOCKED.md C-B1."""
    declared = set(inspect.signature(campaign_db.upsert_company).parameters)
    seed = ledger.company_kwargs(**FINDER_CALL)["hook_seed"] or ""

    for field in FINDER_CALL:
        if field in COMPANY_ORPHANS:
            assert f"{field}=" in seed, f"{field} was dropped silently"
        else:
            target = COMPANY_RENAMES.get(field, field)
            assert target in declared, (
                f"{field} maps to {target}, which Batch B does not declare")


def test_the_orphaned_company_fields_are_readable_in_hook_seed():
    seed = ledger.company_kwargs(**FINDER_CALL)["hook_seed"]
    assert "city=Aarhus" in seed
    assert "team_size=10-24" in seed
    assert "stage=discovered" in seed
    assert "notes=MX=eksempel-bolig-dk.mail.protection.outlook.com; clean" in seed


def test_a_hook_seed_that_was_passed_in_survives_the_fold():
    seed = ledger.company_kwargs(**{**FINDER_CALL, "hook_seed": "the pain"})["hook_seed"]
    assert seed.startswith("the pain -- ")
    assert "city=Aarhus" in seed


def test_the_orphaned_touch_fields_are_readable_in_notes():
    notes = ledger.touch_kwargs("cid", **LOADER_CALL)["notes"]
    for field in TOUCH_ORPHANS:
        assert f"{field}=" in notes, f"{field} was dropped silently"


def test_the_classifier_that_judged_a_reply_is_written_down():
    notes = ledger.reply_kwargs("cid", **REPLY_CALL)["notes"]
    assert "classifier=keyword" in notes
    assert "ledger_stage=qualified" in notes


# --------------------------------------------------------------------------
# contact_id: resolved, or refused out loud
# --------------------------------------------------------------------------

@pytest.fixture
def strict_ledger(campaign_db, monkeypatch):
    """A stand-in for campaign_db whose every function binds against the REAL
    signature before returning a canned row.

    This is the end-to-end half of the proof: the tests above check the
    builders, this one drives the actual call sites through them and fails on
    any argument B would not accept.
    """
    calls: list[tuple[str, tuple, dict]] = []

    def strict(name, result):
        real = getattr(campaign_db, name)

        def call(*args, **kwargs):
            inspect.signature(real).bind(*args, **kwargs)
            calls.append((name, args, kwargs))
            return result
        return call

    fake = SimpleNamespace(
        upsert_company=strict("upsert_company",
                              {"id": "company-1", "domain": "example.com"}),
        upsert_contact=strict("upsert_contact", {"id": "contact-1"}),
        log_touch=strict("log_touch", {"id": "touch-1"}),
        record_reply=strict("record_reply", {"id": "touch-1"}),
    )
    monkeypatch.setattr(ledger, "_real", fake)
    monkeypatch.setattr(ledger, "_COMPANY_IDS", {})
    return SimpleNamespace(calls=calls, module=fake)


def test_log_touch_resolves_a_real_contact_id_before_writing(strict_ledger):
    """B keys campaign.touches on contact_id and the column is NOT NULL. This
    repo works from domains and emails, so the contact is created first."""
    ledger.log_touch(**LOADER_CALL)
    names = [name for name, _, _ in strict_ledger.calls]
    assert names == ["upsert_company", "upsert_contact", "log_touch"]

    _, _, contact_kwargs = strict_ledger.calls[1]
    assert contact_kwargs["email"] == "sarah@example-accounting.com"
    assert contact_kwargs["full_name"] == "Sarah Miller"

    _, _, touch_kwargs = strict_ledger.calls[2]
    assert touch_kwargs["contact_id"] == "contact-1"
    assert touch_kwargs["language"] == "en"
    assert touch_kwargs["sequence_step"] == 1


def test_the_firm_is_only_upserted_once_per_process(strict_ledger):
    ledger.log_touch(**LOADER_CALL)
    ledger.log_touch(**{**LOADER_CALL, "step": 2})
    names = [name for name, _, _ in strict_ledger.calls]
    assert names.count("upsert_company") == 1


def test_an_unresolvable_contact_is_refused_out_loud_not_dropped(strict_ledger):
    """The one thing worse than a touch that is not written is a touch written
    against a made-up contact."""
    with pytest.raises(ledger.LedgerContactUnresolved, match="company_name"):
        ledger.log_touch(company_domain="example.com", work_email="a@example.com",
                         channel="email", step=1, market="global", locale="en")
    with pytest.raises(ledger.LedgerContactUnresolved, match="work_email"):
        ledger.log_touch(company_domain="example.com", channel="email", step=1,
                         market="global", locale="en")


def test_a_reply_passed_to_log_touch_is_forwarded_to_record_reply(strict_ledger):
    """B's log_touch takes neither replied_at nor reply_sentiment; they belong
    to record_reply. Forwarded rather than dropped."""
    ledger.log_touch(**{**LOADER_CALL, "replied_at": "2026-09-24T09:12:00Z",
                        "reply_sentiment": "hot_pain"})
    names = [name for name, _, _ in strict_ledger.calls]
    assert names[-1] == "record_reply"
    assert strict_ledger.calls[-1][2]["sentiment"] == "hot_pain"


def test_the_finders_real_call_site_binds_end_to_end(strict_ledger, tmp_path):
    """engine/icp_finder.py, driven for real against B's real signatures."""
    from engine import icp_finder
    summary = icp_finder.run_market("dk", probe=False, lists_dir=tmp_path,
                                    run_date="2026-09-03")
    assert summary["new"] > 0
    company_calls = [c for c in strict_ledger.calls if c[0] == "upsert_company"]
    assert company_calls, "the finder wrote nothing to the ledger"
    # Every one of those calls was bound against B's real signature inside the
    # fake before it was recorded, so reaching here at all is the assertion.
    # These two names are checked anyway because they are the exact pair that
    # was wrong before the reconciliation.
    for _, _, kwargs in company_calls:
        assert "company_name" not in kwargs and "employees_est" not in kwargs
        assert kwargs["name"] and kwargs["domain"]


def test_the_loaders_real_call_site_binds_end_to_end(strict_ledger):
    """load_instantly.py, driven for real against B's real signatures."""
    import load_instantly
    from engine.contacts import load_contacts

    contacts = [c for c in load_contacts() if c.market == "global"]
    assert contacts
    written = load_instantly.log_touches(contacts, dry_run=True)
    assert written == len(contacts)
    touches = [c for c in strict_ledger.calls if c[0] == "log_touch"]
    assert len(touches) == len(contacts)
    for _, _, kwargs in touches:
        assert kwargs["contact_id"]
        assert "step" not in kwargs and "utm_content" not in kwargs


# --------------------------------------------------------------------------
# The read side
# --------------------------------------------------------------------------

def test_the_funnel_views_take_no_arguments_on_bs_side(campaign_db, monkeypatch):
    """This repo asks for one market. B's view returns all of them and takes no
    parameters, so the narrowing happens in the adapter rather than as a
    TypeError."""
    assert not inspect.signature(campaign_db.get_market_funnel).parameters

    rows = [{"market": "dk", "leads": 3}, {"market": "lt", "leads": 1}]
    monkeypatch.setattr(ledger, "_real",
                        SimpleNamespace(get_market_funnel=lambda: rows))
    assert ledger.get_market_funnel("dk") == [{"market": "dk", "leads": 3}]
    assert ledger.get_market_funnel() == rows


def test_a_sentiment_batch_b_does_not_know_is_refused_with_both_lists(campaign_db):
    """This repo's reply_taxonomy.yaml was reconstructed and its six ids are
    not B's six. Refused here, with both vocabularies in the message, rather
    than guessed at or sent to be rejected as an opaque enum cast error."""
    assert set(campaign_db._SENTIMENTS) == {
        "hot_pain", "curious", "endorse", "objection", "unrelated", "ineligible"}
    with pytest.raises(ledger.LedgerVocabularyMismatch, match="hot_pain"):
        ledger.reply_kwargs("cid", **{**REPLY_CALL, "reply_sentiment": "interested"})
    # B's own six still pass straight through.
    for value in campaign_db._SENTIMENTS:
        out = ledger.reply_kwargs("cid", **{**REPLY_CALL, "reply_sentiment": value})
        assert out["sentiment"] == value
