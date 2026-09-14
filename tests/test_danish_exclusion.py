"""Danish addresses must not be able to reach the Instantly loader.

This is a legal requirement, not a preference. Denmark's marketing law is
stricter than the rest of the EU on unsolicited commercial email, so no Danish
address goes into Instantly until Dovy confirms otherwise in writing. Denmark is
worked through LinkedIn and phone instead.

The tests below attack the exclusion from every direction a real dataset would:
a correctly labelled Danish contact, one mislabelled into the global market, one
with a foreign country code but a .dk address, and one with neither but a Danish
phone number. Then they check the loader's own last line of defence still fires
if somebody bypasses the filter entirely.

If any test in this file fails, the loader is not safe to run.
"""

import pytest

import load_instantly
from engine.contacts import ContactRow


def _contact(**kw) -> ContactRow:
    base = dict(
        company_domain="example-accounting.com", company_name="Example Accounting",
        first_name="Sarah", last_name="Miller", role="owner_partner",
        title="Partner", work_email="sarah@example-accounting.com",
        phone="+1 555 0100", linkedin_url="https://linkedin.com/in/x",
        market="global", locale="en", segment="accounting", country="US",
    )
    base.update(kw)
    return ContactRow(**base)


# --- the four independent exclusion signals ------------------------------

def test_contact_in_the_dk_market_is_refused():
    contact = _contact(market="dk", country="DK",
                       work_email="mette@eksempel-revision.dk", phone="+45 20 00 00 01")
    keep, refused = load_instantly.eligible([contact])
    assert keep == []
    assert "Danish exclusion" in refused[0][1]


def test_danish_company_mislabelled_as_global_is_still_refused():
    """The realistic failure. Somebody tags a Danish firm `global` by hand."""
    contact = _contact(market="global", country="DK",
                       work_email="lars@mislabelled.dk", phone="+45 20 00 00 04")
    keep, refused = load_instantly.eligible([contact])
    assert keep == []
    assert "Danish exclusion" in refused[0][1]


def test_dk_email_domain_alone_is_enough_to_refuse():
    """Market and country both say global. Only the address is Danish."""
    contact = _contact(market="global", country="US",
                       work_email="someone@firma.dk", phone="+1 555 0100")
    keep, refused = load_instantly.eligible([contact])
    assert keep == []
    assert ".dk domain" in refused[0][1]


def test_danish_phone_number_alone_is_enough_to_refuse():
    """Every other field is clean. The phone number gives it away."""
    contact = _contact(market="global", country="US",
                       work_email="someone@example.com", phone="+45 20 00 00 09")
    keep, refused = load_instantly.eligible([contact])
    assert keep == []
    assert "+45" in refused[0][1]


# --- the loader's last line of defence -----------------------------------

def test_build_payload_raises_if_a_danish_contact_gets_past_the_filter():
    """Simulates a future caller that forgets to run eligible() first."""
    danish = _contact(market="dk", country="DK", work_email="mette@revision.dk")
    with pytest.raises(load_instantly.DanishAddressRefused):
        load_instantly.build_payload([danish], "teams_q4_global", {"segments": {}})


def test_no_danish_address_survives_into_a_real_payload():
    """End to end over the shipped fixture, which contains four Danish rows."""
    from engine.contacts import load_contacts
    import yaml
    from pathlib import Path

    hooks = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "config" / "hooks.yaml")
        .read_text(encoding="utf-8"))
    contacts = load_contacts()
    keep, refused = load_instantly.eligible(contacts)

    danish_refusals = [r for _, r in refused if r.startswith("Danish exclusion")]
    assert len(danish_refusals) == 4, "the fixture is supposed to contain four Danish rows"

    payload = load_instantly.build_payload(keep, "teams_q4_global", hooks)
    emails = [lead["email"] for lead in payload["leads"]]
    assert emails, "the test is worthless if the payload is empty"
    for email in emails:
        assert not email.endswith(".dk"), f"{email} reached the Instantly payload"


def test_lithuania_is_now_an_email_market():
    """Changed 2026-09-14 on Dovy's instruction, and the law agrees.

    LT was previously held back for unverified addresses. AI Arc now supplies
    verified contacts, and Elektroniniu rysiu istatymas Art. 81(1) as amended by
    Law XV-815 of 2026-04-16 carves legal persons out of the prior-consent rule,
    so Lithuania is the one market here that got easier rather than harder.
    """
    assert "lt" in load_instantly.EMAIL_MARKETS
    lt = _contact(market="lt", country="LT", work_email="rasa@pavyzdys.lt",
                  phone="+370 600 00001")
    keep, refused = load_instantly.eligible([lt])
    assert [c.work_email for c in keep] == ["rasa@pavyzdys.lt"], refused


def test_the_united_states_is_not_in_the_email_allowlist():
    """Excluded by choice rather than by law - Dovy, 2026-09-14."""
    assert "US" not in load_instantly.EMAIL_COUNTRIES
    us = _contact(market="global", country="US",
                  work_email="hank@example.com", phone="+1 850 000 0001")
    keep, refused = load_instantly.eligible([us])
    assert keep == []
    assert "allowlist" in refused[0][1]


def test_the_netherlands_is_refused_until_counsel_confirms():
    """Telecommunicatiewet art. 11.7(1) has covered business recipients since
    2009 and needs provable prior consent, with KvK register data expressly
    excluded as a basis for it. Unlike Denmark this HAS a switch, because it is
    a research finding rather than settled advice - but it defaults closed."""
    assert load_instantly.NL_CONSENT_CONFIRMED is False
    nl = _contact(market="global", country="NL",
                  work_email="jan@voorbeeld.nl", phone="+31 20 000 0001")
    keep, refused = load_instantly.eligible([nl])
    assert keep == []
    assert "11.7" in refused[0][1]


def test_the_dutch_switch_actually_opens_when_set(monkeypatch):
    """A gate nobody can open is a deleted market, not a gate. Prove the switch
    works so that turning it on is a decision rather than an excavation."""
    monkeypatch.setattr(load_instantly, "NL_CONSENT_CONFIRMED", True)
    nl = _contact(market="global", country="NL",
                  work_email="jan@voorbeeld.nl", phone="+31 20 000 0001")
    keep, _ = load_instantly.eligible([nl])
    assert [c.work_email for c in keep] == ["jan@voorbeeld.nl"]


def test_denmark_has_no_such_switch_and_never_will():
    """The contrast that matters: NL is gated, DK is excluded. Setting the Dutch
    flag must not create a path for a Danish address."""
    monkeypatched = dict(vars(load_instantly))
    assert not any("NL_CONSENT" in k and "DK" in k for k in monkeypatched)
    dk = _contact(market="global", country="DK",
                  work_email="mette@eksempel.dk", phone="+45 20 00 00 01")
    load_instantly.NL_CONSENT_CONFIRMED = True
    try:
        keep, refused = load_instantly.eligible([dk])
    finally:
        load_instantly.NL_CONSENT_CONFIRMED = False
    assert keep == []
    assert refused[0][1].startswith("Danish exclusion")


def test_the_exclusion_has_no_off_switch():
    """No argument, flag or environment variable may disable it.

    Reads the loader's own argument parser rather than trusting a comment.
    """
    import argparse
    parser_actions = []

    original = argparse.ArgumentParser.add_argument

    def spy(self, *args, **kwargs):
        parser_actions.extend(a for a in args if isinstance(a, str))
        return original(self, *args, **kwargs)

    argparse.ArgumentParser.add_argument = spy
    try:
        try:
            load_instantly.main(["--dry-run"])
        except SystemExit:
            pass
    finally:
        argparse.ArgumentParser.add_argument = original

    banned = [a for a in parser_actions
              if "danish" in a.lower() or "allow-dk" in a.lower() or "no-dk" in a.lower()]
    assert banned == [], f"the loader grew a flag that touches the exclusion: {banned}"
