"""Turn a revenue goal into a hardware requirement, and catch a market problem.

This is slide 7 of the VergeLead "outbound machine" deck made executable - the
part the deck calls "the number nobody in this room knows". Their own measured
funnel, for a high-ticket B2B service:

    1,000 emails   ->  1 discovery call
    10 discoveries ->  7 qualified demos
    7 demos        ->  1 to 2 clients
                   =  ~6,700 emails per client won
    6,700 / 22 working days / 15 per inbox = 20 inboxes

and slide 8's infrastructure constraint: 15 emails per day per account, on
sending domains that are never the domain the invoices go out from.

THE FLIP, WHICH IS THE WHOLE POINT
----------------------------------
The deck states it plainly: "TAM of 4,000 companies but you need 6,000 contacts
a month? You don't have a copy problem. You have a market problem. Way out: more
channels per contact, or higher frequency over a longer cycle. Not a bigger
list."

`plan()` computes both directions and says which problem you have, because those
two failures look identical from inside a campaign - reply rates are bad either
way - and the fixes are opposites. Buying more inboxes to solve a market problem
is the expensive mistake this module exists to prevent.

RATES ARE SOMEONE ELSE'S UNTIL THEY ARE YOURS
---------------------------------------------
`VERGELEAD` are measured, but measured on a different product at a different
price point: the deck's own slide 3 cites a single client worth EUR 25,000+.
Conversion arithmetic does not transfer across an order of magnitude of price -
what one deal is worth decides how many emails it can justify. Substitute your
own rates as soon as you have fifty replies of your own; until then these are a
starting prior and are labelled as such in the output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FunnelRates:
    """Conversion from sent email through to a won client."""

    emails_per_discovery: float = 1000.0   # deck: 1,000 emails -> 1 discovery
    demos_per_discovery: float = 0.7       # deck: 10 discoveries -> 7 demos
    clients_per_demo: float = 1.5 / 7.0    # deck: 7 demos -> 1 to 2 clients
    source: str = "VergeLead deck, measured on a ~EUR 25k service"

    @property
    def emails_per_client(self) -> float:
        per_client = self.demos_per_discovery * self.clients_per_demo
        if per_client <= 0:
            return float("inf")
        return self.emails_per_discovery / per_client


VERGELEAD = FunnelRates()


@dataclass(frozen=True)
class Infrastructure:
    """What the sending side can physically do in a month."""

    inboxes: int = 45
    emails_per_inbox_per_day: int = 15     # deck slide 8; NOT 18
    working_days_per_month: int = 22
    inboxes_per_domain: int = 3

    @property
    def emails_per_month(self) -> int:
        return self.inboxes * self.emails_per_inbox_per_day * self.working_days_per_month

    @property
    def domains(self) -> int:
        return math.ceil(self.inboxes / self.inboxes_per_domain) if self.inboxes else 0


@dataclass(frozen=True)
class Market:
    """The addressable market, after every filter that actually applies."""

    companies: int                      # firms matching the ICP
    contacts_per_company: float = 2.0   # named, reachable people per firm
    reachable_share: float = 1.0        # survives the MX gate, verification, etc.

    @property
    def contacts(self) -> int:
        return int(self.companies * self.contacts_per_company * self.reachable_share)


@dataclass(frozen=True)
class Plan:
    emails_per_month: int
    emails_per_client: float
    clients_per_month: float
    revenue_per_month: float
    contacts_needed_per_month: int
    market_contacts: int
    months_to_exhaust_market: float
    inboxes_needed_for_goal: int
    domains_needed_for_goal: int
    verdict: str
    notes: tuple[str, ...]

    def render(self) -> str:
        lines = [
            f"sending capacity     {self.emails_per_month:,} emails/month",
            f"emails per client    {self.emails_per_client:,.0f}  (someone else's rate until it is yours)",
            f"clients/month        {self.clients_per_month:.2f}",
            f"revenue/month        {self.revenue_per_month:,.0f} at steady state from one month's wins",
            "",
            f"new contacts needed  {self.contacts_needed_per_month:,}/month",
            f"market contacts      {self.market_contacts:,}",
            f"market exhausted in  {self.months_to_exhaust_market:.1f} months"
            if math.isfinite(self.months_to_exhaust_market) else
            "market exhausted in  never (market is larger than the plan can consume)",
            "",
            f"VERDICT: {self.verdict}",
        ]
        lines += [f"  - {n}" for n in self.notes]
        return "\n".join(lines)


def plan(
    market: Market,
    infra: Infrastructure = Infrastructure(),
    rates: FunnelRates = VERGELEAD,
    *,
    touches_per_contact: int = 4,
    price_per_client_per_month: float = 89.0,
    revenue_goal_per_month: float | None = None,
) -> Plan:
    """Work the funnel both ways and name which problem you have."""
    emails = infra.emails_per_month
    per_client = rates.emails_per_client
    clients = emails / per_client if per_client else 0.0

    contacts_needed = int(math.ceil(emails / max(1, touches_per_contact)))
    market_contacts = market.contacts
    months = (market_contacts / contacts_needed) if contacts_needed else float("inf")

    notes: list[str] = []

    # Direction two: what the revenue goal demands, independent of what is owned.
    inboxes_needed = infra.inboxes
    if revenue_goal_per_month and price_per_client_per_month > 0:
        clients_needed = revenue_goal_per_month / price_per_client_per_month
        emails_needed = clients_needed * per_client
        per_inbox_month = infra.emails_per_inbox_per_day * infra.working_days_per_month
        inboxes_needed = int(math.ceil(emails_needed / per_inbox_month)) if per_inbox_month else 0
        notes.append(
            f"a goal of {revenue_goal_per_month:,.0f}/month needs {clients_needed:,.0f} clients, "
            f"{emails_needed:,.0f} emails and {inboxes_needed:,} inboxes")
    domains_needed = math.ceil(inboxes_needed / infra.inboxes_per_domain) if inboxes_needed else 0

    # The flip: is the market big enough to feed the hardware?
    if market_contacts < contacts_needed:
        verdict = ("MARKET PROBLEM - the list cannot feed the infrastructure. "
                   "More inboxes will not help.")
        notes.append(
            f"the whole market is {market_contacts:,} contacts and this plan consumes "
            f"{contacts_needed:,} every month")
        notes.append("way out: more channels per contact, or a longer cycle at lower "
                     "frequency. Not a bigger list.")
    elif months < 6:
        verdict = (f"MARKET IS THIN - the entire market is consumed in "
                   f"{months:.1f} months at this volume.")
        notes.append("size the infrastructure to the market, not the other way round")
    else:
        verdict = "CAPACITY-BOUND - the market can feed this. Sending volume is the limit."

    # Unit economics. The deck's rates were measured on a service worth roughly
    # EUR 25k a client; at two orders of magnitude less per client the same
    # funnel stops paying for itself, so say so rather than reporting a number.
    revenue = clients * price_per_client_per_month
    if per_client > 0 and price_per_client_per_month > 0:
        emails_per_currency_unit = per_client / price_per_client_per_month
        if emails_per_currency_unit > 50:
            notes.append(
                f"unit economics: {per_client:,.0f} emails to win {price_per_client_per_month:,.0f} "
                f"per month of revenue - {emails_per_currency_unit:,.0f} emails per unit of "
                f"monthly revenue. These rates came from a much higher-priced offer; "
                f"re-check them against your own before trusting this plan.")

    return Plan(
        emails_per_month=emails,
        emails_per_client=per_client,
        clients_per_month=clients,
        revenue_per_month=revenue,
        contacts_needed_per_month=contacts_needed,
        market_contacts=market_contacts,
        months_to_exhaust_market=months,
        inboxes_needed_for_goal=inboxes_needed,
        domains_needed_for_goal=domains_needed,
        verdict=verdict,
        notes=tuple(notes),
    )


def infrastructure_for(
    emails_per_month: int, infra: Infrastructure = Infrastructure()
) -> Infrastructure:
    """The smallest infrastructure that can send this much."""
    per_inbox = infra.emails_per_inbox_per_day * infra.working_days_per_month
    inboxes = int(math.ceil(emails_per_month / per_inbox)) if per_inbox else 0
    return replace(infra, inboxes=inboxes)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="capacity",
        description="Turn a revenue goal into inboxes, and catch a market problem.")
    p.add_argument("--companies", type=int, required=True,
                   help="ICP companies in the addressable market")
    p.add_argument("--contacts-per-company", type=float, default=2.0)
    p.add_argument("--reachable-share", type=float, default=1.0,
                   help="share surviving the MX gate and email verification")
    p.add_argument("--inboxes", type=int, default=45)
    p.add_argument("--per-inbox-per-day", type=int, default=15)
    p.add_argument("--working-days", type=int, default=22)
    p.add_argument("--inboxes-per-domain", type=int, default=3)
    p.add_argument("--touches", type=int, default=4, help="emails per contact in a sequence")
    p.add_argument("--price", type=float, default=89.0, help="price per client per month")
    p.add_argument("--goal", type=float, help="revenue goal per month")
    args = p.parse_args(argv)

    out = plan(
        Market(args.companies, args.contacts_per_company, args.reachable_share),
        Infrastructure(args.inboxes, args.per_inbox_per_day,
                       args.working_days, args.inboxes_per_domain),
        touches_per_contact=args.touches,
        price_per_client_per_month=args.price,
        revenue_goal_per_month=args.goal,
    )
    print(out.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
