"""The wire contract with Instantly, asserted.

This file exists because every defect it covers was invisible: the loader had
never run, so a wrong endpoint, a wrong field name and a ledger that recorded
sends the API never accepted all looked exactly like working code. None of them
would have surfaced until the first live push, against real warmed domains, with
real prospects on the other end.

Nothing here touches the network.
"""

import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import load_instantly                                    # noqa: E402
from engine.contacts import ContactRow                   # noqa: E402

CAMPAIGN = "019cc043-e39c-7d91-a325-66191be14c42"


def _contact(**kw):
    base = dict(company_domain="example.co.uk", company_name="Example Ltd",
                first_name="Ann", last_name="Webb", role="owner_partner",
                title="Partner", work_email="ann@example.co.uk",
                phone="+44 20 0000 0001", linkedin_url="https://li/x",
                market="global", locale="en", segment="accounting", country="GB")
    base.update(kw)
    return ContactRow(**base)


HOOKS = {"segments": {}}


# --------------------------------------------------------------------------
# The two defects that would have failed on the first live call
# --------------------------------------------------------------------------

def test_the_bulk_endpoint_is_the_one_we_post_to():
    """/api/v2/leads takes ONE flat lead. /api/v2/leads/add takes the `leads`
    array this loader builds. Posting the array shape to the singular URL is
    what the file shipped with."""
    assert load_instantly.INSTANTLY_API.endswith("/api/v2/leads/add")


def test_the_campaign_field_is_campaign_id_not_campaign():
    """`campaign` is the single-lead endpoint's name. On the bulk endpoint it is
    silently ignored, so the leads would import with no campaign attached and
    simply never send - the worst failure shape available, because it looks like
    a success."""
    payload = load_instantly.build_payload([_contact()], CAMPAIGN, HOOKS)
    assert payload["campaign_id"] == CAMPAIGN
    assert "campaign" not in payload


def test_a_non_uuid_campaign_id_is_recognised_as_invalid():
    """The old default was the literal string 'teams_q4_global'."""
    assert load_instantly.is_uuid(CAMPAIGN)
    assert not load_instantly.is_uuid("teams_q4_global")
    assert not load_instantly.is_uuid("")
    assert not load_instantly.is_uuid(None)


def test_custom_variable_values_stay_scalar():
    """The spec permits string, number, boolean and null - objects and arrays
    are rejected, and a rejected batch is a silent gap in the campaign."""
    payload = load_instantly.build_payload([_contact()], CAMPAIGN, HOOKS)
    for value in payload["leads"][0]["custom_variables"].values():
        assert isinstance(value, (str, int, float, bool)) or value is None


def test_the_landing_page_points_at_a_domain_that_exists():
    """teams.doviloop.dev was never registered. Every click would have died."""
    page = load_instantly.build_payload([_contact()], CAMPAIGN,
                                        HOOKS)["leads"][0]["custom_variables"]["landingPage"]
    assert "teams.doviloop.dev" not in page
    assert page.startswith("https://campaign-site-azure.vercel.app/")


# --------------------------------------------------------------------------
# Batching
# --------------------------------------------------------------------------

def test_batches_stay_under_the_thousand_lead_cap():
    assert load_instantly.MAX_LEADS_PER_REQUEST <= 1000
    batches = list(load_instantly.chunked(list(range(1201))))
    assert sum(len(b) for b in batches) == 1201
    assert all(len(b) <= load_instantly.MAX_LEADS_PER_REQUEST for b in batches)


def test_chunking_an_empty_list_yields_nothing():
    assert list(load_instantly.chunked([])) == []


# --------------------------------------------------------------------------
# The ledger must record what happened, not what was attempted
# --------------------------------------------------------------------------

def _fake_request(monkeypatch, responses):
    """Feed canned API responses; record the requests that were made."""
    calls = []
    queue = list(responses)

    def fake(url, api_key, payload=None, method="POST", timeout=60.0):
        calls.append({"url": url, "method": method, "payload": payload})
        return queue.pop(0) if queue else {}

    monkeypatch.setattr(load_instantly, "_request", fake)
    return calls


def test_only_leads_instantly_accepted_come_back_as_accepted(monkeypatch):
    """The old code logged a `sent` touch for every contact it intended to send,
    whatever the response said. A half-failed batch produced a ledger that
    confidently disagreed with reality."""
    contacts = [_contact(work_email=f"a{i}@example.co.uk") for i in range(10)]
    _fake_request(monkeypatch, [{"leads_uploaded": 6, "in_blocklist": 3,
                                 "invalid_email_count": 1}])

    accepted, totals = load_instantly.push(contacts, CAMPAIGN, HOOKS, "key")
    assert len(accepted) == 6
    assert totals["in_blocklist"] == 3
    assert totals["invalid_email_count"] == 1


def test_totals_accumulate_across_batches(monkeypatch):
    contacts = [_contact(work_email=f"a{i}@example.co.uk") for i in range(900)]
    _fake_request(monkeypatch, [{"leads_uploaded": 500}, {"leads_uploaded": 400}])
    accepted, totals = load_instantly.push(contacts, CAMPAIGN, HOOKS, "key")
    assert totals["leads_uploaded"] == 900
    assert len(accepted) == 900


def test_a_response_with_no_count_is_taken_at_face_value(monkeypatch):
    """An API that stops reporting counts must not silently zero the ledger."""
    contacts = [_contact(work_email=f"a{i}@example.co.uk") for i in range(5)]
    _fake_request(monkeypatch, [{}])
    accepted, _ = load_instantly.push(contacts, CAMPAIGN, HOOKS, "key")
    assert len(accepted) == 5


def test_every_batch_carries_the_campaign_id(monkeypatch):
    contacts = [_contact(work_email=f"a{i}@example.co.uk") for i in range(900)]
    calls = _fake_request(monkeypatch, [{"leads_uploaded": 500}, {"leads_uploaded": 400}])
    load_instantly.push(contacts, CAMPAIGN, HOOKS, "key")
    assert len(calls) == 2
    for call in calls:
        assert call["payload"]["campaign_id"] == CAMPAIGN
        assert call["url"].endswith("/leads/add")


# --------------------------------------------------------------------------
# Suppression - the one that is a legal problem rather than a bug
# --------------------------------------------------------------------------

def test_a_blocked_address_is_suppressed():
    blocklist = {"ann@example.co.uk"}
    assert load_instantly.suppressed(_contact(), blocklist)


def test_a_blocked_domain_suppresses_every_address_on_it():
    """The Global Blocklist holds whole domains as well as addresses."""
    blocklist = {"example.co.uk"}
    assert load_instantly.suppressed(_contact(work_email="someone@example.co.uk"),
                                     blocklist)


def test_an_unblocked_contact_is_not_suppressed():
    assert not load_instantly.suppressed(_contact(), {"other@elsewhere.com"})


def test_the_blocklist_is_paged_to_the_end(monkeypatch):
    """A partial read looks like a shorter blocklist, which means re-mailing
    people who opted out. Paging has to be exhaustive or not attempted."""
    pages = [
        {"items": [{"bl_value": "a@x.com"}], "next_starting_after": "cur1"},
        {"items": [{"bl_value": "B@Y.COM"}, {"bl_value": "spam.dk"}]},
    ]
    monkeypatch.setattr(load_instantly, "_request",
                        lambda url, key, payload=None, method="POST", timeout=60.0: pages.pop(0))
    blocked = load_instantly.fetch_blocklist("key")
    assert blocked == {"a@x.com", "b@y.com", "spam.dk"}


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------

def test_rate_limiting_is_retried_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"leads_uploaded": 1}'

    def fake_urlopen(request, timeout=60):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise urllib.error.HTTPError(
                "u", 429, "Too Many Requests", {"Retry-After": "0"}, None)
        return Resp()

    monkeypatch.setattr(load_instantly.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(load_instantly.time, "sleep", lambda s: None)
    monkeypatch.setattr(load_instantly.json, "load", lambda fh: json.loads(fh.read()))

    body = load_instantly._request("https://x", "key", {"a": 1})
    assert body == {"leads_uploaded": 1}
    assert attempts["n"] == 3


def test_an_auth_failure_raises_rather_than_retrying(monkeypatch):
    """A 401 will never come good, and failing closed beats logging phantom
    sends."""
    class Err(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("u", 401, "Unauthorized", {}, None)
        def read(self): return b'{"error":"bad key"}'

    def fake_urlopen(request, timeout=60):
        raise Err()

    monkeypatch.setattr(load_instantly.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="401"):
        load_instantly._request("https://x", "key", {"a": 1})


def test_the_api_key_never_appears_in_an_error_message(monkeypatch):
    class Err(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("u", 400, "Bad Request", {}, None)
        def read(self): return b'{"error":"nope"}'

    monkeypatch.setattr(load_instantly.urllib.request, "urlopen",
                        lambda request, timeout=60: (_ for _ in ()).throw(Err()))
    with pytest.raises(RuntimeError) as caught:
        load_instantly._request("https://x", "sk-secret-value", {"a": 1})
    assert "sk-secret-value" not in str(caught.value)
