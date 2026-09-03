"""Reading contacts back out of the campaign.

There is a seam here worth naming. The eleven functions Batch B exposes on
`campaign_db.py` are eight writes and three aggregate reads
(`get_market_funnel`, `get_channel_funnel`, `get_content_perf`). None of them
returns a list of contacts. So a loader that needs "every contact in market
global" has nowhere to ask, and until Batch B adds a reader the loaders read a
CSV export instead. See BLOCKED.md B14.

That is why `load_contacts()` takes a path. Point it at a real export when one
exists; it defaults to the sample fixture so the dry runs and tests work today.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTACTS = ROOT / "fixtures" / "contacts" / "sample-contacts.csv"

# Straight from the shared qualifier payload contract in 00-START-HERE.md.
ROLES = ("owner_partner", "ops_office_manager", "it_admin", "other")


@dataclass
class ContactRow:
    company_domain: str
    company_name: str
    first_name: str
    last_name: str
    role: str
    title: str
    work_email: str
    phone: str
    linkedin_url: str
    market: str
    locale: str
    segment: str
    country: str
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p)

    @property
    def email_domain(self) -> str:
        return self.work_email.rsplit("@", 1)[-1].strip().lower() if "@" in self.work_email else ""


def load_contacts(path: Path | str | None = None, *,
                  market: str | None = None) -> list[ContactRow]:
    """Read contacts from a CSV export. Optionally filter to one market."""
    path = Path(path or DEFAULT_CONTACTS)
    if not path.exists():
        raise FileNotFoundError(
            f"no contacts file at {path}. Pass --contacts, or export "
            f"campaign.contacts to CSV once Batch B has a reader."
        )
    rows: list[ContactRow] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            row = ContactRow(
                company_domain=(raw.get("company_domain") or "").strip().lower(),
                company_name=(raw.get("company_name") or "").strip(),
                first_name=(raw.get("first_name") or "").strip(),
                last_name=(raw.get("last_name") or "").strip(),
                role=(raw.get("role") or "other").strip(),
                title=(raw.get("title") or "").strip(),
                work_email=(raw.get("work_email") or "").strip(),
                phone=(raw.get("phone") or "").strip(),
                linkedin_url=(raw.get("linkedin_url") or "").strip(),
                market=(raw.get("market") or "").strip().lower(),
                locale=(raw.get("locale") or "").strip().lower(),
                segment=(raw.get("segment") or "").strip(),
                country=(raw.get("country") or "").strip().upper(),
            )
            if market and row.market != market:
                continue
            rows.append(row)
    return rows
