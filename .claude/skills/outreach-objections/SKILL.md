---
name: outreach-objections
description: Handle an objection from a prospect reply, or build the objection playbook for a segment. Use when a lead replies with a concern ("we could build this ourselves", "too expensive", "not now", "where is our data"), when preparing for a call, or when the user asks for objection handling for DoviLoop outreach. Grounded in the locked ICP and offer.
---

# Objection handling — DoviLoop

Adapted from `sales-objections` (MIT, Zubair Trabzada) — see `.claude/skills/ATTRIBUTION.md`.

## When this runs

Two modes:

1. **One objection** — a prospect replied with a concern. Produce a response now.
2. **Playbook** — build `OBJECTION-PLAYBOOK.md` for a segment before a campaign.

## Before you answer anything

Read `docs/ICP-BRIEF.md`. It is the source of truth for the offer, the pricing
and the positioning, and it is updated more often than this file. If this skill
and the brief disagree, **the brief wins** — say so and use the brief.

## The framework: LAER

| Step | Action |
|---|---|
| **Listen** | Read what they actually wrote. Do not pattern-match to the nearest template objection. |
| **Acknowledge** | Validate the concern in one sentence. Never argue, never "actually". |
| **Explore** | One clarifying question. The stated objection is often not the real one. |
| **Respond** | Address it, then redirect to a single low-friction next step. |

LAER rather than Feel-Felt-Found deliberately: Feel-Felt-Found is an English
idiom that does not survive translation into Danish or Lithuanian. LAER is a
procedure, so it does.

## Hard rules

- **Never invent a customer, a logo, a case study, or a metric.** DoviLoop is
  recruiting its first ten design partners. There are no customers yet. If a
  response needs social proof, use the guarantee instead — that is what it is
  for. A fabricated reference is unrecoverable when it is checked.
- **Never argue hours-saved or ROI arithmetic.** `docs/ICP-BRIEF.md` records a
  prospect rejecting that lever on tape: *"what do I make per hour? That's not
  the issue."* The upstream skill had five ROI tactics; they are removed here.
  Argue **capacity** — more clients without more headcount.
- **Never draft Danish or Lithuanian copy and present it as ready to send.**
  Both languages are drafted but not native-checked (`copy/*.json` carries
  `NEEDS_NATIVE_PROOFREAD`). Write the response in English and label it
  `NEEDS NATIVE REVIEW` if it is destined for a DK or LT prospect.
- **Never promise a feature.** If the objection needs a capability that does not
  exist, say the objection is unanswerable today and hand it back to the user.

## The five objections this ICP actually raises

Ordered by expected frequency for accounting and bookkeeping firms in DK/LT.
Everything else is secondary; start here.

### 1. "We could build this ourselves." — the defining objection

`docs/ICP-BRIEF.md` G6 names this directly: *they'll think they can build it.*
Note the asymmetry — a firm with an actual in-house dev team is a **hard gate
failure** and should never have received the email. So when this comes from a
gated lead, it is almost always a partner who has seen a demo of an LLM, not an
engineering assessment.

- **Acknowledge:** "You probably could — the drafting part is not the hard part any more."
- **Explore:** "When you picture it working, who maintains the answers when your fee schedule changes in January?"
- **Respond:** The product is not the model. It is the knowledge base — fees,
  deadlines, document checklists, engagement and policy terms — plus a voice
  profile per person, and someone keeping both current. Firms that build this
  themselves get a working demo in a fortnight and an unmaintained one by spring.
  We build the knowledge base *for* them; most tools hand you an upload box and
  wish you luck, which is why most firms never finish.
- **Redirect:** "We build it first and you only pay if the drafts are good enough after 30 days. If you'd still rather build, you'd at least have the knowledge base."

### 2. "Where does our client data go?" / data sovereignty

**This is a reason to buy, not a hurdle.** The brief calls European data
sovereignty the biggest current driver in European buying. Do not get defensive.

- **Acknowledge:** "Right question to ask first, given what's in your inboxes."
- **Explore:** "Is the constraint your own policy, or something a client has written into an engagement letter?"
- **Respond:** It runs in Europe. It runs inside the Outlook they already use —
  the mail does not move to a new system. And it never sends anything on its
  own: every draft waits for a person to read it.
- **Redirect:** "Happy to put that in writing before we go further — would that be useful for your partners?"

### 3. "Too expensive" / "we don't have budget"

- **Acknowledge:** "Fair — and worth being precise about what it costs."
- **Explore:** "Is it the number, or that you can't yet see what it returns?"
- **Respond:** Design partner rate is $49/seat/month locked for twelve months
  (standard is $99, minimum ten seats), onboarding waived. Ten places only, in
  exchange for a logo, a case study, a testimonial and a monthly feedback call.
  **Do not run ROI math.** The point is capacity: the same partners take on more
  clients without hiring.
- **Redirect:** "There are ten design-partner places. Want me to hold one while you decide?"

### 4. "Not right now" / "come back after year-end"

The seasonal hook makes this the weakest objection in the set — but do not be
clever about it, because they are genuinely busy.

- **Acknowledge:** "Understood — and year-end is exactly why I'm early."
- **Explore:** "When does the inbox actually start climbing for you?"
- **Respond:** The inbox triples at year-end and nobody can hire for an
  eight-week peak. The knowledge base has to be built *before* the surge to be
  any use during it. Building it in the quiet weeks is the whole point.
- **Redirect:** "Shall I come back in [month], or would 15 minutes now mean you're ready for it?"

### 5. "I need to discuss with my partners."

- **Acknowledge:** "Of course — this is a partnership decision."
- **Explore:** "Who else weighs in, and what will their first objection be?"
- **Respond:** Offer a one-pager written for the other partners, or a short call
  with them present. Name the three things partners ask about first: it stays
  in Outlook, it never auto-sends, it runs in Europe.
- **Redirect:** "Would 20 minutes with you and [partner] together be easier than me writing it up?"

## Secondary objections

Handle with the same LAER shape; do not pre-write these unless asked.

| Objection | The turn |
|---|---|
| "We tried an AI tool and it was useless" | Ask which one and what failed. Almost always: nobody built the knowledge base, so it wrote generic prose. That is the thing we do differently. |
| "Our clients would hate AI replies" | It drafts in *their* wording from a voice profile, and never sends. The client sees an email their accountant read and approved. |
| "We're too small" | If genuinely under 10 seats they failed G4 and are out of scope — say so plainly and leave the door open rather than stretching to fit. |
| "Send me some information" | Usually a soft no. Ask one qualifying question instead of sending a deck. |
| "Just not interested" | Accept it. Ask if someone else at the firm should see it. Remove from sequence. Do not attempt a third turn. |

## Reply-mode output

Keep it short — this is an email reply, not a document.

```
OBJECTION:  <what they actually said, verbatim>
UNDERNEATH: <your read of the real concern, or "as stated">
CATEGORY:   build-vs-buy | sovereignty | price | timing | authority | trust | out-of-scope

DRAFT REPLY
<under 120 words, one CTA, plain text, no exclamation marks, no bold>

WATCH FOR: <what a bad answer to your Explore question would mean>
LANGUAGE:  <en | NEEDS NATIVE REVIEW (da) | NEEDS NATIVE REVIEW (lt)>
```

If the reply reveals a **hard gate failure** — an in-house dev team (G6), under
ten seats (G4) — say so explicitly and recommend disqualifying rather than
handling. The gate exists so that time is not spent here.

## Playbook-mode output

Write `OBJECTION-PLAYBOOK.md`: the five primary objections in full LAER,
secondary objections as a table, and a prevention section listing what should be
said in the sequence itself to stop each objection arising. Note which of the
three currently-unstated true things — never leaves Outlook, never auto-sends,
runs in Europe — would have pre-empted each objection, since `docs/ICP-BRIEF.md`
flags that none of them are in the copy today.
