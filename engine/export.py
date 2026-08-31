"""Export a campaign to an Instantly-importable CSV.

Instantly maps CSV headers to lead fields; anything extra becomes a custom
variable usable as {{header}} in the sequence editor. We therefore export the
gate's reasoning too, so a reply can be traced back to why the lead qualified.
"""

from __future__ import annotations

import csv
from pathlib import Path

from engine.gate import evaluate
from engine.model import Campaign

COLUMNS = [
    "email", "firstName", "lastName", "companyName", "website",
    "title", "country", "vertical", "nace", "employees", "city",
    "mailProvider", "gateScore", "gateNotes", "language", "cell",
]


def to_csv(campaign: Campaign, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for contact in campaign.contacts:
            firm = contact.firm
            verdict = evaluate(firm)
            writer.writerow({
                "email": contact.email,
                "firstName": contact.first_name,
                "lastName": contact.last_name,
                "companyName": firm.name,
                "website": firm.domain,
                "title": contact.title,
                "country": firm.country,
                "vertical": firm.vertical,
                "nace": firm.nace,
                "employees": firm.employees if firm.employees is not None else "",
                "city": firm.city,
                "mailProvider": firm.provider.value,
                "gateScore": verdict.score,
                "gateNotes": "; ".join(verdict.reasons),
                "language": contact.language,
                "cell": campaign.cell,
            })
    return out
