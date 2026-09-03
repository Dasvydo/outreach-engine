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


def test_only_the_global_market_is_an_email_market():
    """Lithuania is excluded too, for a different reason: unverified addresses."""
    assert load_instantly.EMAIL_MARKETS == ("global",)
    lt = _contact(market="lt", country="LT", work_email="rasa@pavyzdys.lt",
                  phone="+370 600 00001")
    keep, refused = load_instantly.eligible([lt])
    assert keep == []
    assert "not an email market" in refused[0][1]


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
