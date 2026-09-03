"""The three loaders: queue building, dry runs, and the reply classifier."""

import json
from datetime import date
from pathlib import Path

import pytest

import build_linkedin_queue as blq
import load_instantly
import sync_replies
from engine.contacts import ContactRow, load_contacts

ROOT = Path(__file__).resolve().parent.parent


def _contact(i: int, market: str = "global") -> ContactRow:
    return ContactRow(
        company_domain=f"firm{i}.com", company_name=f"Firm {i}",
        first_name=f"Name{i}", last_name="Surname", role="owner_partner",
        title="Partner", work_email=f"a{i}@firm{i}.com", phone="+1 555 0100",
        linkedin_url=f"https://www.linkedin.com/in/person-{i}/",
        market=market, locale="en", segment="accounting", country="US",
    )


# --- the 20 a day cap -----------------------------------------------------

def test_the_daily_cap_is_twenty():
    assert blq.DAILY_CAP == 20


def test_a_big_list_is_split_at_twenty_a_day():
    contacts = [_contact(i) for i in range(55)]
    planned = blq.schedule(contacts, start=date(2026, 9, 8), days=10)
    per_day: dict[date, int] = {}
    for when, _ in planned:
        per_day[when] = per_day.get(when, 0) + 1
    assert per_day, "nothing was scheduled"
    for when, count in per_day.items():
        assert count <= blq.DAILY_CAP, f"{when} has {count} connects, over the cap"
    assert len(planned) == 55


def test_the_queue_never_schedules_a_weekend():
    contacts = [_contact(i) for i in range(60)]
    planned = blq.schedule(contacts, start=date(2026, 9, 11), days=10)  # a Friday
    for when, _ in planned:
        assert when.weekday() < 5, f"{when} is a weekend"


def test_the_cap_is_shared_across_markets_not_per_market(tmp_path):
    """Three markets at 20 each would be 60 a day and would get the account hit."""
    result = blq.build(["dk", "lt", "global"], contacts_path=None,
                       start=date(2026, 9, 8), days=10, out_dir=tmp_path,
                       dry_run=True)
    for day, count in result["per_day"].items():
        assert count <= blq.DAILY_CAP, f"{day} has {count}, over the shared cap"


def test_the_queue_writes_both_shapes_and_the_documented_fields(tmp_path):
    result = blq.build(["dk"], contacts_path=None, start=date(2026, 9, 8),
                       days=10, out_dir=tmp_path, dry_run=False)
    assert result["jsonl"].exists()
    assert result["csv"].exists()

    lines = result["jsonl"].read_text(encoding="utf-8").strip().splitlines()
    assert lines
    for line in lines:
        record = json.loads(line)
        assert set(record) == set(blq.QUEUE_FIELDS), \
            "a queue record drifted from QUEUE_FIELDS"
        assert record["step"] == 1
        assert record["utm_content"].endswith("_1")
        assert record["profile_url"].startswith("https://www.linkedin.com/")


def test_queue_notes_are_in_the_markets_language(tmp_path):
    result = blq.build(["dk", "lt", "global"], contacts_path=None,
                       start=date(2026, 9, 8), days=10, out_dir=tmp_path,
                       dry_run=True)
    by_market = {r["market"]: r for r in result["records"]}
    assert "Jeg arbejder med" in by_market["dk"]["note"]
    assert "Dirbu su" in by_market["lt"]["note"]
    assert "I work with" in by_market["global"]["note"]
    assert by_market["dk"]["sequence_id"] == "linkedin_da"
    assert by_market["lt"]["sequence_id"] == "linkedin_lt"
    assert by_market["global"]["sequence_id"] == "linkedin_en"


def test_every_queued_note_is_under_the_linkedin_limit(tmp_path):
    result = blq.build(["dk", "lt", "global"], contacts_path=None,
                       start=date(2026, 9, 8), days=10, out_dir=tmp_path,
                       dry_run=True)
    for record in result["records"]:
        assert len(record["note"]) < blq.CONNECT_NOTE_LIMIT, record["note"]


# --- dry runs -------------------------------------------------------------

def test_load_instantly_dry_run_exits_clean(capsys):
    assert load_instantly.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN, nothing sent" in out
    assert "Danish addresses blocked at the loader: 4" in out


def test_load_instantly_refuses_to_run_live_without_a_key(monkeypatch, capsys):
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    assert load_instantly.main(["--live"]) == 2
    assert "Refusing to run live" in capsys.readouterr().err


def test_sync_replies_dry_run_exits_clean(capsys):
    assert sync_replies.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "nothing was written to campaign.touches" in out.lower()


def test_build_linkedin_queue_dry_run_writes_no_file(tmp_path, capsys):
    assert blq.main(["--all", "--dry-run", "--out-dir", str(tmp_path)]) == 0
    assert list(tmp_path.glob("*")) == []


# --- the reply classifier -------------------------------------------------

def test_the_taxonomy_has_exactly_six_values():
    taxonomy = sync_replies.load_taxonomy()
    ids = [v["id"] for v in taxonomy["values"]]
    assert len(ids) == 6
    assert len(set(ids)) == 6


def test_the_taxonomy_is_honestly_marked_as_reconstructed():
    """It is not the real DSD six and must not pretend to be. BLOCKED.md B5."""
    assert sync_replies.load_taxonomy()["canonical"] is False


@pytest.mark.parametrize("body,expected", [
    ("Please unsubscribe me from this list.", "unsubscribe"),
    ("Sounds good, send the link", "interested"),
    ("Not right now, we are in busy season", "not_now"),
    ("I am not the right person, copying our office manager", "referred"),
    ("Where is the data stored?", "objection"),
    ("We are only three people, not a fit", "not_a_fit"),
])
def test_the_keyword_classifier_hits_every_value(body, expected):
    taxonomy = sync_replies.load_taxonomy()
    value, _ = sync_replies.classify_keyword(body, taxonomy)
    assert value == expected


def test_unsubscribe_beats_a_polite_refusal():
    """A reply can match two lists. Suppression has to win."""
    taxonomy = sync_replies.load_taxonomy()
    value, _ = sync_replies.classify_keyword(
        "Not a fit for us, please remove me from your list.", taxonomy)
    assert value == "unsubscribe"


def test_an_unmatched_reply_goes_to_a_human_not_to_a_guess():
    taxonomy = sync_replies.load_taxonomy()
    value, why = sync_replies.classify_keyword("Thanks for reaching out.", taxonomy)
    assert value == taxonomy["fallback"] == "objection"
    assert "nothing matched" in why


def test_accented_replies_still_classify():
    """Danish and Lithuanian replies carry diacritics the keyword lists do not."""
    taxonomy = sync_replies.load_taxonomy()
    assert sync_replies.classify_keyword("Prašau nerašykite man daugiau",
                                         taxonomy)[0] == "unsubscribe"
    assert sync_replies.classify_keyword("Ikke lige nu, vi har travlt",
                                         taxonomy)[0] == "not_now"


def test_the_model_classifier_refuses_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        sync_replies.classify_model("hello", sync_replies.load_taxonomy())


# --- the ledger seam ------------------------------------------------------

def test_the_ledger_exposes_exactly_batch_bs_eleven_functions():
    from engine import ledger
    expected = {
        "upsert_company", "upsert_contact", "log_touch", "record_reply",
        "insert_lead", "upsert_content", "snapshot_content_stats",
        "snapshot_ad_stats", "get_market_funnel", "get_channel_funnel",
        "get_content_perf",
    }
    for name in expected:
        assert callable(getattr(ledger, name)), f"ledger is missing {name}"


def test_the_ledger_degrades_instead_of_crashing_when_batch_b_is_absent(clean_ledger):
    """Batch C must not be blocked on Batch B landing."""
    assert clean_ledger.backend_name() in ("shim", "campaign_db")
    assert clean_ledger.get_market_funnel("dk") == [] or clean_ledger.using_real_ledger()
    assert clean_ledger.log_touch(channel="linkedin", step=1)


def test_contacts_fixture_covers_all_three_markets():
    for market in ("dk", "lt", "global"):
        assert load_contacts(market=market), f"no {market} contacts in the fixture"
