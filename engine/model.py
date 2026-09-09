"""Core records. The Lead JSON is the API boundary of this engine.

List building writes Leads; the gate filters them; sequencing reads them;
export consumes them. Everything upstream exists to produce more Leads.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from engine.enrich import Provider

VERTICALS = ("accounting", "administrative", "insurance")
COUNTRIES = ("DK", "LT")


@dataclass
class Firm:
    name: str
    domain: str
    country: str                      # DK | LT
    vertical: str                     # accounting | administrative | insurance
    nace: str = ""                    # 69.20 | 82.11 | 66.22
    employees: int | None = None      # None = unknown, not zero
    city: str = ""
    registry_id: str = ""             # CVR number, or LT juridinio asmens kodas
    provider: Provider = Provider.UNKNOWN
    has_dev_team: bool | None = None  # G6; None = not yet assessed
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provider"] = self.provider.value
        return d


@dataclass
class Contact:
    firm: Firm
    email: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    linkedin: str = ""

    # Passed a bounce check. NOT PERSISTED, and currently never set: nothing in
    # this repo writes it and campaign.contacts has no column for it, so
    # engine/ledger.py's upsert_contact cannot forward it. Batch B accepts
    # exactly full_name, role_guess, linkedin_url, email and email_source
    # alongside company_id and market. Every other Contact field IS forwarded -
    # first_name and last_name are joined into full_name, title becomes
    # role_guess, and firm is decomposed into company_id and market - so this is
    # the only one that would be lost, and it is lost from a value that is
    # always False today. Setting it and expecting it to reach the ledger is the
    # trap this comment exists to prevent: adding a column is Batch B's call
    # (ops/DECISIONS.md B-03).
    verified: bool = False

    @property
    def language(self) -> str:
        """Outreach language follows the firm's country, not the contact."""
        return {"DK": "da", "LT": "lt"}.get(self.firm.country, "en")


@dataclass
class Campaign:
    id: str
    vertical: str
    country: str
    copy_variant: str
    contacts: list[Contact] = field(default_factory=list)

    @property
    def cell(self) -> str:
        """The A/B cell this campaign occupies, e.g. accounting-DK-capacity."""
        return f"{self.vertical}-{self.country}-{self.copy_variant}"
