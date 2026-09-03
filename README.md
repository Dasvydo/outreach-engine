# outreach-engine

Cold outreach for DoviLoop, built from official registries rather than bought
lists. Firms go in, a gated and enriched Instantly campaign comes out.

Sibling to `reel-engine` and `ad-engine`; all three work from the same locked
brief in `docs/ICP-BRIEF.md`.

```
segments/<name>.json    who      firms + contacts, one file per list build
copy/<variant>.json     the words  sequence variants, one per A/B arm
engine/                 the code   registry -> enrich -> gate -> sequence -> export
queue/                  state      built campaigns (gitignored)
```

**The Lead JSON is the API boundary.** List building writes it, the gate filters
it, sequencing reads it, export consumes it. Everything upstream exists to
produce more of them.

---

## Quick start

```bash
pip install -r requirements.txt

python -m engine.cli counts                       # live DK registry counts
python -m engine.cli mx cbs.dk pwc.dk doviloop.dev # who runs their mail
python -m engine.cli gate segments/example-leads.json
python -m engine.cli build segments/example-leads.json --variant capacity --out queue/acc-dk.csv
```

## The four stages

**1. Registry.** `engine/registry.py` pulls live counts from Statistics Denmark's
open StatBank API (no key). Denmark is the strong side — CVR is filterable by
industry code, employee band and municipality. **Lithuania has no open
equivalent**, and the LT fetchers are deliberately unimplemented rather than
stubbed: a function returning plausible numbers is worse than an honest gap,
because the numbers get quoted. `lt_sources()` names the real routes.

**2. Enrich.** `engine/enrich.py` classifies each domain's mail provider from one
MX lookup. No key, no cost, one DNS query. **This is the highest-value enrichment
available for this ICP** — G1 prefers Microsoft, and Gmail carries a real cost
(unverified-app consent screen, 100-user lifetime cap), so the provider decides
both whether to contact a firm and which sequence it gets.

**3. Gate.** `engine/gate.py` encodes G1–G7 from the brief as predicates. Every
rejection carries a reason — a silently dropped lead is one you cannot audit.
G4 (under 10 seats) and G6 (in-house developers) are hard failures. **G1 is not**:
corrected 2026-08-31, Gmail downranks by 0.35 rather than disqualifying.

**4. Sequence and export.** `engine/sequence.py` renders a copy variant in the
firm's country language; `engine/export.py` writes an Instantly CSV carrying the
gate's own reasoning, so a reply traces back to why the lead qualified.

## The A/B that matters

Two copy variants exist, and they are the experiment:

| Variant | Framing | Status |
|---|---|---|
| `capacity` | Take on more clients without hiring | **Recommended, untested** |
| `hours` | Hours saved per person | **Control** — what the pricing page says today |

A prospect rejected the hours-saved lever directly — *"what do I make per hour?
That's not the issue."* But that is one anecdote, and replacing a live framing on
one anecdote would be its own mistake. Run both, settle it with reply rate.

## Language safety

Danish and Lithuanian bodies are **drafted, not native-checked**, and carry a
`NEEDS_NATIVE_PROOFREAD` sentinel. `render()` refuses to build them by default.
Pass `--allow-english-fallback` to send English instead — never ship the sentinel.

Getting a native speaker on the DA and LT copy is the single highest-leverage
task in this repo. The product ships in both languages; outreach that doesn't
match throws away the one advantage no US competitor can copy.

## Cells

Three verticals × two countries × two copy variants. Keep everything but the
variable constant per comparison.

**Read reply rate and qualified-conversation rate, never open rate.**

⚠️ **Insurance is not a cold-email cell.** ~75 firms in band across both
countries, and Lithuania's is a *closed licensed register of 105* — the entire
market, not a sample. Enumerate by hand, go LinkedIn and the broker associations,
and read the result qualitatively. Do not compare its reply rate against
accounting's.

## Deliverability

Not built yet, and it is real work. From an ex-sales-director's advice: a
separate domain per sending identity, no more than three mailboxes per domain,
warm before sending, verify every address twice (bounce rate under 1%), and
rotate a domain out the moment it degrades. Volume is not the constraint —
domain reputation is.

---

# Campaign layer: DoviLoop Teams, 8 September to 19 October 2026

Everything above this line is the original engine and still works unchanged. The
sections below are the campaign build (Batch C) that sits on top of it.

Read `AUDIT.md` for what was found before any of this was written, `BLOCKED.md`
for what was missing and what it blocks, and `RUN-REPORT.md` for what Dovy has
to do himself.

## Timing. Read this before planning anything

**Email cannot start before roughly 22 September 2026.** Instantly needs its own
sending domains and two to three weeks of mailbox warmup before a single message
is safe to send. Buying the domains on 8 September does not buy you 8 September.

**LinkedIn and phone start 8 September in all three markets.** Neither needs
warmup and neither is waiting on a purchase.

So the A/B reads like this:

| Weeks | Dates | What is running |
|---|---|---|
| 1 to 2 | 8 Sept to 21 Sept | LinkedIn across dk, lt and global. Phone in dk. Three markets, one channel, and that is the comparison. |
| 3 onward | 22 Sept to 19 Oct | Email joins, `global` only. Now it is three markets on LinkedIn plus one market on two channels. |

Two consequences that are easy to miss later:

1. **Weeks 1 and 2 are the clean market comparison.** One channel, three
   markets. Once email starts, `global` has two channels and its numbers stop
   being comparable to dk and lt on volume alone. Read per channel from week 3,
   using Batch B's `get_channel_funnel`.
2. **Denmark never gets email at all**, so dk versus global is never a
   like-for-like channel comparison. It is a market comparison run on the
   channels each market actually allows.

## Denmark does not get cold email

Danish marketing law is stricter than the rest of the EU on unsolicited
commercial email. Until Dovy confirms otherwise in writing, no Danish address
enters Instantly.

This is enforced in `load_instantly.py` as a filter that runs before the payload
is built, on four independent signals (market, country, a .dk email domain, a
+45 phone number), with no flag to switch it off. `tests/test_danish_exclusion.py`
fails the build if anyone weakens it. Denmark runs on LinkedIn and phone, and
`sequences/phone/da.md` is the script that replaces the email.

## What was added

```
config/queries/{dk,lt,global}.yaml   search queries, editable without code
config/hooks.yaml                    segment openers, 3 segments x 3 locales
config/reply_taxonomy.yaml           six reply values, reconstructed
engine/icp_finder.py                 search -> MX gate -> dedup -> dated CSV
engine/signals.py                    dev-team and size soft signals
engine/ledger.py                     the campaign_db.py seam
engine/contacts.py                   reading contacts back out
sequences/linkedin/{en,da,lt}.md     four steps, 20 connects a day
sequences/email/en.md                four touches, global only
sequences/phone/{da,en,lt}.md        opener plus the three brush offs
load_instantly.py                    global only, Danish addresses excluded
build_linkedin_queue.py              20 a day, shared across markets
sync_replies.py                      classify replies, write them back
lists/{market}-YYYY-MM-DD.csv        the dated market lists
fixtures/                            stand-ins for the absent API keys
```

## Campaign commands

```bash
pip install -r requirements.txt

# discovery, all three markets, reading each company's own public site
python3 -m engine.icp_finder --all --probe

# deterministic version, no site fetches, used by the tests
python3 -m engine.icp_finder --market dk --no-probe

# loaders. Both default to a dry run and send nothing.
python3 load_instantly.py --dry-run
python3 build_linkedin_queue.py --all --dry-run
python3 sync_replies.py --dry-run

python3 -m pytest -q
```

## The campaign offer, which is not the offer in docs/ICP-BRIEF.md

The campaign prices at **$89 per seat per month plus a $500 setup fee** covering
the workshop, onboarding and setup, for teams of 10 and up, with a free two week
pilot and billing starting on day 14.

`docs/ICP-BRIEF.md` still says $49 and $99 a seat with $750 onboarding. The two
disagree. The campaign brief is dated later and all campaign copy follows it.
The locked brief was deliberately left untouched because `reel-engine` and
`ad-engine` share it. See `BLOCKED.md` B8, and reconcile it once.
