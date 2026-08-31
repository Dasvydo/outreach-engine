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
