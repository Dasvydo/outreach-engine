# AUDIT.md — Batch C Phase 0

Ran 2026-09-03 in the unattended campaign container, on branch `campaign/c-outreach`,
before any other file in this repo was created or changed.

Every line below names the command that was run and what actually came back.
Three verdicts are used and kept distinct:

- **EXISTS AND RUNS** — present in this container, executed, produced correct output
- **EXISTS AND IS BROKEN** — present, executed, did not do its job
- **DOES NOT EXIST HERE** — not in this container at all. Not "probably fine", not
  "assumed elsewhere". Absent, and the absence is a finding.

---

## 1. The `outreach-engine` repo as it stands — EXISTS AND RUNS

```
$ git log --oneline
037c2af Initial commit: registry -> enrich -> gate -> sequence -> export
$ git branch
* campaign/c-outreach   claude/campaign-specs-setup-9uwkl9   main
```

One commit. Nothing half-merged, no stale branches of work in progress.

Tree at audit time:

```
README.md  requirements.txt  .gitignore
copy/capacity.json  copy/hours.json
docs/ICP-BRIEF.md
engine/{cli,enrich,export,gate,model,registry}.py
segments/example-leads.json
tests/test_gate.py
```

`requirements.txt` is one line, `dnspython>=2.6`. Neither dnspython nor pytest were
installed in the container image:

```
$ python3 -c "import dns.resolver"
ModuleNotFoundError: No module named 'dns'
$ python3 -m pytest --version
No module named pytest
$ pip install dnspython pyyaml pytest   # succeeded, network reachable
```

Not a repo defect, an environment one. Noted because anyone reproducing this needs
the install first.

### What actually runs today

| Command | Result |
|---|---|
| `python3 -m pytest -q` | **7 passed in 0.08s** |
| `python3 -m engine.cli counts` | live hit on Statistics Denmark StatBank, returned accounting 4,882 / administrative 1,793 / insurance 448 |
| `python3 -m engine.cli mx cbs.dk pwc.dk doviloop.dev microsoft.com` | `cbs.dk microsoft`, `pwc.dk unknown`, `doviloop.dev google`, `microsoft.com microsoft` |
| `python3 -m engine.cli gate segments/example-leads.json` | `qualified 1 / 3`, both drops carried a printed reason |
| `python3 -m engine.cli build ... --variant capacity` | exited with `REFUSED: variant 'capacity' step day 0 is not proofread in 'da'` |

That last one is the design working, not a failure. `engine/sequence.py` refuses to
render copy still carrying the `NEEDS_NATIVE_PROOFREAD` sentinel unless
`--allow-english-fallback` is passed. It is the single best piece of engineering in
the repo and this batch keeps the same posture.

### What exists and is scaffolded but deliberately unimplemented

`engine/registry.py::lt_sources()` returns source URLs instead of fetching. The
docstring says why: a stub returning plausible Lithuanian firm counts is worse than
an honest gap because the numbers get quoted. **This is correct and was left alone.**
It is not abandoned scaffolding, it is a documented refusal.

### One real conflict found

`docs/ICP-BRIEF.md` is marked "Locked 2026-08-31" and prices the offer at
**$49/seat design partner, $99/seat standard, $750 onboarding**, with a 30-day
build-first guarantee. The campaign brief in `00-START-HERE.md` prices it at
**$89/seat/month + $500 setup**, teams of 10+, free 2-week pilot with Stripe charging
on day 14. These disagree. `00-START-HERE.md` is dated later and is the campaign
authority, so all new copy in this batch uses $89 + $500 and the 2-week pilot.
`docs/ICP-BRIEF.md` was **not** edited, because it is shared with `reel-engine` and
`ad-engine` and rewriting a locked shared brief from inside one batch is not this
session's call. Logged in `BLOCKED.md` for Dovy to reconcile.

---

## 2. `icp_finder.py` — DOES NOT EXIST HERE (but its output does)

```
$ find / -name "icp_finder*" -not -path "*/proc/*" 2>/dev/null
(no output)
```

Searched the whole filesystem, not just this repo. There is no `icp_finder.py` in
this container. The spec describes it as an existing Google Custom Search -> MX
lookup -> CSV pipeline and says to extend rather than rewrite it. It is not here to
extend.

**It is however evidenced.** Its output artifacts are in Google Drive under
`DoviLoop Ops / Outreach /`:

- `leads_2026-08-11.csv` (3,784 bytes)
- `leads_2026-08-18.csv` (3,447 bytes)

Downloaded `leads_2026-08-18.csv` through the Drive connector. Header:

```
date_added,company,domain,country,vertical,est_size,fit_score,hook_seed,status,notes
```

Twelve rows, `country` in {US, DK}, `vertical` in {insurance, real estate},
`fit_score` 3 to 5, `status` = `new` on every row, and every single `notes` field
opens with an MX record:

```
MX=coverlink-com.mail.protection.outlook.com; independent agency: personal, business, benefits
MX=dkfm-dk.mail.protection.outlook.com; size unverified, may be under 20
MX=dacas-dk.mail.protection.outlook.com; property administration across Jutland + Funen, 20+ years
```

Every row resolves to `*.mail.protection.outlook.com`. **The Microsoft 365 MX gate
the spec describes is real and is confirmed by its own output**, even though the code
that produced it is absent from this container.

### How Batch C handled this

Two things, and they are different:

1. **The MX-based Microsoft 365 gate already lives in this repo**, in
   `engine/enrich.py::classify()` plus `engine/gate.py`. That is the same gate,
   implemented here, working (proved by the `mx` run above). So "extend, do not
   rewrite" was honoured against the local implementation: `engine/enrich.py` and
   `engine/gate.py` were **not** rewritten. New code imports and calls them.
2. **The discovery half** (Google Custom Search -> candidate domains) has no local
   implementation, so it was written new, as `engine/icp_finder.py`, keeping the
   exact `leads_*.csv` column contract found in Drive so the two are interchangeable
   and Dovy's existing files still load.

If the real `icp_finder.py` turns up on Dovy's machine, the merge is small and is
described in `RUN-REPORT.md`.

---

## 3. The `linkedin-automator` CLI — DOES NOT EXIST HERE

```
$ find / -iname "*linkedin*automator*" -not -path "*/proc/*" 2>/dev/null
(no output)
```

Not present. The spec says it is Python + Playwright, capped at 20 connects a day,
and that `build_linkedin_queue.py` must write "exactly the format the existing
automator expects". **That format could not be read, because the tool is not here.**

Guessing a schema and calling it "exactly the format" would be a lie in a file Dovy
trusts. What was done instead:

- `build_linkedin_queue.py` writes a documented, conservative JSONL queue, one object
  per line, plus a sibling `.csv` with the same fields, so whichever the automator
  reads it has a candidate.
- The field names and the whole record shape are declared in one dict in one place
  (`QUEUE_FIELDS` in `build_linkedin_queue.py`) so remapping to the real format is a
  single edit, not a rewrite.
- The 20/day cap is enforced regardless, since that number came from the spec and is
  not in doubt.

Logged in `BLOCKED.md`. This is the one deliverable that cannot be called verified.

---

## 4. The DSD discovery pipeline and its six-value taxonomy — DOES NOT EXIST HERE

```
$ grep -rin -E "dsd|taxonomy|apify|haiku" /home/user/outreach-engine
(no output — the strings appear nowhere in this repo)
```

No Apify config, no Haiku classifier, no six-value vocabulary, in this repo or
anywhere reachable. `C-outreach-engine.md` names the taxonomy twice but never
enumerates its six values, and the batch instructions restrict reading to
`00-START-HERE.md` and `C-outreach-engine.md` only, so the values could not be
recovered from a sibling spec either.

`sync_replies.py` needs a six-value vocabulary to classify replies into. Since the
real one was unavailable, six values were defined explicitly in
`config/reply_taxonomy.yaml`, in one file, marked as reconstructed:

`interested` · `not_now` · `not_a_fit` · `referred` · `objection` · `unsubscribe`

They are a reasonable reply-classification set and they are honestly labelled as
this batch's invention. **They are almost certainly not identical to DSD's six.**
Logged in `BLOCKED.md`. Reconciling is a one-file edit and the classifier reads the
YAML, so no Python changes when the real list arrives.

No LinkedIn scraping was performed or written in this batch, per the spec. Company
level public data only.

---

## 5. Existing outreach copy, sequences and `leads*.csv` — EXISTS, IN TWO PLACES

```
$ find / -iname "leads*.csv" -not -path "*/proc/*" 2>/dev/null
(no output — nothing on local disk)
```

Nothing local. Both stores are elsewhere:

### In this repo

`copy/capacity.json` and `copy/hours.json`. Two 3-step email variants, an A/B pair.
`capacity` = "take on more clients without hiring", `hours` = "hours saved" as the
control. Both are English-complete; every Danish and Lithuanian body is the literal
string `NEEDS_NATIVE_PROOFREAD`. So **DA and LT copy did not previously exist in
this repo at all** — the slots existed, the copy did not. Batch C writes real DA and
LT copy for the first time.

### In Google Drive — "DoviLoop Ops" structure, CONFIRMED PRESENT

The connector was live and the structure is real:

```
DoviLoop Ops/                     (folder 1VgkXs4uyZHEdPuUvog-jQCzJ7AMmhnkd)
  _Spine/
  Development/
  Marketing/
  Sales/
  Outreach/
    Pipeline (edit me)            (spreadsheet)
    leads_2026-08-11.csv
    leads_2026-08-18.csv
    Drafts/
      Outreach drafts — 2026-08-11
      Outreach drafts — 2026-08-18
```

Read `Outreach drafts — 2026-08-18` in full. It contains first-touch LinkedIn DMs
and cold emails for the top 5 M365-verified leads, in English and in Danish, signed
Dovy Vinickis, with the header "NOTHING HAS BEEN SENT."

Three things were taken from it, and one was deliberately not:

- **Taken: the ROI figures.** "roughly 9x ROI", "payback in about 40 days". These
  match `00-START-HERE.md` exactly, so they are corroborated from two independent
  places and are safe to use as the proof point where no testimonial exists.
- **Taken: the voice.** Short sentences, plain verbs, the hook drawn from something
  actually on the prospect's own website. The new sequences follow it.
- **Taken: proof that Danish copy is written for this ICP already.** The DACAS and
  dkfm.dk Danish drafts read as competent Danish. They still went out as drafts, not
  native-checked, which is the same posture this batch takes.
- **Not taken: the offer.** Those drafts pitch "a founding group of 50 companies,
  call first, no credit card upfront". The campaign offer is $89/seat/month + $500
  setup with a free 2-week pilot. Different offer. New copy uses the campaign one.
- **Not taken: the punctuation.** Those drafts are full of em dashes. The campaign
  copy rules forbid them. New copy has none.

Nothing in Drive was modified. Read only.

---

## 6. Ledger client `campaign_db.py` — DOES NOT EXIST HERE

```
$ find / -name "campaign_db*" -not -path "*/proc/*" 2>/dev/null
(no output)
```

Expected. It is Batch B's deliverable, in the `campaign-ledger` repo, which this
session cannot see or write to. Batch C imports it defensively and falls back to a
local logging shim. The seam is documented in `RUN-REPORT.md`.

---

## 7. Credentials in the session — one dangerous finding

| Variable | State |
|---|---|
| `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` | absent |
| `INSTANTLY_API_KEY` | absent |
| `ANTHROPIC_API_KEY` | absent |
| `CAMPAIGN_DB_URL` | absent |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | **SET** |

The Supabase pair is set, and it is the wrong project:

```
$ echo "$SUPABASE_URL" | grep -q "kngcxwcybozgqgnoweyt" && echo FORBIDDEN
FORBIDDEN
```

`kngcxwcybozgqgnoweyt` is the **product** project, which `00-START-HERE.md` rule 2
forbids touching. The only database credential available in this session points at
the one database this batch must not write to.

**Consequence, and it is a real one:** the spec's "rows written straight into
`campaign.companies` via `campaign_db.py`" could not be executed live, and would not
have been even if `campaign_db.py` were present, because the only reachable database
is off limits. Every ledger write in this batch therefore goes through the shim and
prints instead of writing. The CSVs in `lists/` are the real output of this run.

No code in this repo reads `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY`. No secret
value is written into any committed file. Logged in `BLOCKED.md`.

---

## Summary table

| Target | Verdict |
|---|---|
| `outreach-engine` repo, 4-stage pipeline | exists and runs, 7/7 tests pass |
| `engine/enrich.py` M365 MX gate | exists and runs, extended not rewritten |
| StatBank DK registry client | exists and runs, live data returned |
| LT registry fetchers | absent on purpose, correct, left alone |
| `icp_finder.py` | does not exist here; output CSV contract recovered from Drive |
| `linkedin-automator` CLI | does not exist here; queue format unverifiable |
| DSD pipeline + six-value taxonomy | does not exist here; taxonomy reconstructed |
| Drive "DoviLoop Ops" structure | exists, read, copy and leads CSVs found |
| DA / LT sequence copy | did not exist; written for the first time in this batch |
| `campaign_db.py` | does not exist here, expected, shimmed |
| Usable campaign database credential | none; the only one present is forbidden |

Gaps only from here. Nothing that already worked was rewritten.
