"""Offline tests for the CVR ingest path.

Everything here runs without credentials and without network: the mapping and
the band arithmetic are where the errors that would put a wrong firm in a
campaign actually live.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from engine.cvr import (
    F_BRANCHEKODE, Credentials, MissingCredentials, bands_within, build_query,
    to_domain, to_firm,
)
from engine.gate import MAX_SEATS, MIN_SEATS, evaluate


def _hit(**over):
    """A CVR hit shaped like the published Vrvirksomhed schema."""
    v = {
        "cvrNummer": 12345678,
        "reklamebeskyttet": False,
        "hjemmeside": [{"kontaktoplysning": "www.nordicrevision.dk",
                        "hemmelig": False, "periode": {"gyldigTil": None}}],
        "elektroniskPost": [{"kontaktoplysning": "kontakt@nordicrevision.dk",
                             "hemmelig": False, "periode": {"gyldigTil": None}}],
        "virksomhedMetadata": {
            "nyesteNavn": {"navn": "Nordic Revision ApS"},
            "nyesteHovedbranche": {"branchekode": "692000",
                                   "branchetekst": "Bogføring og revision"},
            "nyesteBeliggenhedsadresse": {"postdistrikt": "København K",
                                          "kommune": {"kommuneKode": "0101"}},
            "nyesteAarsbeskaeftigelse": {"aar": 2025, "antalAnsatte": 14,
                                         "intervalKodeAntalAnsatte": "ANTAL_10_19"},
        },
    }
    v.update(over)
    return {"Vrvirksomhed": v}


def test_bands_are_wholly_inside_the_seat_range():
    """A partially-overlapping band would smuggle firms past G4 or G7."""
    bands = bands_within(MIN_SEATS, MAX_SEATS)
    assert "ANTAL_10_19" in bands and "ANTAL_100_199" in bands
    assert "ANTAL_5_9" not in bands      # contains firms under the G4 floor
    assert "ANTAL_200_499" not in bands  # contains firms over the G7 ceiling


def test_query_filters_on_branchekode_and_bands():
    q = build_query("692000", ["ANTAL_10_19"], kommune_koder=["0101"])
    must = q["query"]["bool"]["must"]
    assert {"term": {F_BRANCHEKODE: "692000"}} in must
    assert any("ANTAL_10_19" in str(clause) for clause in must)


def test_maps_a_cvr_hit_onto_a_firm_that_passes_the_gate():
    firm, reason = to_firm(_hit(), "accounting")
    assert reason == ""
    assert (firm.name, firm.domain, firm.nace) == (
        "Nordic Revision ApS", "nordicrevision.dk", "69.20")
    assert firm.employees == 14 and firm.registry_id == "DK12345678"
    # G6 is not answerable from CVR; guessing False would fake a passed gate.
    assert firm.has_dev_team is None
    assert evaluate(firm).passed


def test_advertising_protected_firms_are_dropped():
    """Not a preference - a condition of the CVR data access."""
    firm, reason = to_firm(_hit(reklamebeskyttet=True), "accounting")
    assert firm is None and reason == "reklamebeskyttet"


def test_firm_without_a_website_is_dropped():
    firm, reason = to_firm(_hit(hjemmeside=[]), "accounting")
    assert firm is None and "domain" in reason


def test_secret_and_expired_contact_details_are_not_used():
    secret = [{"kontaktoplysning": "hidden.dk", "hemmelig": True,
               "periode": {"gyldigTil": None}}]
    expired = [{"kontaktoplysning": "old.dk", "hemmelig": False,
                "periode": {"gyldigTil": "2020-01-01"}}]
    assert to_firm(_hit(hjemmeside=secret), "accounting")[0] is None
    assert to_firm(_hit(hjemmeside=expired), "accounting")[0] is None


def test_band_lower_bound_is_used_when_cvr_has_no_exact_count():
    meta = _hit()["Vrvirksomhed"]["virksomhedMetadata"]
    meta["nyesteAarsbeskaeftigelse"] = {"intervalKodeAntalAnsatte": "ANTAL_20_49"}
    firm, _ = to_firm(_hit(virksomhedMetadata=meta), "accounting")
    assert firm.employees == 20  # conservative: never rounds a firm up past a gate


def test_unknown_headcount_stays_unknown_rather_than_zero():
    meta = _hit()["Vrvirksomhed"]["virksomhedMetadata"]
    meta.pop("nyesteAarsbeskaeftigelse")
    firm, _ = to_firm(_hit(virksomhedMetadata=meta), "accounting")
    assert firm.employees is None
    assert evaluate(firm).passed          # soft downrank, not a hard fail
    assert evaluate(firm).score < 1.0


@pytest.mark.parametrize("raw,expected", [
    ("http://www.x.dk/kontakt", "x.dk"),
    ("HTTPS://Revision.DK", "revision.dk"),
    ("x.dk", "x.dk"),
    ("not a url", ""),
    ("", ""),
])
def test_website_text_is_reduced_to_a_bare_host(raw, expected):
    assert to_domain(raw) == expected


def test_missing_credentials_raise_rather_than_degrade_the_source(monkeypatch):
    monkeypatch.delenv("CVR_USER", raising=False)
    monkeypatch.delenv("CVR_PASSWORD", raising=False)
    with pytest.raises(MissingCredentials, match="cvrselvbetjening@erst.dk"):
        Credentials.from_env()
