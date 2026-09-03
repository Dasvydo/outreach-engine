# BLOCKED.md — Batch C

Append-only. Every entry names what was missing, what it blocks, and what unblocks
it. Nothing here stopped the batch.

---

## B1 — No usable campaign database credential

**Missing:** any connection to the campaign ledger. `CAMPAIGN_DB_URL` is absent.
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set, but the URL resolves to
project `kngcxwcybozgqgnoweyt`, which is the product database that global rule 2
forbids this batch from touching.

**Blocks:** the spec's "rows written straight into `campaign.companies` via
`campaign_db.py`". No row was written to any database in this batch.

**Workaround shipped:** every ledger call goes through `engine/ledger.py`, which tries
`import campaign_db` and falls back to a logging shim that prints the exact call it
would have made. The dated CSVs in `lists/` are the real, complete output of this
run and can be imported later without re-running discovery.

**Unblocks it:** Dovy creates the campaign ledger project (Batch B), runs Batch B's
migration himself, drops `campaign_db.py` on the path, sets `CAMPAIGN_DB_URL`. Then
`python3 -m engine.icp_finder --market dk --commit` writes for real.

---

## B2 — `icp_finder.py` is not in this container

**Missing:** the file itself. `find / -name "icp_finder*"` returned nothing.

**Blocks:** the spec's instruction to extend the existing Google Custom Search ->
MX -> CSV pipeline rather than write a new one.

**Workaround shipped:** the MX-based Microsoft 365 gate the spec cares about already
exists locally in `engine/enrich.py` and `engine/gate.py`, and those were extended,
not rewritten. The missing discovery half was written as `engine/icp_finder.py`,
against the exact `leads_*.csv` column contract recovered from the two real output
files in Google Drive, so the old and new files are interchangeable.

**Unblocks it:** if the original turns up, diff `engine/icp_finder.py::search()`
against it. Only the search-call layer should differ.

---

## B3 — No Google Custom Search API key

**Missing:** `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`. Both absent.

**Blocks:** live discovery. The target of 100+ companies per market cannot be hit in
this session. No live search call was made.

**Workaround shipped:** `engine/icp_finder.py` runs against
`fixtures/serp/{dk,lt,global}.json`, which are recorded-shape search payloads, and
produces valid gated rows for all three markets. The fixture path and the live path
are the same code after the fetch, so the key is the only difference.

**Unblocks it:** Dovy adds both keys to `.env` and drops `--fixtures`. About 5
minutes, plus API quota.

---

## B4 — `linkedin-automator` CLI is not in this container

**Missing:** the tool, and therefore its queue file format.
`find / -iname "*linkedin*automator*"` returned nothing.

**Blocks:** the spec's requirement that `build_linkedin_queue.py` write "exactly the
format the existing automator expects". That claim cannot be made honestly.

**Workaround shipped:** `build_linkedin_queue.py` writes JSONL plus a matching CSV,
with every field name declared once in `QUEUE_FIELDS` so remapping is a single edit.
The 20 connects per day cap is enforced either way, since that number is not in doubt.

**Unblocks it:** Dovy opens the automator, reads one queue file it accepts, and
edits `QUEUE_FIELDS`. About 5 minutes. This is the only deliverable in the batch that
cannot be called verified.

---

## B5 — The DSD six-value taxonomy is not recoverable here

**Missing:** the DSD discovery pipeline and its six-value vocabulary. Not in this
repo, not on disk. `C-outreach-engine.md` names the taxonomy twice and never
enumerates it, and this session was restricted to two spec files, so it could not be
read from a sibling spec either.

**Blocks:** `sync_replies.py` classifying replies into the *same* vocabulary the rest
of DoviLoop uses. It classifies into a vocabulary, just possibly not that one.

**Workaround shipped:** six values defined in `config/reply_taxonomy.yaml` and marked
as reconstructed: `interested`, `not_now`, `not_a_fit`, `referred`, `objection`,
`unsubscribe`. The classifier reads the YAML, so correcting the list needs no Python
change.

**Unblocks it:** Dovy pastes the real six values into that YAML. About 2 minutes.

---

## B6 — No Instantly API key, nothing sent

**Missing:** `INSTANTLY_API_KEY`. Absent, by design of the batch.

**Blocks:** the real run of `load_instantly.py` and `sync_replies.py`. **The real run
is logged here as blocked and was not attempted.** Both were run in `--dry-run` and
the printed payloads are pasted into `RUN-REPORT.md`.

**Also blocked by calendar, not just by key:** Instantly needs its own sending
domains and 2 to 3 weeks of mailbox warmup, so email cannot start before roughly
22 September regardless of when the key appears. LinkedIn and phone are unaffected
and start 8 September.

**Unblocks it:** Dovy buys the Instantly seat and 2 to 3 sending domains, starts
warmup, sets `INSTANTLY_API_KEY` and `INSTANTLY_CAMPAIGN_ID`.

---

## B7 — No Anthropic key for reply classification

**Missing:** `ANTHROPIC_API_KEY`.

**Blocks:** the model-backed classifier path in `sync_replies.py`.

**Workaround shipped:** `sync_replies.py` ships a deterministic keyword classifier
that needs no key and no network, and it is what the tests exercise. The model path
is written behind `--classifier=model` and is not reachable without the key.

**Unblocks it:** set the key, pass `--classifier=model`. The keyword classifier is
good enough to ship week 1 and can stay as the fallback.

---

## B8 — Two documents disagree about the price

**Missing:** a decision, not a file.

`docs/ICP-BRIEF.md`, marked "Locked 2026-08-31", says $49/seat design partner,
$99/seat standard, $750 onboarding, 30-day build-first guarantee.
`00-START-HERE.md` says $89/seat/month + $500 setup, 10+ seats, free 2-week pilot
charging on day 14.

**Blocks:** nothing in this batch. All Batch C copy uses the `00-START-HERE.md`
numbers, since it is the campaign authority and is dated later.

**Not fixed here on purpose:** `docs/ICP-BRIEF.md` is shared with `reel-engine` and
`ad-engine`. Rewriting a locked shared brief from inside one batch would silently
change two other repos' source of truth. Left untouched.

**Unblocks it:** Dovy reconciles the two, in the canonical brief, once. About 5
minutes, and it should happen before any of the three repos ships copy.

---

## B9 — No testimonials and no named pilots

**Missing:** social proof. Confirmed absent by `00-START-HERE.md`, which says do not
invent either.

**Blocks:** the proof slot in every sequence's step 3.

**Workaround shipped:** the ROI figures are used instead, roughly 9x ROI and payback
in about 40 days. Those are corroborated in two independent places: the campaign
brief, and the real August outreach drafts in the Drive "DoviLoop Ops" folder. No
firm is named anywhere in the copy.

**Unblocks it:** the first pilot that agrees to be named.

---

## B10 — Danish and Lithuanian copy is not native-checked

**Missing:** a native speaker.

**Blocks:** sending anything in Danish or Lithuanian.

**Workaround shipped:** every DA and LT file is headed `NEEDS NATIVE CHECK`, and the
repo's existing `NEEDS_NATIVE_PROOFREAD` refusal in `engine/sequence.py` is untouched
and still refuses to render unproofread JSON copy.

**Unblocks it:** Dovy reads them, then a native speaker checks them. This is on the
"when you land" list in `00-START-HERE.md`.

---

## B11 — LT company discovery has no open registry

**Missing:** an open Lithuanian company API. This is pre-existing and documented in
`engine/registry.py::lt_sources()`, which deliberately does not stub it.

**Blocks:** hitting 100+ verified LT companies at the same confidence as DK.

**Workaround shipped:** the LT market list is built from web search plus the MX gate,
same as `global`, rather than from a registry. `config/queries/lt.yaml` carries the
queries. The honest LT ceiling is noted in the README: insurance in LT is a closed
licensed register of 105 firms, which is the entire market, not a sample.

**Unblocks it:** manual enumeration from rekvizitai.vz.lt, or a paid data source.
Not a code problem.

---

## B12 — The ledger column lists were not in the spec

**Missing:** the column lists for `campaign.companies`, `campaign.contacts` and
`campaign.touches`. The batch instructions said they are in the Batch C spec.
They are not. `C-outreach-engine.md` names all three tables and never enumerates
a column, and this session was restricted to `00-START-HERE.md` and
`C-outreach-engine.md`, so `B-ledger.md` could not be read either.

**Blocks:** writing rows whose column names are certain to match Batch B's schema.

**Workaround shipped:** the three lists are defined once, in
`engine/ledger.py` as `COMPANY_COLUMNS`, `CONTACT_COLUMNS` and `TOUCH_COLUMNS`,
derived from what the specs do state: the shared qualifier payload contract and
its exact enum values (`market`, `locale`, `team_size`, `email_client`, `role`),
the two column names the Batch C spec gives outright for `campaign.touches`
(`replied_at`, `reply_sentiment`), and the gates this repo already encodes.

**Unblocks it:** Dovy diffs those three tuples against Batch B's migration and
fixes any name that differs. One file, about 5 minutes. Nothing downstream reads
column names directly.

---

## B13 — Under the 100+ companies per market target

**Missing:** live search. Consequence of B3, recorded separately because it is a
number in the QA gate.

**Where the run landed:** dk 17, lt 7, global 17. Forty one companies, not three
hundred. Every one is a real domain that passed a real live Microsoft 365 MX
lookup, and every one had its own public site read for the size and dev-team
signals, so the rows are real. There are just not enough of them.

**Why lt is thinnest:** no open Lithuanian registry (B11), and four of the twelve
LT candidates were rejected by the MX gate, one of them Google Workspace.

**Unblocks it:** the search key. The finder already loops queries, pages and
country hints, so volume is a quota question, not a code one.
