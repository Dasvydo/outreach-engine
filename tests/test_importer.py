"""The importer is the front door, so its failures are silent by nature.

A lead that never arrives looks exactly like a lead that was never found. These
tests exist to make the four ways out of the importer - lead, review, rejected,
contact - explicit and countable, because the whole design rests on rows never
vanishing between them.

Nothing here touches the network. MX results are injected.
"""

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import importer                                    # noqa: E402
from engine.enrich import MXResult, Provider, Unresolved       # noqa: E402


HEADER = ("Company Name,Website,Country,Industry,Employee Count,Match Score,"
          "Icebreaker,Comments,First Name,Last Name,Job Title,Email Address,"
          "Phone,LinkedIn")


def _write(tmp_path, *rows, header=HEADER):
    p = tmp_path / "export.csv"
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return p


def _run(tmp_path, *rows, **kw):
    src = _write(tmp_path, *rows, header=kw.pop("header", HEADER))
    out = tmp_path / "out"
    kw.setdefault("check_mx", False)
    report = importer.run_import(src, out, run_date="2026-09-14", **kw)
    read = lambda name: list(csv.DictReader(  # noqa: E731
        (out / f"{name}_2026-09-14.csv").open(encoding="utf-8")))
    return report, read


# --------------------------------------------------------------------------
# Column resolution - the reason this importer exists in alias form at all
# --------------------------------------------------------------------------

def test_columns_resolve_through_aliases_not_exact_names():
    """No AI Arc export has been seen. The importer must survive plausible
    header names rather than assume one spelling."""
    resolved, unmapped = importer.resolve_columns(
        ["Company Name", "Website", "Match Score", "Email Address", "LinkedIn"])
    assert resolved["company"] == "Company Name"
    assert resolved["domain"] == "Website"
    assert resolved["fit_score"] == "Match Score"
    assert resolved["work_email"] == "Email Address"
    assert resolved["linkedin_url"] == "LinkedIn"
    assert not unmapped


def test_an_explicit_mapping_overrides_auto_detection():
    """When auto-detection guesses wrong, --mapping must always win."""
    resolved, _ = importer.resolve_columns(
        ["name", "site"], overrides={"company": "name", "domain": "site"})
    assert resolved["company"] == "name"
    assert resolved["domain"] == "site"


def test_unmapped_columns_are_reported_rather_than_ignored_quietly():
    _, unmapped = importer.resolve_columns(["Company Name", "Mystery Field"])
    assert unmapped == ["Mystery Field"]


def test_one_source_column_is_never_claimed_by_two_canonical_names():
    resolved, _ = importer.resolve_columns(["title", "role"])
    assert len({v for v in resolved.values()}) == len(resolved)


# --------------------------------------------------------------------------
# fit_score - the silent one
# --------------------------------------------------------------------------

def test_the_fit_scale_is_detected_per_file_not_per_row():
    """1.0 is valid on both scales, so a row alone cannot say which is meant."""
    assert importer.detect_fit_scale(["1", "0.5", "0.75"]) == "unit"
    assert importer.detect_fit_scale(["5", "4", "3"]) == "one_to_five"
    assert importer.detect_fit_scale(["82", "45"]) == "percent"
    assert importer.detect_fit_scale([]) == "unknown"


def test_a_one_to_five_score_is_rescaled_and_not_left_to_corrupt_the_ledger():
    """engine/ledger.py multiplies by 100 regardless of scale, so an un-normalised
    5 would be written as 5% fit and every downstream ranking would invert."""
    assert importer.normalise_fit(5, "one_to_five") == 1.0
    assert importer.normalise_fit(1, "one_to_five") == 0.0
    assert importer.normalise_fit(4, "one_to_five") == 0.75
    assert importer.normalise_fit(0.82, "unit") == 0.82
    assert importer.normalise_fit(82, "percent") == 0.82
    assert importer.normalise_fit("", "one_to_five") is None


def test_a_normalised_fit_survives_the_ledger_without_breaking_its_constraint():
    """Batch B's fit_score column has a 0..100 check constraint."""
    from engine import ledger
    for raw in (1, 2, 3, 4, 5):
        value = ledger.fit_score(importer.normalise_fit(raw, "one_to_five"))
        assert 0 <= value <= 100


# --------------------------------------------------------------------------
# The vertical split Dovy chose on 2026-09-14
# --------------------------------------------------------------------------

def test_a_property_administrator_labelled_real_estate_is_let_through():
    vertical, why = importer.resolve_vertical(
        "real estate", "DACAS Dansk Administrationscenter ejendomsadministration")
    assert vertical == "administrative", why


def test_an_estate_agent_labelled_real_estate_is_rejected():
    """Estate agents sell homes. Different business, genuinely off-ICP."""
    vertical, why = importer.resolve_vertical(
        "real estate", "Aarhus Maeglerne ejendomsmaegler")
    assert vertical is None
    assert "exclude signal" in why


def test_an_undecidable_real_estate_row_is_reviewed_not_guessed():
    """The whole point of the split: when no signal fires, a human decides."""
    vertical, why = importer.resolve_vertical("real estate", "Mystery Property Co")
    assert vertical is None
    assert why.startswith("review:")


def test_the_three_locked_verticals_pass_straight_through():
    for label in ("accounting", "insurance", "administrative"):
        assert importer.resolve_vertical(label)[0] == label


def test_every_vertical_the_importer_emits_is_one_the_gate_accepts():
    """A vertical this file maps to but VERTICALS does not carry would be
    hard-rejected downstream - the exact failure 'real estate' already caused."""
    from engine.model import VERTICALS

    vmap = importer.load_vertical_map()
    targets = set((vmap.get("direct") or {}).values())
    for rule in (vmap.get("ambiguous") or {}).values():
        targets |= {k for k in (rule.get("signals") or {}) if k != "exclude"}
    assert targets <= set(VERTICALS), f"maps to non-ICP verticals: {targets - set(VERTICALS)}"


# --------------------------------------------------------------------------
# Market policy, set 2026-09-14: LT, GB, NL. Not US.
# --------------------------------------------------------------------------

def test_country_spellings_are_normalised_to_iso_codes():
    assert importer.normalise_country("United Kingdom") == "GB"
    assert importer.normalise_country("uk") == "GB"
    assert importer.normalise_country("Lithuania") == "LT"
    assert importer.normalise_country("Nederland") == "NL"
    assert importer.normalise_country("USA") == "US"


def test_markets_stay_inside_the_ledgers_enum():
    """Batch B accepts dk|lt|global, so GB and NL ride under global and keep
    their identity in the country column rather than inventing a market B
    would reject outright."""
    from engine import ledger

    for country in ("LT", "GB", "NL", "DK"):
        assert importer.market_for(country) in ledger._B_MARKETS


def test_a_us_row_is_rejected_by_the_country_allowlist(tmp_path):
    report, read = _run(
        tmp_path,
        "US Broker,harrisinsurance.com,US,insurance,25,5,hook,note,H,H,Owner,h@x.com,+1,li")
    assert report.leads == 0 and report.rejected == 1
    assert "allowlist" in read("rejected")[0]["reason"]


def test_denmark_is_not_in_the_email_allowlist_either():
    assert "DK" not in importer.EMAIL_COUNTRIES
    assert "US" not in importer.EMAIL_COUNTRIES
    assert set(importer.EMAIL_COUNTRIES) == {"LT", "GB", "NL"}


# --------------------------------------------------------------------------
# The MX gate, injected rather than resolved over the network
# --------------------------------------------------------------------------

def _fake_mx(mapping):
    def lookup(domains, workers=12, timeout=6.0):
        return {d: mapping[d] for d in {x for x in domains if x} if d in mapping}
    return lookup


def test_a_gateway_fronted_firm_is_parked_not_deleted(tmp_path, monkeypatch):
    """Measured 2026-09-14: kpmg.nl fronts Proofpoint and is Microsoft behind it.
    Deleting these would quietly remove real best-fit prospects."""
    monkeypatch.setattr(importer, "_mx_lookup", _fake_mx({
        "kpmg.nl": MXResult("kpmg.nl", Provider.GATEWAY,
                            ("mxa-00120b03.gslb.pphosted.com",),
                            Unresolved.NONE, "Proofpoint"),
    }))
    report, read = _run(
        tmp_path,
        "KPMG,kpmg.nl,Netherlands,accounting,180,4,hook,note,S,V,Partner,s@kpmg.nl,+31,li",
        check_mx=True)
    assert report.leads == 0 and report.rejected == 0
    assert report.review == 1
    assert "Proofpoint" in read("review")[0]["review_reason"]


def test_a_google_firm_is_rejected_under_the_outlook_only_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "_mx_lookup", _fake_mx({
        "g.lt": MXResult("g.lt", Provider.GOOGLE, ("aspmx.l.google.com",)),
    }))
    report, read = _run(
        tmp_path,
        "G,g.lt,Lithuania,accounting,40,4,hook,note,A,B,Owner,a@g.lt,+370,li",
        check_mx=True)
    assert report.rejected == 1 and report.review == 0
    assert "not Microsoft" in read("rejected")[0]["reason"]


def test_a_timeout_is_parked_because_it_is_not_evidence_of_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "_mx_lookup", _fake_mx({
        "slow.nl": MXResult("slow.nl", Provider.UNKNOWN, (), Unresolved.TIMEOUT),
    }))
    report, _ = _run(
        tmp_path,
        "Slow,slow.nl,Netherlands,accounting,40,4,hook,note,A,B,Owner,a@slow.nl,+31,li",
        check_mx=True)
    assert report.review == 1 and report.rejected == 0


def test_a_microsoft_firm_becomes_a_lead(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "_mx_lookup", _fake_mx({
        "aon.lt": MXResult("aon.lt", Provider.MICROSOFT,
                           ("aon-lt.mail.protection.outlook.com",)),
    }))
    report, read = _run(
        tmp_path,
        "Aon,aon.lt,Lithuania,insurance,40,5,hook,note,T,P,Direktorius,t@aon.lt,+370,li",
        check_mx=True)
    assert report.leads == 1
    lead = read("leads")[0]
    assert lead["mail_provider"] == "microsoft"
    assert lead["market"] == "lt" and lead["locale"] == "lt"
    assert lead["fit_score"] == "1.0"
    assert lead["segment"] == "insurance"


# --------------------------------------------------------------------------
# Contacts, and the invariant that holds the whole thing together
# --------------------------------------------------------------------------

def test_contacts_are_carried_through_when_the_source_has_them(tmp_path):
    _, read = _run(
        tmp_path,
        "Aon,aon.lt,Lithuania,insurance,40,5,hook,note,Tomas,Petrauskas,"
        "Direktorius,tomas@aon.lt,+370 600,https://linkedin.com/in/x")
    contact = read("contacts")[0]
    assert contact["work_email"] == "tomas@aon.lt"
    assert contact["first_name"] == "Tomas" and contact["last_name"] == "Petrauskas"
    assert contact["role"] == "owner_partner"


def test_a_row_without_an_email_still_becomes_a_lead_but_not_a_contact(tmp_path):
    report, read = _run(
        tmp_path,
        "Aon,aon.lt,Lithuania,insurance,40,5,hook,note,Tomas,Petrauskas,Direktorius,,,")
    assert report.leads == 1 and report.contacts == 0
    assert read("contacts") == []


def test_a_full_name_is_split_when_first_and_last_are_absent():
    assert importer.split_name("", "", "Tomas Petrauskas") == ("Tomas", "Petrauskas")
    assert importer.split_name("", "", "Jan van der Berg") == ("Jan", "van der Berg")
    assert importer.split_name("A", "B", "ignored") == ("A", "B")


def test_roles_are_guessed_from_titles_in_every_market_language():
    assert importer.guess_role("Direktorius") == "owner_partner"
    assert importer.guess_role("Office Manager") == "ops_office_manager"
    assert importer.guess_role("IT Manager") == "it_admin"
    assert importer.guess_role("Barista") == "other"


def test_domains_are_cleaned_of_scheme_path_and_www():
    assert importer.clean_domain("https://www.aon.lt/contact") == "aon.lt"
    assert importer.clean_domain("HTTP://KPMG.NL") == "kpmg.nl"
    assert importer.clean_domain("  aon.lt.  ") == "aon.lt"


def test_every_row_leaves_through_exactly_one_output(tmp_path):
    """The invariant the whole design rests on: a row is never lost between the
    four outputs, so 'we found nothing' can never be confused with 'we dropped
    it silently'."""
    report, _ = _run(
        tmp_path,
        "Aon,aon.lt,Lithuania,insurance,40,5,h,n,T,P,Direktorius,t@aon.lt,+370,li",
        "Agent,maegler.lt,Lithuania,real estate,15,4,h,ejendomsmaegler,A,B,Owner,a@maegler.lt,+370,li",
        "Mystery,myst.nl,Netherlands,real estate,30,3,h,no signal,C,D,Owner,c@myst.nl,+31,li",
        "USco,us.com,US,insurance,25,5,h,n,E,F,Owner,e@us.com,+1,li",
        "Legal,law.co.uk,United Kingdom,legal,40,3,h,n,G,H,Partner,g@law.co.uk,+44,li")
    assert report.total_rows == 5
    assert report.reconciles(), report.render()
    assert (report.leads, report.review, report.rejected) == (1, 1, 3)


def test_a_source_missing_a_required_column_fails_loudly(tmp_path):
    """Better to refuse the file than to import half of it."""
    report, _ = _run(tmp_path, "just,two,cols", header="alpha,beta,gamma")
    assert report.missing_required
    assert report.leads == 0


def test_the_report_renders_every_count_it_tracks(tmp_path):
    report, _ = _run(
        tmp_path,
        "Aon,aon.lt,Lithuania,insurance,40,5,h,n,T,P,Direktorius,t@aon.lt,+370,li")
    text = report.render()
    for expected in ("rows in", "leads", "review", "rejected", "fit_score scale"):
        assert expected in text
