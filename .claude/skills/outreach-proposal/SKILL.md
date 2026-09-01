---
name: outreach-proposal
description: Write a design-partner or standard proposal for a firm that has had the call and wants terms in writing. Use after a positive call when a prospect asks for a proposal, pricing in writing, or something to show their partners.
---

# Proposal — DoviLoop

Adapted from `sales-proposal` (MIT, Zubair Trabzada) — see `.claude/skills/ATTRIBUTION.md`.

Two sections of the upstream skill are **deliberately absent**: the ROI
projection and the case studies. Both are explained below. Do not reinstate
them from the source.

## Before writing

Read `docs/ICP-BRIEF.md` — it holds the offer and is updated more often than
this file. **If the two disagree, the brief wins**; say so and use the brief.

Then gather. Ask for anything missing rather than inventing it:

- Firm name, legal form, seat count (from the Lead JSON — do not re-ask)
- What *they* said the problem was, in their words, from the call
- Which partners will read this
- Design partner or standard
- Anything promised on the call

If you have no notes from the call, say so and stop. A proposal written from the
registry record alone is a brochure, and it reads like one.

## The offer

**Design partner — first ten firms only**

| | |
|---|---|
| Price | **$49 per seat per month**, locked 12 months |
| Onboarding | Waived |
| In exchange | Logo, case study, testimonial, monthly feedback call |

**Standard**

| | |
|---|---|
| Price | $99 per seat per month, minimum 10 seats |
| Onboarding | $750, waived on an annual commitment |

**Delivered either way:** we build the knowledge base — fees, deadlines,
document checklists, engagement and policy terms · a voice profile per person ·
a 90-minute kickoff workshop · a monthly tune-up · **new hires free forever**.

**The guarantee:** we build the knowledge base first. If the drafts are not good
enough to send after 30 days, they do not pay — and they keep the knowledge base.

The design-partner rate is flagged in the brief as a proposal, not a founder-stated
decision. **Confirm it with the user before putting $49 in a document that goes
to a real firm.**

## Structure

Eight sections. Under six pages. A 15-person partnership will not read twelve.

### 1. Cover
Firm name, date, who it is from, one-line summary. Nothing else.

### 2. What you told us
Their situation **in their own words from the call**. Quote them. This section
is the reason the proposal gets read, and it is the one that cannot be written
without call notes.

### 3. What we do about it
The mechanism, tied to what section 2 just said. Lead with the three things:

- It never leaves Outlook — drafts wait in the Outlook the team already uses
- It never auto-sends — a person reads every draft before it goes
- It runs in Europe

### 4. What we build for you
The knowledge base, itemised for *their* firm: their fee schedule, their
deadlines, their document checklists, their engagement terms. Then the voice
profile per person.

Name the differentiator plainly: most tools hand you an upload box and wish you
luck, which is why most firms never finish. We build it.

### 5. How it goes
90-minute kickoff → knowledge base built → 30-day evaluation → monthly tune-up.
Give week numbers, not dates, unless a start date was agreed.

### 6. What it costs
The table above, for their actual seat count. State the total plainly. If design
partner, state that there are ten places and what the exchange is — it is a
two-way agreement, not a discount, and framing it as a discount devalues both
sides.

### 7. The guarantee
Its own section, in full. **This is where a case study would go in a normal
proposal.** DoviLoop has no customers yet — the first ten design partners are
being recruited now — so the guarantee carries the risk instead of a reference
carrying it. That is a stronger position than a borrowed logo, and it is honest.

### 8. Next step
One action, one owner, one date.

## Not in this proposal, and why

**No ROI projection, no hours-saved arithmetic, no payback-period table.**
`docs/ICP-BRIEF.md` records a prospect rejecting that lever directly: *"what do
I make per hour? That's not the issue."* The upstream skill devoted a full
section to ROI math. It is removed. Argue **capacity** — the same partners take
on more clients without adding headcount — and for audit work, **consistency**:
a junior answers like a senior.

**No case studies, no customer names, no logos, no "firms like yours report".**
There are none yet. Inventing one is unrecoverable the moment it is checked, and
in a market of a few hundred firms it will be checked. Section 7 exists so that
this section does not need to.

**No feature that does not exist.** If the call created an expectation the
product cannot meet, raise it with the user rather than writing around it.

## Language

Draft in English. Danish and Lithuanian copy in this repo is **drafted but not
native-checked**. A proposal is a higher-stakes document than a cold email — it
gets forwarded to partners and sometimes to advisers.

If the firm is DK or LT, mark the output `NEEDS NATIVE REVIEW` and tell the user
plainly that it should not be sent until a native speaker has read it. Never
emit the `NEEDS_NATIVE_PROOFREAD` sentinel into a document.

## Output

Write `PROPOSAL-<firm>.md`, then print:

```
FIRM        <name> · <seats> seats · <design partner | standard>
VALUE       <seats> x $<rate>/mo = $<total>/mo
LANGUAGE    <en | NEEDS NATIVE REVIEW (da/lt)>
FROM CALL   <yes — notes used | NO — this is a brochure, get notes first>
UNCONFIRMED <anything you had to assume, listed>
```

The `UNCONFIRMED` line is the important one. Everything on it is something the
user must check before this reaches a real firm.
