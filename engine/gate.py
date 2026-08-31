"""The seven qualification gates, as predicates over a Firm.

Encoded from docs/ICP-BRIEF.md. A gate returns (passed, reason) so a rejection
is always explainable - a silently dropped lead is a lead you cannot audit.

G1 is deliberately NOT a hard failure. It was corrected on 2026-08-31: Gmail is
workable once the OAuth consent screen leaves Testing status. It costs an
unverified-app screen and a 100-user lifetime cap, so it downranks rather than
disqualifies.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.enrich import Provider
from engine.model import Firm, VERTICALS

MIN_SEATS = 10
MAX_SEATS = 200  # G7: above this, data-sovereignty procurement review bites


@dataclass(frozen=True)
class Verdict:
    passed: bool
    score: float          # 0.0-1.0; ranks the survivors
    reasons: tuple[str, ...]

    @property
    def rejected_for(self) -> str:
        return "; ".join(self.reasons) if not self.passed else ""


def evaluate(firm: Firm) -> Verdict:
    hard: list[str] = []
    soft: list[str] = []
    score = 1.0

    # G4 - seat count. Hard.
    if firm.employees is None:
        soft.append("G4: employee count unknown")
        score -= 0.25
    elif firm.employees < MIN_SEATS:
        hard.append(f"G4: {firm.employees} employees, need >= {MIN_SEATS}")
    elif firm.employees > MAX_SEATS:
        hard.append(f"G7: {firm.employees} employees, above the {MAX_SEATS} ceiling")

    # G6 - in-house developers. Hard when known.
    if firm.has_dev_team is True:
        hard.append("G6: has an in-house development team")
    elif firm.has_dev_team is None:
        soft.append("G6: dev-team status not assessed")
        score -= 0.10

    # Vertical must be one of the three locked.
    if firm.vertical not in VERTICALS:
        hard.append(f"off-ICP vertical: {firm.vertical!r}")

    # G1 - provider. Soft since 2026-08-31.
    if firm.provider is Provider.GOOGLE:
        soft.append("G1: Google Workspace - unverified-app screen + 100-user cap")
        score -= 0.35
    elif firm.provider is Provider.UNKNOWN:
        soft.append("G1: mail provider unresolved")
        score -= 0.15
    elif firm.provider is Provider.OTHER:
        soft.append("G1: neither Microsoft nor Google - needs a manual look")
        score -= 0.20

    if not firm.domain:
        hard.append("no domain - cannot enrich or contact")

    return Verdict(
        passed=not hard,
        score=max(0.0, round(score, 3)),
        reasons=tuple(hard + soft),
    )


def partition(firms: list[Firm]) -> tuple[list[Firm], list[tuple[Firm, Verdict]]]:
    """Split into (qualified, sorted best-first) and (rejected, with reason)."""
    kept: list[tuple[Firm, Verdict]] = []
    dropped: list[tuple[Firm, Verdict]] = []
    for f in firms:
        v = evaluate(f)
        (kept if v.passed else dropped).append((f, v))
    kept.sort(key=lambda pair: pair[1].score, reverse=True)
    return [f for f, _ in kept], dropped
