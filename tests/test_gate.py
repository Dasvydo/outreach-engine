import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.enrich import Provider
from engine.gate import evaluate, partition, triage
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


def test_gmail_is_disqualifying_while_the_campaign_targets_outlook_only():
    """Changed 2026-09-14. Was soft since 2026-08-31; see engine/gate.py.

    This is a targeting decision, not a correction of the 2026-08-31 reasoning -
    Gmail still costs exactly what that note said it costs. The campaign has
    decided not to pay it, so the gate is hard while OUTLOOK_ONLY is set.
    """
    v = evaluate(_firm(provider=Provider.GOOGLE))
    assert not v.passed
    assert not v.review, "Google is a clear reject, not an unresolved provider"
    assert "Microsoft 365 only" in v.rejected_for


def test_the_soft_provider_path_still_works_when_outlook_only_is_off():
    """The 2026-08-31 behaviour is switched off, not deleted. Prove it still runs
    so that flipping the switch back is a one-line change and not an excavation."""
    import engine.gate as gate_module

    original = gate_module.OUTLOOK_ONLY
    try:
        gate_module.OUTLOOK_ONLY = False
        v = evaluate(_firm(provider=Provider.GOOGLE))
        assert v.passed
        assert v.score < evaluate(_firm()).score
    finally:
        gate_module.OUTLOOK_ONLY = original


def test_a_gateway_fronted_firm_is_parked_not_rejected():
    """Mimecast/Proofpoint in front of a domain hides the platform behind it.

    Measured 2026-09-14: kpmg.nl fronts Proofpoint and bbc.co.uk MessageLabs, and
    both are Microsoft shops. Rejecting GATEWAY outright would silently delete
    real best-fit prospects, so it parks for a second look instead.
    """
    v = evaluate(_firm(provider=Provider.GATEWAY))
    assert not v.passed, "not eligible to contact until the platform is known"
    assert v.review, "but must not be thrown away"
    assert "gateway" in v.parked_for.lower()


def test_an_unresolved_provider_is_parked_not_rejected():
    """A resolver timeout is not evidence that a firm is off-ICP."""
    v = evaluate(_firm(provider=Provider.UNKNOWN))
    assert not v.passed and v.review


def test_a_firm_failing_another_gate_is_rejected_not_parked():
    """Parking is only for a firm whose ONLY problem is an unresolved provider.
    A four-person shop behind a gateway is still a four-person shop."""
    v = evaluate(_firm(provider=Provider.GATEWAY, employees=4))
    assert not v.passed
    assert not v.review
    assert "G4" in v.rejected_for


def test_off_icp_vertical_is_rejected():
    assert not evaluate(_firm(vertical="freight")).passed


def test_oversized_firm_trips_the_sovereignty_ceiling():
    v = evaluate(_firm(employees=500))
    assert not v.passed and "G7" in v.rejected_for


def test_partition_keeps_only_microsoft_under_the_outlook_only_gate():
    ms, goog = _firm(name="MS"), _firm(name="G", provider=Provider.GOOGLE)
    kept, notkept = partition([goog, ms])
    assert [f.name for f in kept] == ["MS"]
    assert [f.name for f, _ in notkept] == ["G"]


def test_triage_separates_the_parked_from_the_rejected():
    """The distinction partition() flattens away, and the one that decides
    whether a lead gets a second chance or is gone."""
    ms = _firm(name="MS")
    goog = _firm(name="G", provider=Provider.GOOGLE)
    gw = _firm(name="GW", provider=Provider.GATEWAY)
    tiny = _firm(name="TINY", employees=3)

    kept, parked, rejected = triage([goog, ms, gw, tiny])
    assert [f.name for f in kept] == ["MS"]
    assert [f.name for f, _ in parked] == ["GW"]
    assert sorted(f.name for f, _ in rejected) == ["G", "TINY"]

    # And partition() folds parked back in with rejected, losing the difference.
    p_kept, p_notkept = partition([goog, ms, gw, tiny])
    assert p_kept == kept
    assert len(p_notkept) == len(parked) + len(rejected)
