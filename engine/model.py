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
    verified: bool = False            # passed a bounce check

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
