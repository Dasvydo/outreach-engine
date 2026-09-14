"""The seven qualification gates, as predicates over a Firm.

Encoded from docs/ICP-BRIEF.md. A gate returns (passed, reason) so a rejection
is always explainable - a silently dropped lead is a lead you cannot audit.

G1 AND THE TWO TIMES IT CHANGED
-------------------------------
On 2026-08-31 G1 was deliberately made SOFT. The reasoning was recorded and is
worth keeping: Gmail is workable once the OAuth consent screen leaves Testing
status, costing an unverified-app screen and a 100-user lifetime cap, so it
downranked rather than disqualified.

On 2026-09-14 Dovy set the campaign's targeting to Microsoft 365 only. That is a
change of strategy rather than a correction of the earlier reasoning - the
2026-08-31 note is still true about what Gmail costs; the campaign has simply
decided not to pay it for now. So G1 is hard again, but behind the
`OUTLOOK_ONLY` switch below rather than by deleting the old behaviour, because a
decision that flipped twice will plausibly flip again.

NOTHING IS SILENTLY DROPPED
---------------------------
A hard provider gate turns every misclassification into a deleted prospect, so
the verdict now has three outcomes rather than two:

    passed=True                  -> eligible to be contacted
    passed=False, review=True    -> parked, NOT rejected: the provider could not
                                    be established and a human or a richer probe
                                    should decide
    passed=False, review=False   -> genuinely out of ICP

`review` exists mainly for GATEWAY. A firm behind Mimecast or Proofpoint may well
be Microsoft underneath - `engine/enrich.py` documents the measurements - and
throwing those away would quietly delete a slice of the best-fit market. UNKNOWN
is parked for the same reason: from a Firm alone there is no way to tell a
permanent NXDOMAIN from a resolver timeout, and only one of those is a real
rejection.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.enrich import Provider
from engine.model import Firm, VERTICALS

MIN_SEATS = 10
MAX_SEATS = 200  # G7: above this, data-sovereignty procurement review bites

# Campaign targeting, set 2026-09-14. True: only Microsoft 365 firms are
# eligible. False restores the 2026-08-31 soft behaviour, where a non-Microsoft
# provider downranks but still qualifies.
OUTLOOK_ONLY = True


@dataclass(frozen=True)
class Verdict:
    passed: bool
    score: float          # 0.0-1.0; ranks the survivors
    reasons: tuple[str, ...]
    review: bool = False  # parked rather than rejected; see the module docstring

    @property
    def rejected_for(self) -> str:
        return "; ".join(self.reasons) if not self.passed else ""

    @property
    def parked_for(self) -> str:
        return "; ".join(self.reasons) if self.review else ""


def evaluate(firm: Firm) -> Verdict:
    hard: list[str] = []
    soft: list[str] = []
    park: list[str] = []
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

    # G1 - mail provider. Hard since 2026-09-14 when OUTLOOK_ONLY is set; see the
    # module docstring for why the soft path is kept rather than deleted.
    if OUTLOOK_ONLY:
        if firm.provider is Provider.GATEWAY:
            park.append("G1: a security gateway fronts this domain - the platform "
                        "behind it is unresolved and may well be Microsoft")
            score -= 0.15
        elif firm.provider is Provider.UNKNOWN:
            park.append("G1: mail provider unresolved - retry before rejecting")
            score -= 0.15
        elif firm.provider is Provider.GOOGLE:
            hard.append("G1: Google Workspace - campaign targets Microsoft 365 only")
        elif firm.provider is not Provider.MICROSOFT:
            hard.append(f"G1: {firm.provider.value} - campaign targets Microsoft 365 only")
    else:
        if firm.provider is Provider.GOOGLE:
            soft.append("G1: Google Workspace - unverified-app screen + 100-user cap")
            score -= 0.35
        elif firm.provider is Provider.UNKNOWN:
            soft.append("G1: mail provider unresolved")
            score -= 0.15
        elif firm.provider is Provider.GATEWAY:
            soft.append("G1: a security gateway fronts this domain - platform unresolved")
            score -= 0.20
        elif firm.provider is Provider.OTHER:
            soft.append("G1: neither Microsoft nor Google - needs a manual look")
            score -= 0.20

    if not firm.domain:
        hard.append("no domain - cannot enrich or contact")

    # A hard failure is a rejection outright; parking only applies to a firm that
    # cleared every other gate and fell over solely on an unresolved provider.
    parked = bool(park) and not hard
    return Verdict(
        passed=not hard and not park,
        score=max(0.0, round(score, 3)),
        reasons=tuple(hard + park + soft),
        review=parked,
    )


def partition(firms: list[Firm]) -> tuple[list[Firm], list[tuple[Firm, Verdict]]]:
    """Split into (qualified, sorted best-first) and (not qualified, with reason).

    Kept for the existing callers. Parked firms appear in the second list, so a
    caller that only wants to know "may I contact this" still gets the right
    answer. Use `triage()` when the difference between parked and rejected
    matters - which it does anywhere a lead could be lost.
    """
    kept, parked, rejected = triage(firms)
    return kept, parked + rejected


def triage(firms: list[Firm]) -> tuple[
    list[Firm], list[tuple[Firm, Verdict]], list[tuple[Firm, Verdict]]
]:
    """Split into (qualified best-first, parked for review, rejected).

    The middle list is the one that matters under an Outlook-only gate: those
    firms are not rejects, they are unresolved, and they need a second look
    rather than a bin. See the module docstring.
    """
    kept: list[tuple[Firm, Verdict]] = []
    parked: list[tuple[Firm, Verdict]] = []
    rejected: list[tuple[Firm, Verdict]] = []
    for f in firms:
        v = evaluate(f)
        if v.passed:
            kept.append((f, v))
        elif v.review:
            parked.append((f, v))
        else:
            rejected.append((f, v))
    kept.sort(key=lambda pair: pair[1].score, reverse=True)
    return [f for f, _ in kept], parked, rejected
