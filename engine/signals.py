"""Soft signals read off a company's own public website.

Two of them, and both are deliberately soft:

**Dev team.** The strongest disqualifier in the brief is G6, an in-house
development team, because those firms will decide they can build it themselves.
There is no reliable public field for that, so this scores three cheap proxies
from the spec: engineering roles on a careers page, a GitHub organisation linked
from the domain, and an /engineering or /developers path. A score, never a hard
block. `engine/gate.py` still hard-fails G6 when `has_dev_team` is known to be
True from a human, and this module never sets that flag to True on its own.

**Size.** A headcount pulled from a team page or an "X employees" line. Also
soft. Unknown stays unknown, and unknown is not zero.

Company-level public data only. No LinkedIn scraping. That stays in the DSD
pipeline where it already lives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Paths that say "we employ developers" loudly enough to matter.
DEV_PATHS = ("/engineering", "/developers", "/developer", "/docs/api", "/api-docs", "/tech")

# Job-title fragments on a careers page. Lowercased substring match.
DEV_ROLE_WORDS = (
    "software engineer", "software developer", "backend", "back-end",
    "frontend", "front-end", "full stack", "fullstack", "devops",
    "data engineer", "platform engineer", "udvikler", "softwareudvikler",
    "programuotojas", "programuotoja", "sistemu inzinierius",
)

GITHUB_ORG = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/?(?:\"|'|\s|$)")

# "42 employees", "42 ansatte", "42 medarbejdere", "42 darbuotojai", "team of 42"
SIZE_PATTERNS = (
    ("en headcount", re.compile(r"\b(\d{1,4})\s*(?:\+)?\s*(?:employees|people|staff|specialists)\b", re.I)),
    ("en team of N", re.compile(r"\bteam of\s*(\d{1,4})\b", re.I)),
    ("da headcount", re.compile(r"\b(\d{1,4})\s*(?:\+)?\s*(?:ansatte|medarbejdere|specialister)\b", re.I)),
    ("lt headcount", re.compile(r"\b(\d{1,4})\s*(?:\+)?\s*(?:darbuotoj\w*|specialist\w*)\b", re.I)),
)

# The qualifier payload contract fixes these four bands. Nothing else is valid.
BANDS = ("1-9", "10-24", "25-49", "50+")


@dataclass
class SiteProfile:
    """What we know about one company site without logging in to anything.

    `paths` are URL paths seen for this domain in search results or a probe.
    `text` is concatenated public page text: search snippets, a careers page, an
    about page. `links` is raw HTML or text that may contain outbound links.
    """
    domain: str
    paths: tuple[str, ...] = ()
    text: str = ""
    links: str = ""
    stated_employees: int | None = None
    team_page_names: int | None = None
    notes: list[str] = field(default_factory=list)


def dev_team_signal(profile: SiteProfile) -> tuple[float, tuple[str, ...]]:
    """0.0 means nothing suggests developers, 1.0 means several things do.

    Never returns a boolean, because the spec says score it and never hard-block
    on it, and because every one of these proxies has a false positive: a firm
    can link a GitHub account it opened once and abandoned.
    """
    score = 0.0
    reasons: list[str] = []

    lowered_paths = tuple(p.lower() for p in profile.paths)
    hit_paths = [p for p in lowered_paths if any(p.startswith(d) for d in DEV_PATHS)]
    if hit_paths:
        score += 0.4
        reasons.append(f"dev path on site: {', '.join(sorted(set(hit_paths))[:3])}")

    lowered_text = profile.text.lower()
    hit_roles = sorted({w for w in DEV_ROLE_WORDS if w in lowered_text})
    if hit_roles:
        score += 0.4
        reasons.append(f"engineering role wording: {', '.join(hit_roles[:3])}")

    org = GITHUB_ORG.search(profile.links or "")
    if org:
        score += 0.3
        reasons.append(f"github organisation linked: {org.group(1)}")

    return (round(min(score, 1.0), 2), tuple(reasons))


def size_estimate(profile: SiteProfile) -> tuple[int | None, str]:
    """Best public guess at headcount, and the reason for it.

    Order matters. A number the firm states about itself beats a count of faces
    on a team page, which beats nothing. Nothing stays None, never 0.
    """
    if profile.stated_employees:
        return profile.stated_employees, "stated on site"

    for label, pattern in SIZE_PATTERNS:
        m = pattern.search(profile.text or "")
        if m:
            try:
                return int(m.group(1)), f"{label} on the site"
            except ValueError:
                pass

    if profile.team_page_names:
        return profile.team_page_names, "counted names on the team page"

    return None, "unknown"


def to_band(employees: int | None) -> str | None:
    """Map a headcount onto the qualifier contract's four bands."""
    if employees is None:
        return None
    if employees < 10:
        return "1-9"
    if employees < 25:
        return "10-24"
    if employees < 50:
        return "25-49"
    return "50+"
