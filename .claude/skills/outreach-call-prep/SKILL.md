---
name: outreach-call-prep
description: Prepare a brief for a booked call with a prospect firm — what to say, what to ask, what to expect. Use when a lead has agreed to a call or demo and it needs preparing. Builds from the Lead JSON and the locked ICP rather than scraping the firm's website.
---

# Call prep — DoviLoop

Adapted from `sales-prep` (MIT, Zubair Trabzada) — see `.claude/skills/ATTRIBUTION.md`.

## Where the facts come from

**From the Lead JSON** (`segments/*.json`) — registry-sourced and trustworthy:
firm name, CVR/registry id, NACE code, employee band, city, mail provider,
gate score and the gate's own reasoning.

**From the thread** — what they wrote, what they objected to, who else was
copied.

**From the user** — attendee names and roles, and what was agreed.

The upstream skill fetched nine hardcoded English page paths (`/about`,
`/team`, `/leadership`…). Danish firms use `/om-os`, `/medarbejdere`,
`/kontakt`, so that step returned nothing useful and is dropped. If you do open
the firm's website, read it as a human would and cite what you actually saw —
**never present an inference as a fact about their firm.** Getting a detail
wrong about a 15-person partnership is worse than not knowing it.

Read `docs/ICP-BRIEF.md` for the offer. If it disagrees with this file, it wins.

## The call is 15 minutes

The cold copy asks for fifteen minutes. Honour that — a prep brief that assumes
a 45-minute discovery call sets up a broken promise in the first sentence.

| Minutes | Purpose |
|---|---|
| 0-2 | Why you wrote. One sentence. Then stop talking. |
| 2-9 | **Discovery.** Their inbox, not your product. |
| 9-13 | What it does, framed to what they just said. |
| 13-15 | Next step, single and specific. |

If it runs long because they are engaged, that is their choice to make, not
yours to assume.

## The one thing this call must establish: G3

`docs/ICP-BRIEF.md` gate G3 — **recurring questions have stable, documentable
answers.** This is the qualifier that decides whether they can be a customer at
all, and it is the only gate that cannot be checked from a registry.

The test: are their most-repeated client questions **lookups or judgement
calls?**

- *"When is my VAT due?"* / *"What documents do you need for the annual
  accounts?"* / *"What does an audit cost?"* — lookups. The knowledge base
  answers these. **Qualified.**
- *"Should I incorporate?"* / *"Is this deductible in my situation?"* — judgement.
  A drafted answer is a liability, not a help. **Not qualified**, however
  friendly the call is.

Every firm has both. The question is the mix, and you find it by asking for
examples rather than asking the question directly.

## Discovery questions

Ask five or six, not ten. Listen to the answers.

**Establishing G3 (ask these first):**
1. "What are the three questions your team answers most often in a week?"
2. "If I asked two of your people the same one, would I get the same answer?"
3. "Where does the correct answer live today — a document, or someone's head?"

**Establishing the shape of the problem:**
4. "How many people at the firm write to clients on a normal day?" (confirms G4)
5. "What happens to the inbox in the four weeks before a deadline?" (the seasonal hook)
6. "When someone new starts, how long before they can answer a client without checking?"

**Establishing the buying process:**
7. "If this were obviously useful, who else would need to say yes?"

**Never ask:** anything the registry already answered — headcount, city, what
they do. Asking a firm what it does when the CVR record is in front of you reads
as not having prepared.

## What to expect them to raise

Prep the top two from `outreach-objections`, and no more — a brief listing
fifteen objections gets read as none.

For an accounting firm on Microsoft 365, expect in this order:
1. **"We could build this ourselves"** — the ICP brief names it explicitly.
2. **"Where does client data go"** — and remember this one is a reason to buy.

## What to say when it is your turn

Three things, in this order, all currently absent from the cold copy:

1. **It never leaves Outlook.** Buyer-stated: *"a lot of apps do similar things,
   but then you have to move away… we just do a little prep work for you."*
2. **It never auto-sends.** Buyer-stated: *"I like that it doesn't auto-send,
   because that would be a big no-no for me."*
3. **It runs in Europe.**

Then the delivery: the knowledge base is built for them, a voice profile per
person, a 90-minute kickoff, a monthly tune-up, new hires free forever.

**Do not run ROI arithmetic.** A prospect rejected it outright — *"what do I
make per hour? That's not the issue."* Argue capacity: more clients without
more headcount.

## Next step to propose

One. Not a menu.

- Strong call → the design-partner place. $49/seat locked twelve months,
  onboarding waived, ten places, in exchange for a logo, case study,
  testimonial and a monthly feedback call.
- Warm but hesitant → the 90-minute kickoff workshop as the next commitment.
- Unclear on G3 → ask them to send their five most-repeated client questions.
  That both qualifies them and starts the knowledge base.

## Output

Write `CALL-PREP-<firm>.md`. One page. If it does not fit on one page it will
not be read before the call.

```
FIRM        <name> · <city> · <employees> employees · CVR <id>
CELL        <vertical-country-variant>       GATE  <score> — <notes>
PROVIDER    <microsoft|google|other>          <if google: consent screen + 100-user cap>
ATTENDEES   <names, roles>
THREAD      <what they said, verbatim>

OPEN (1 sentence)
DISCOVERY (5-6 questions, G3 first)
G3 VERDICT — what answer would disqualify them
EXPECT (top 2 objections + the turn)
SAY (three true things + delivery)
ASK (one next step)
DO NOT (registry facts, ROI math, hours-saved, any invented customer)
```

**Flag rather than fill:** if the gate score carries `G6: dev-team status not
assessed` or `G4: employee count unknown`, put that on the brief. An unassessed
hard gate is a question for the call, not a detail to gloss.
