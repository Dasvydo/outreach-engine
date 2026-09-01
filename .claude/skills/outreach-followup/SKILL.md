---
name: outreach-followup
description: Write follow-up emails after a prospect replies, after a call or demo, after a proposal, or to re-engage someone who went quiet. Use once a lead has responded or a meeting has happened — anything after the cold sequence ends. Not for cold email; engine/sequence.py owns that.
---

# Follow-up sequences — DoviLoop

Adapted from `sales-followup` (MIT, Zubair Trabzada) — see `.claude/skills/ATTRIBUTION.md`.

## Where this sits in the pipeline

```
registry -> enrich -> gate -> sequence -> export        engine/  (cold, code-owned)
                                            |
                                          reply
                                            |
                                    THIS SKILL          (warm, judgement)
```

`engine/sequence.py` owns the cold sequence: three steps at day 0, 3 and 7,
copy held constant so the `capacity` vs `hours` A/B stays readable. **Do not
write cold email here and do not vary the cold copy** — that contaminates the
experiment the whole engine exists to run.

This skill starts the moment a human replies. From there personalisation costs
nothing: the A/B already recorded its outcome at reply rate.

## Before writing

Read `docs/ICP-BRIEF.md` for the offer and positioning. If it disagrees with
anything below, the brief wins.

Ask for whatever of this is missing — do not invent it:

- Who replied, at which firm, and what they actually said (paste it)
- What stage: replied / call held / demo held / proposal sent / gone quiet
- What was agreed, and any date they named
- Anything they objected to (route that to `outreach-objections` first)

## Hard rules

- **No fabricated proof.** No customer names, no logos, no "firms like yours see
  X%". There are no customers yet — the first ten design partners are being
  recruited now. Where the upstream skill reached for a case study, use the
  guarantee: the knowledge base gets built first, and if the drafts are not good
  enough to send after 30 days they do not pay and they keep it.
- **No hours-saved framing.** Capacity, not minutes. See `docs/ICP-BRIEF.md`.
- **Danish and Lithuanian are not native-checked.** Draft in English and mark
  `NEEDS NATIVE REVIEW` for a DK or LT recipient. Never emit the
  `NEEDS_NATIVE_PROOFREAD` sentinel into anything a person could send.
- **Never auto-send.** This skill writes drafts. A human sends them — which is
  also, not coincidentally, how the product works.
- **One CTA per email.** Under 120 words. Plain text. No bold, no emoji, no
  exclamation marks.

## Scenarios

### A. They replied but did not commit (2 emails)

The most common case, and the one the engine hands over most often.

| # | When | Job |
|---|---|---|
| 1 | same day | Answer their actual question in one paragraph. Propose two specific times. Nothing else. |
| 2 | +4 days | One new concrete detail they have not heard — usually that the knowledge base is built for them. Re-offer the same two times. |

### B. After the call (3 emails)

| # | When | Job |
|---|---|---|
| 1 | within 2 hours | Recap what *they* said the problem was, in their words. Confirm next step and owner. |
| 2 | +3 days | Deliver whatever was promised on the call. If nothing was, send one thing genuinely useful and make no ask. |
| 3 | +7 days | Direct: are we doing this? Name the design-partner place and that there are ten. |

### C. After the proposal (3 emails)

| # | When | Job |
|---|---|---|
| 1 | day 0 | Proposal attached. Offer to walk the partners through it. |
| 2 | +3 days | Answer the objection they did not raise out loud — usually build-vs-buy or data location. |
| 3 | +10 days | Ask directly whether it is a no. Make the no easy to give. |

### D. Gone quiet (2 emails, then stop)

| # | When | Job |
|---|---|---|
| 1 | +7 days from last contact | Assume the thread is buried, not refused. One line, no guilt, restate the ask. |
| 2 | +14 days | Close the loop. Say you will stop. Leave the door open for year-end. **Then actually stop.** |

Never send a third. A firm that ignored four emails is a firm the list should
re-approach in the next quarter, not one to be worn down.

### E. Not now, genuinely (nurture)

Set a date, one touch per quarter, tied to their calendar rather than yours:
before year-end close, after the filing deadline. No newsletter. No "just
checking in".

## Cadence rules

- Reply within **one hour** to anything positive. Nothing else in this file
  matters as much as this line.
- Follow the recipient's working day, not yours. DK and LT are CET/EET — a
  09:00 send from a US-shaped schedule lands at 03:00.
- Any reply, out-of-office included, **pauses the automated sequence**. Move the
  lead out of Instantly and handle it here.
- "Not interested" ends it. Ask once whether someone else at the firm should
  see it, then remove from all sequences.

## Output

```
LEAD:      <name, firm, cell — e.g. accounting-DK-capacity>
STAGE:     <replied | call | demo | proposal | quiet | nurture>
SCENARIO:  <A-E>
LANGUAGE:  <en | NEEDS NATIVE REVIEW (da) | NEEDS NATIVE REVIEW (lt)>

EMAIL 1 — send <when>
Subject: <4-7 words, lowercase acceptable>
<body>

EMAIL 2 — send <when>
Subject: Re: <thread>
<body>

STOP CONDITION: <what makes you stop sending>
```

If the reply contained an objection, handle it with `outreach-objections`
before writing the follow-up — the objection is the email, and a follow-up that
talks past it reads as not having been read.
