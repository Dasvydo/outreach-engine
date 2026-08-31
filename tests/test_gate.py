import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.enrich import Provider
from engine.gate import evaluate, partition
from engine.model import Firm


def _firm(**kw):
    base = dict(name="X", domain="x.dk", country="DK", vertical="accounting",
                nace="69.20", employees=14, provider=Provider.MICROSOFT,
                has_dev_team=False)
    base.update(kw)
    return Firm(**base)


def test_clean_microsoft_firm_passes_at_full_score():
    v = evaluate(_firm())
    assert v.passed and v.score == 1.0


def test_under_ten_seats_is_a_hard_fail():
    v = evaluate(_firm(employees=4))
    assert not v.passed and "G4" in v.rejected_for


def test_dev_team_is_a_hard_fail():
    v = evaluate(_firm(has_dev_team=True))
    assert not v.passed and "G6" in v.rejected_for


def test_gmail_downranks_but_does_not_disqualify():
    """Corrected 2026-08-31: Gmail is workable, not disqualifying."""
    v = evaluate(_firm(provider=Provider.GOOGLE))
    assert v.passed
    assert v.score < evaluate(_firm()).score


def test_off_icp_vertical_is_rejected():
    assert not evaluate(_firm(vertical="freight")).passed


def test_oversized_firm_trips_the_sovereignty_ceiling():
    v = evaluate(_firm(employees=500))
    assert not v.passed and "G7" in v.rejected_for


def test_partition_sorts_microsoft_above_google():
    ms, goog = _firm(name="MS"), _firm(name="G", provider=Provider.GOOGLE)
    kept, _ = partition([goog, ms])
    assert [f.name for f in kept] == ["MS", "G"]


def test_english_fallback_is_labelled_english_in_the_csv(tmp_path):
    """The language column routes a lead to a sequence.

    A Danish firm sent English fallback copy must not be labelled 'da', or it
    gets routed to a Danish sequence its body was never written for.
    """
    from engine.export import to_csv
    from engine.model import Campaign, Contact

    contact = Contact(firm=_firm(), email="a@x.dk", first_name="Lars")
    assert contact.language == "da"
    camp = Campaign("c", "accounting", "DK", "capacity", [contact])

    out = to_csv(camp, tmp_path / "da.csv").read_text()
    assert out.strip().splitlines()[1].split(",")[-2] == "da"

    out = to_csv(camp, tmp_path / "en.csv", rendered_language="en").read_text()
    assert out.strip().splitlines()[1].split(",")[-2] == "en"
