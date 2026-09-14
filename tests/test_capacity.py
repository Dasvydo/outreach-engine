"""Slide 7 of the outbound-machine deck, asserted.

The reason this module is tested rather than left as a spreadsheet: a market
problem and a copy problem look identical from inside a running campaign - the
reply rate is bad either way - and the fixes are opposites. Getting the verdict
wrong means buying inboxes to cure a market that was never big enough.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.capacity import (                                   # noqa: E402
    VERGELEAD, FunnelRates, Infrastructure, Market, infrastructure_for, plan,
)


# --------------------------------------------------------------------------
# The deck's own arithmetic, reproduced
# --------------------------------------------------------------------------

def test_the_decks_funnel_yields_its_own_stated_headline():
    """1,000 emails -> 1 discovery; 10 discoveries -> 7 demos; 7 demos -> 1-2
    clients. The deck rounds the product to 'about 6,700 emails per client'."""
    assert 6600 <= VERGELEAD.emails_per_client <= 6700


def test_the_decks_twenty_inbox_figure_falls_out_of_its_own_numbers():
    """'6,700 / 22 days / 15 per inbox = 20 inboxes' - slide 7, verbatim.

    The exact quotient is 20.3, which the deck rounds down to 20. This function
    rounds UP, because 20 inboxes cannot send what 20.3 inboxes' worth requires
    and under-provisioning is the more expensive direction of the two.
    """
    infra = infrastructure_for(round(VERGELEAD.emails_per_client))
    assert infra.inboxes == 21
    assert 20 <= VERGELEAD.emails_per_client / (15 * 22) <= 21


def test_the_infrastructure_constraint_is_fifteen_a_day_not_eighteen():
    """Slide 8 says 15 emails per day per account. The campaign plan assumed 18,
    which is a 20% overstatement of capacity before anything else is wrong."""
    assert Infrastructure().emails_per_inbox_per_day == 15
    assert Infrastructure(inboxes=45).emails_per_month == 45 * 15 * 22


def test_domains_follow_the_three_inboxes_per_domain_rule():
    assert Infrastructure(inboxes=45).domains == 15
    assert Infrastructure(inboxes=20).domains == 7
    assert Infrastructure(inboxes=0).domains == 0


# --------------------------------------------------------------------------
# The flip - the part the deck says nobody in the room knows
# --------------------------------------------------------------------------

def test_a_market_smaller_than_the_monthly_burn_is_named_a_market_problem():
    """The deck: 'TAM of 4,000 companies but you need 6,000 contacts a month?
    You don't have a copy problem. You have a market problem.'"""
    # Their scenario burns 6,000 contacts a month, which at 4 touches each is
    # 24,000 emails, which is 73 inboxes - not the 45 this campaign planned.
    out = plan(Market(companies=4000, contacts_per_company=1.0),
               Infrastructure(inboxes=73))
    assert out.contacts_needed_per_month >= 6000
    assert "MARKET PROBLEM" in out.verdict
    assert any("Not a bigger list" in n for n in out.notes)


def test_lithuania_measured_is_a_market_problem_for_this_plan():
    """LT accounting 134 + LT insurance 40 = 174 ICP companies, from Eurostat
    SBS_SC_OVW and Statistics Lithuania, 2024. Against 45 inboxes that is days
    of sending, not a market."""
    out = plan(Market(companies=174), Infrastructure(inboxes=45))
    assert "MARKET PROBLEM" in out.verdict
    assert out.months_to_exhaust_market < 0.2


def test_a_market_that_lasts_under_six_months_is_flagged_as_thin():
    out = plan(Market(companies=8000, reachable_share=0.4),
               Infrastructure(inboxes=45))
    assert "THIN" in out.verdict
    assert 1.0 < out.months_to_exhaust_market < 3.0


def test_a_large_enough_market_is_capacity_bound_not_market_bound():
    out = plan(Market(companies=500_000), Infrastructure(inboxes=45))
    assert "CAPACITY-BOUND" in out.verdict


def test_the_mx_gate_shrinks_the_market_that_counts():
    """Only Microsoft firms are reachable, so the reachable share is part of the
    market size rather than a detail of the pipeline."""
    everything = Market(companies=10_000, reachable_share=1.0).contacts
    microsoft_only = Market(companies=10_000, reachable_share=0.4).contacts
    assert microsoft_only == int(everything * 0.4)


# --------------------------------------------------------------------------
# Revenue goal -> hardware, in one step
# --------------------------------------------------------------------------

def test_a_revenue_goal_becomes_an_inbox_count():
    out = plan(Market(companies=500_000), Infrastructure(inboxes=45),
               price_per_client_per_month=2225.0, revenue_goal_per_month=10_000.0)
    assert 80 <= out.inboxes_needed_for_goal <= 100
    assert out.domains_needed_for_goal == -(-out.inboxes_needed_for_goal // 3)


def test_price_per_client_moves_the_hardware_requirement_by_orders_of_magnitude():
    """The deck's rates were measured on a client worth EUR 25,000+. At 89 a
    month the same funnel needs ~25x the infrastructure for the same revenue,
    which is the single assumption most worth checking before spending."""
    cheap = plan(Market(companies=500_000), price_per_client_per_month=89.0,
                 revenue_goal_per_month=10_000.0)
    dear = plan(Market(companies=500_000), price_per_client_per_month=2225.0,
                revenue_goal_per_month=10_000.0)
    assert cheap.inboxes_needed_for_goal > 20 * dear.inboxes_needed_for_goal


def test_poor_unit_economics_are_called_out_rather_than_quietly_reported():
    out = plan(Market(companies=500_000), price_per_client_per_month=89.0)
    assert any("unit economics" in n for n in out.notes)


def test_healthy_unit_economics_raise_no_such_note():
    out = plan(Market(companies=500_000), price_per_client_per_month=25_000.0)
    assert not any("unit economics" in n for n in out.notes)


# --------------------------------------------------------------------------
# Substituting your own rates, which is the point once replies exist
# --------------------------------------------------------------------------

def test_your_own_rates_replace_the_decks_wholesale():
    optimistic = FunnelRates(emails_per_discovery=400.0, demos_per_discovery=0.8,
                             clients_per_demo=0.4, source="ours, after 50 replies")
    assert optimistic.emails_per_client < VERGELEAD.emails_per_client
    out = plan(Market(companies=500_000), rates=optimistic)
    assert out.clients_per_month > plan(Market(companies=500_000)).clients_per_month


def test_a_dead_funnel_does_not_divide_by_zero():
    dead = FunnelRates(clients_per_demo=0.0)
    assert dead.emails_per_client == float("inf")
    out = plan(Market(companies=1000), rates=dead)
    assert out.clients_per_month == 0.0


def test_the_render_states_the_verdict_and_the_borrowed_rates():
    text = plan(Market(companies=174), Infrastructure(inboxes=45)).render()
    assert "VERDICT" in text
    assert "someone else's rate" in text
