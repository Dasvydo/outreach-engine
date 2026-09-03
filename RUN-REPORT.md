# RUN-REPORT: Batch C, `outreach-engine`

Branch `campaign/c-outreach`. All work committed locally. **Nothing pushed.**
Run unattended 2026-09-03. Nothing was sent, published or charged.

Read `AUDIT.md` first if you want to know what was already here. Read
`BLOCKED.md` for the fifteen things that were missing and what each one blocks.

---

## The short version

Three market lists built and gate-verified against live DNS. Seven sequence
files written as real copy in three languages. Three loaders written, all three
dry-run clean, none of them able to send. 103 tests pass, including the one that
proves a Danish address cannot reach Instantly.

**Your part is about 25 minutes, not 15.** The spec estimated 15. It missed the
LinkedIn queue format, which you have to look up yourself because the automator
is not in this container. Breakdown at the bottom.

---

## QA gate, line by line, honestly

The spec's checklist, each line marked with what was actually run.

### `icp_finder` extension runs against fixtures and produces valid rows for all three markets

**PASS.**

```
$ python3 -m engine.icp_finder --all --probe
dk      24 candidates -> 19 passed the M365 gate -> 2 hard-failed the ICP gate -> 17 rows
lt      12 candidates ->  8 passed the M365 gate -> 1 hard-failed the ICP gate ->  7 rows
global  23 candidates -> 18 passed the M365 gate -> 1 hard-failed the ICP gate -> 17 rows
```

41 companies, in `lists/dk-2026-09-03.csv`, `lists/lt-2026-09-03.csv` and
`lists/global-2026-09-03.csv`.

`tests/test_icp_finder.py` asserts per row that the market and locale are right,
that `mail_provider` is `microsoft` and the MX host actually is a Microsoft one,
that the fit score is in range, and that the size band is one of the four from
the qualifier contract.

**What is real in those rows, since it matters.** Every domain is a real company
domain and every one went through a real live MX lookup, so the hard gate is
genuinely exercised and genuinely rejects. Every company that passed had its own
public website read for the size and dev-team signals, so `est_size`,
`dev_team_signal` and `notes` are real observations. What is not verified is the
`company` display name: where `name_source` is `drive` it came from your real
`leads_2026-08-18.csv`, and where it is `derived` it was reconstructed from the
domain. Check names before you write to anyone.

**What did not happen: the 100+ per market target.** 41 is not 300. There is no
Google Custom Search key in the session, so discovery ran against
`fixtures/serp/*.json` instead of the live API. The finder already loops queries,
pages and country hints, so this is a quota question, not a code one.
`BLOCKED.md` B3 and B13.

### Dedup proven: running twice adds nothing

**PASS, twice, two different ways.**

Once as a test, on a clean isolated ledger:

```
$ python3 -m pytest tests/test_icp_finder.py::test_running_twice_adds_nothing -q
1 passed
```

It asserts the second run reports `new == 0`, that its duplicate count equals the
first run's new count, and that the second CSV has a matching header and **zero
data rows**. Not "the same length". Empty.

And once for real, re-running all three markets against the ledger left behind by
the actual probed run:

```
=== dk ===       new this run 0     already in ledger 19
=== lt ===       new this run 0     already in ledger 8
=== global ===   new this run 0     already in ledger 18

$ wc -l dedup-proof/*.csv
  1 dk-2026-09-03.csv        <- header only
  1 global-2026-09-03.csv    <- header only
  1 lt-2026-09-03.csv        <- header only
```

**One caveat, stated plainly.** Dedup was proved against `engine/ledger.py`'s
shim, because Batch B's `campaign_db.py` does not exist in this container. The
shim is an idempotent upsert keyed on domain, which is what the real one will be,
but the proof is against the stand-in. Re-run the same command after wiring the
real module in and you will know in ten seconds.

### Danish addresses cannot reach the Instantly loader, proven with a test

**PASS.** `tests/test_danish_exclusion.py`, 8 tests, all passing.

The exclusion is a filter in `load_instantly.py` that runs before the payload is
built, on four independent signals, any one of which excludes:

1. `market == "dk"`
2. `country == "DK"`
3. the email domain ends in `.dk`
4. the phone number starts `+45`

There is no flag, argument or environment variable that turns it off, and one of
the tests reads the loader's own argument parser to confirm nobody has added one.
`build_payload()` raises `DanishAddressRefused` as a last line of defence if a
future caller skips the filter.

The tests attack it the way real data would, not the way a happy path would. The
one that matters most is `test_danish_company_mislabelled_as_global_is_still_refused`:
a Danish firm hand-tagged `global`, which is the realistic failure. It is caught
by the country check. There is a row like that in the shipped fixture on purpose
(`lars@sneaky-mislabelled.dk`, market `global`, country `DK`) and the live dry
run catches it:

```
  REFUSED lars@sneaky-mislabelled.dk    Danish exclusion: company country is DK

Danish addresses blocked at the loader: 4
```

### Every sequence file exists, in the right language, with correct UTMs

**PASS.** Seven files, and `tests/test_sequences.py` (49 tests) asserts there are
exactly seven, no more and no fewer.

```
sequences/linkedin/en.md    global   4 steps
sequences/linkedin/da.md    dk       4 steps   NEEDS NATIVE CHECK
sequences/linkedin/lt.md    lt       4 steps   NEEDS NATIVE CHECK
sequences/email/en.md       global   4 touches over 12 days
sequences/phone/da.md       dk       opener + 3 brush offs   NEEDS NATIVE CHECK
sequences/phone/en.md       global   opener + 3 brush offs
sequences/phone/lt.md       lt       opener + 3 brush offs   NEEDS NATIVE CHECK
```

Every file carries the spec's UTM template verbatim:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

and its filled per-step URLs, which a test checks against the file's own market
so `linkedin/da.md` cannot ship a `global_3`.

**One deliberate departure, and here is the reasoning.** The email and phone files
keep `utm_campaign` and `utm_content` exactly as the spec sets them and swap
`utm_source` and `utm_medium` to the channel that actually sent the click:
`instantly`/`email` and `phone`/`call`. Leaving `utm_source=linkedin` on an email
would file every email click in the LinkedIn column of Batch B's
`get_channel_funnel`, which is the single number the whole A/B exists to read.
Each file says so in its own UTM section. Revert it in seven places if you
disagree.

The Lithuanian files use the formal *Jūs* throughout and a test greps for the
familiar forms to make sure none slipped in.

### No em dashes in any sequence file

**PASS.** A per-file test, plus a scan across every deliverable in the repo:

```
$ grep -rn "$(printf '\xe2\x80\x94')" sequences/ config/ engine/ *.py
(no output, exit code 1)
```

The test also rejects an en dash used as an em dash, which is the usual way this
rule gets broken by accident.

Two related copy checks that are not in the spec's list but are in its spirit:
`test_no_ai_flavoured_phrasing_in_the_copy` bans "unlock", "supercharge",
"leverage", "seamlessly" and the rest from the quoted message text, and
`test_no_invented_social_proof` bans testimonial-shaped phrasing, because none
exists and the campaign brief says not to invent any. Where social proof would
normally sit, the ROI figures sit instead: around 9x return, about 400 euro a
month saved, payback in roughly 40 days. Those are corroborated in two
independent places, `00-START-HERE.md` and your real August drafts in Drive.

### Both loaders run clean in `--dry-run`

**PASS.** All three, exit code 0. Payloads below.

### Branch `campaign/c-outreach`, nothing pushed

**PASS.** All work is committed on `campaign/c-outreach` and `git push` was never run. No secret
value is written into any committed file; `.env.example` has empty values only.

---

## The dry runs, pasted

### `python3 load_instantly.py --dry-run`

```
read 12 contacts
eligible for Instantly: 5
refused: 7
  REFUSED mette@eksempel-revision.dk    Danish exclusion: market is dk
  REFUSED jens@eksempel-maegler.dk      Danish exclusion: market is dk
  REFUSED anne@eksempel-bolig.dk        Danish exclusion: market is dk
  REFUSED rasa@pavyzdys-apskaita.lt     market 'lt' is not an email market
  REFUSED tomas@pavyzdys-draudimas.lt   market 'lt' is not an email market
  REFUSED egle@pavyzdys-bustas.lt       market 'lt' is not an email market
  REFUSED lars@sneaky-mislabelled.dk    Danish exclusion: company country is DK

Danish addresses blocked at the loader: 4
This is markedsforingsloven, not a preference. Denmark runs on LinkedIn and phone.

--- DRY RUN, nothing sent. Payload for POST https://api.instantly.ai/api/v2/leads ---
{
  "campaign": "teams_q4_global",
  "skip_if_in_workspace": true,
  "leads": [
    {
      "email": "sarah@example-accounting.com",
      "first_name": "Sarah",
      "last_name": "Miller",
      "company_name": "Example Accounting Partners",
      "website": "example-accounting.com",
      "personalization": "Every year the same thing happens in the weeks before a filing deadline. The work is fine. It is the client email that breaks, because the same handful of questions arrive faster than anyone can answer them.",
      "custom_variables": {
        "segmentOpener": "Every year the same thing happens in the weeks before a filing deadline. The work is fine. It is the client email that breaks, because the same handful of questions arrive faster than anyone can answer them.",
        "market": "global",
        "segment": "accounting",
        "role": "owner_partner",
        "landingPage": "https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_1"
      }
    },
    {
      "email": "david@example-brokers.co.uk",
      "first_name": "David",
      "last_name": "Clarke",
      "company_name": "Example Brokers",
      "website": "example-brokers.co.uk",
      "personalization": "A claim goes in, the carrier takes its time, and the client still wants an update every couple of days in writing. Renewals run the same loop every quarter, with a different name on the file.",
      "custom_variables": {
        "segmentOpener": "A claim goes in, the carrier takes its time, and the client still wants an update every couple of days in writing. Renewals run the same loop every quarter, with a different name on the file.",
        "market": "global",
        "segment": "insurance",
        "role": "ops_office_manager",
        "landingPage": "https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_1"
      }
    }
    ... 3 more leads, same shape: laura@example-property.com (housing_admin),
        pieter@example-boekhouding.nl (accounting, NL),
        amira@example-student-housing.co.uk (housing_admin, GB)
  ]
}
--- end payload. 5 touches logged as planned via shim ---
```

The contacts are the synthetic fixture, not real people. See "what is missing"
below.

### `python3 build_linkedin_queue.py --all --dry-run`

```
markets       dk, lt, global
cap           20 connects a day, shared across all markets
queued        12 connects
  2026-09-08   12

--- DRY RUN, no file written. First 3 records ---
{
  "scheduled_date": "2026-09-08",
  "profile_url": "https://www.linkedin.com/in/example-mette/",
  "first_name": "Mette",
  "last_name": "Sorensen",
  "company_name": "Eksempel Revision",
  "company_domain": "eksempel-revision.dk",
  "market": "dk",
  "locale": "da",
  "segment": "accounting",
  "sequence_id": "linkedin_da",
  "step": 1,
  "note": "Hej Mette. Jeg arbejder med revisionsfirmaer og den bunke kundemails, der vokser i ugerne op mod en frist. Vil gerne forbindes.",
  "utm_content": "dk_1"
}
{
  "scheduled_date": "2026-09-08",
  "profile_url": "https://www.linkedin.com/in/example-rasa/",
  ...
  "sequence_id": "linkedin_lt",
  "note": "Sveiki, Rasa. Dirbu su buhalterinės apskaitos įmonėmis ir tuo klientų laiškų srautu, kuris išauga prieš terminą. Norėčiau susisiekti.",
  "utm_content": "lt_1"
}
{
  "scheduled_date": "2026-09-08",
  "profile_url": "https://www.linkedin.com/in/example-sarah/",
  ...
  "sequence_id": "linkedin_en",
  "note": "Hi Sarah, I work with accounting firms on the client email that stacks up in the weeks before a deadline. Happy to connect.",
  "utm_content": "global_1"
}
--- end ---
```

Each market gets its own language automatically. The cap is shared across all
three, not per market: three markets at 20 each would be 60 connects a day and
would get the account restricted. A test schedules 55 contacts and asserts no day
ever exceeds 20, and another asserts weekends are skipped.

### `python3 sync_replies.py --dry-run`

```
NOTE: the reply taxonomy in config/reply_taxonomy.yaml is reconstructed, not the
real DSD six. See BLOCKED.md B5.

7 replies, classifier=keyword, ledger=shim

  sarah@example-accounting.com          -> interested   (matched en:'sounds good')
      stage qualified    next: Book the discovery call within one working day.

--- DRY RUN, nothing written. record_reply payload for the first reply ---
{
  "company_domain": "example-accounting.com",
  "work_email": "sarah@example-accounting.com",
  "channel": "email",
  "step": 1,
  "market": "global",
  "replied_at": "2026-09-24T09:12:00Z",
  "reply_sentiment": "interested",
  "ledger_stage": "qualified",
  "classifier": "keyword",
  "classifier_note": "matched en:'sounds good'"
}
--- end payload, remaining replies summarised only ---

  david@example-brokers.co.uk           -> not_now      (matched en:'not right now')
  laura@example-property.com            -> unsubscribe  (matched en:'unsubscribe')
  pieter@example-boekhouding.nl         -> referred     (matched en:'copying')
  amira@example-student-housing.co.uk   -> objection    (matched en:'where is the data')
  ops@example-tiny.com                  -> not_a_fit    (matched en:'not a fit')
  info@example-quiet.com                -> objection    (nothing matched, sent to a human)

classified 7 replies
  interested 1   not_now 1   not_a_fit 1   referred 1   objection 2   unsubscribe 1

DRY RUN. Nothing was written to campaign.touches and no live Instantly call was made.
```

All six values exercised, plus the fallback. The classifier never invents a value:
anything unmatched becomes `objection`, which routes to a human, because "someone
should read this" is a safe wrong answer and "not interested" is not.

### `python3 -m pytest -q`

```
103 passed in 4.51s
```

Seven of those are the repo's original gate tests, untouched and still passing.

---

## What was built

| Thing | Where | State |
|---|---|---|
| Three market query configs | `config/queries/{dk,lt,global}.yaml` | 40 queries, native diacritics, directory domains excluded |
| Segment openers | `config/hooks.yaml` | 3 segments x 3 locales x 8 slots, all real copy |
| Reply taxonomy | `config/reply_taxonomy.yaml` | six values, reconstructed and labelled as such |
| Discovery | `engine/icp_finder.py` | runs, 41 companies, live MX gate |
| Soft signals | `engine/signals.py` | dev team scored, size read in en/da/lt |
| Ledger seam | `engine/ledger.py` | all eleven Batch B names, shim fallback |
| Contact reading | `engine/contacts.py` | CSV export, see B14 |
| LinkedIn sequences | `sequences/linkedin/{en,da,lt}.md` | 4 steps each |
| Email sequence | `sequences/email/en.md` | 4 touches, global only |
| Phone scripts | `sequences/phone/{da,en,lt}.md` | opener + 3 brush offs |
| Instantly loader | `load_instantly.py` | dry-run clean, Danish addresses excluded in code |
| LinkedIn queue builder | `build_linkedin_queue.py` | 20/day shared cap, weekends skipped |
| Reply sync | `sync_replies.py` | six values, keyword classifier, no key needed |
| Market lists | `lists/*-2026-09-03.csv` | 41 rows, MX-verified |
| Env template | `.env.example` | every key named, no values |
| Tests | `tests/` | 103 passing |

### One bug fixed in existing code

`engine/enrich.py` was classifying Microsoft's newer Exchange Online endpoint
(`*.mx.microsoft`) as `other`, so genuine Microsoft 365 firms were failing the
hard gate and being dropped. Found by probing 84 real ICP domains, not by reading
documentation: `redmark.dk` and `vbtm.nl` were both in the campaign's own
candidate lists and both were being thrown away. One signature added, regression
test in `tests/test_icp_finder.py`. That is the only change made to pre-existing
code, and it is an addition, not a rewrite.

A second, quieter version of the same problem was found while stabilising the
test suite: **a DNS timeout looks exactly like a firm with no Microsoft 365.**
Under concurrency a handful of MX lookups time out on any given run, and every
one of those was silently dropping a qualified firm from the list. No error, no
crash, just a shorter list than you should have had, varying run to run. The
finder now retries an UNKNOWN result once and reports undecidable domains
separately from genuine non-Microsoft ones:

```
M365 hard gate    19 pass, 5 rejected (0 of those undecidable, retry them)
```

If that number is ever above zero, the run under-counted and is worth repeating.
Across three markets it is currently zero.

---

## What was skipped, and why

| Skipped | Why | Blocked ref |
|---|---|---|
| Any live Instantly call | No key, and the sending domains do not exist. Nothing sends in this batch by rule. | B6 |
| Any live search | No `GOOGLE_API_KEY`. Ran against fixtures. | B3 |
| 100+ companies per market | Same cause. Got 41. | B13 |
| Any database write | The only Supabase credential in the session points at the **product** project `kngcxwcybozgqgnoweyt`, which is off limits. Everything went through the shim. | B1 |
| Extending the real `icp_finder.py` | Not in this container at all. Its CSV contract was recovered from Drive and matched instead. | B2 |
| Writing the real automator queue format | The automator is not in this container. Format could not be read. | B4 |
| The real DSD six-value taxonomy | Not in this container, and the spec never enumerates it. Six were reconstructed. | B5 |
| Contact discovery | Company-level public data only, no LinkedIn scraping. 41 companies, zero contacts. | B15 |
| Editing `docs/ICP-BRIEF.md` | It is shared with `reel-engine` and `ad-engine`. Rewriting a locked shared brief from inside one batch is not this session's call. | B8 |
| Model-based reply classification | No `ANTHROPIC_API_KEY`. Keyword classifier ships as the default. | B7 |

---

## The seam Batch B has to be wired into

`engine/ledger.py` is the only file in this repo that knows `campaign_db` exists.

```python
try:
    import campaign_db as _real
except ImportError:
    _real = None
```

When it imports, every call delegates and the shim never runs. When it does not,
the shim logs the exact call it would have made to `.ledger-shim/calls.jsonl` and
keeps a domain index so dedup still behaves correctly.

All eleven names are wired: `upsert_company`, `upsert_contact`, `log_touch`,
`record_reply`, `insert_lead`, `upsert_content`, `snapshot_content_stats`,
`snapshot_ad_stats`, `get_market_funnel`, `get_channel_funnel`,
`get_content_perf`. A test asserts all eleven are callable.

**To wire it in: put `campaign_db.py` on the import path. That is the whole
change.** Then `python3 -c "from engine import ledger; print(ledger.backend_name())"`
prints `campaign_db` instead of `shim`.

**Two things to check when you do.**

1. **The column names may not match.** The batch instructions said the column
   lists for `campaign.companies`, `campaign.contacts` and `campaign.touches`
   were in the Batch C spec. They are not, and this session could not read
   `B-ledger.md`. So they were derived from the shared qualifier payload contract
   and the two column names the spec does state outright (`replied_at`,
   `reply_sentiment`). They live in `COMPANY_COLUMNS`, `CONTACT_COLUMNS` and
   `TOUCH_COLUMNS` at the top of `engine/ledger.py`. Diff those three tuples
   against your migration and fix any name that differs. B12.
2. **There is no way to read contacts back.** The eleven functions are eight
   writes and three aggregate reads; none returns a contact list. Both loaders
   read a CSV export through `engine/contacts.py` instead. Either add a
   `get_contacts(market=...)` to Batch B, or export the table before each load.
   B14.

---

## What you have to do yourself

About **25 minutes**, in this order. The spec said 15; it did not account for the
LinkedIn queue format.

| # | Task | Time | Why it cannot be done in the batch |
|---|---|---|---|
| 1 | Add `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` to `.env`, re-run `python3 -m engine.icp_finder --all --probe` | 5 min | No key in the session. This is what turns 41 companies into a few hundred. |
| 2 | Open the `linkedin-automator`, read one queue file it accepts, edit `QUEUE_FIELDS` in `build_linkedin_queue.py` to match | 5 min | The tool is not in this container. This is the one deliverable that cannot be called verified. |
| 3 | Read `sequences/linkedin/da.md`, `phone/da.md`, `linkedin/lt.md`, `phone/lt.md`, then send all four to native speakers | 10 min to read, then wait | Nobody in this session speaks Danish or Lithuanian natively. |
| 4 | Paste the real DSD six values into `config/reply_taxonomy.yaml` | 2 min | Not recoverable in this container, and the spec never lists them. |
| 5 | Diff `COMPANY_COLUMNS` / `CONTACT_COLUMNS` / `TOUCH_COLUMNS` against Batch B's migration | 3 min | The real lists were not readable from this session. |
| 6 | Reconcile `docs/ICP-BRIEF.md` ($49/$99/$750) against the campaign offer ($89 + $500) | 5 min | Shared with two other repos. Not one batch's call. |

**Not on the clock, because they are purchases and calendar time, not keyboard
time:** buy the Instantly seat and 2 to 3 sending domains and start warmup (email
cannot begin before roughly 22 September regardless of when you do this), and run
the DSD pipeline over `lists/*.csv` to turn 41 companies into named contacts.

**Before you send anything at all:** verify the `company` values where
`name_source` is `derived`. They were reconstructed from the domain, not looked
up. Getting a firm's own name wrong in the first line is worse than not writing.

---

## Where this departed from the spec

Four places, all deliberate, all reversible.

1. **`icp_finder.py` was written new rather than extended,** because it is not in
   this container. The MX gate half of it, which is the part the spec cares
   about, does exist here as `engine/enrich.py` and was extended rather than
   rewritten. The CSV column contract was recovered from your two real
   `leads_*.csv` files in Drive and matched exactly, so old and new files are
   interchangeable. B2.

2. **Email and phone UTMs swap `utm_source` and `utm_medium` to the real
   channel.** Campaign and content are untouched. Reasoning in the QA section
   above: leaving `utm_source=linkedin` on an email breaks the channel funnel the
   A/B is built to read. Every sequence file also carries the spec's template
   verbatim, so the original string is present in all seven.

3. **The LinkedIn queue format is documented, not matched.** The spec says
   "exactly the format the existing automator expects" and that format could not
   be read. Writing a guess and calling it exact would be a lie in a file you are
   going to trust. Two shapes are written, JSONL and CSV, with every field name
   in one dict. B4.

4. **Hard gate failures are written to the ledger but kept out of the CSV.** The
   spec's gate order does not say what to do with a firm that passes the MX gate
   and then fails G4 or G7. Writing it as `disqualified` is what stops the next
   run rediscovering it; keeping it out of the list is what stops you emailing a
   1,500-person brokerage. Gallagher, Civinity, Martinsen and Redmark were caught
   this way and are named in the run output.

---

## Two things worth knowing that nobody asked about

**The MX gate was silently dropping real prospects.** See the bug above. Any list
built with this repo before 2026-09-03 is missing every firm on Microsoft's newer
mail endpoint. If you have old `leads_*.csv` files, re-run the domains marked
`other` through `python3 -m engine.cli mx`; some of them were always qualified.

**Lithuania is structurally thinner than the other two markets and always will
be.** Four of twelve LT candidates failed the MX gate, one of them on Google
Workspace, and there is no open Lithuanian company registry to enumerate from.
The existing `engine/registry.py` already refuses to fake LT numbers, correctly.
Insurance in LT is a closed licensed register of 105 firms, which is the entire
market rather than a sample, so read its reply rate qualitatively and never
compare it against accounting's. Expect LT to need hand enumeration from
rekvizitai.vz.lt to reach parity.

---

## Reconciliation with Batch B's real ledger — 2026-09-03

Batch B's `campaign_db.py` became readable after this batch was finished. This
repo had been calling its functions by the right names with the wrong arguments,
and would have raised `TypeError` on the first real connection.

**What was wrong.** `engine/icp_finder.py` sent `company_name=`, `employees_est=`,
`dev_team_signal=`, `mail_provider=`; B declares `name=`, `est_size=`,
`has_dev_team=`, `uses_m365=`. `load_instantly.py` and `build_linkedin_queue.py`
sent a whole `log_touch` payload with no `contact_id` in it at all, and B keys
`campaign.touches` on `contact_id` with a NOT NULL foreign key. Four company
fields and four touch fields had no column on B's side. This repo's segment
`housing_admin` is B's `admin`, its `source` carries a `:market` tag B's enum
does not allow, and its `fit_score` is a 0.0–1.0 float where B's column is an
integer with a `0..100` check constraint.

**Why nobody noticed.** The local shim in `engine/ledger.py` accepts any keyword
argument, so all 103 tests passed and both dry runs printed correctly. A suite
can only test the contract it was told about, and this one had been told the
wrong contract by its own fallback.

**What changed.** The translation happens in `engine/ledger.py` and nowhere else.
The repo keeps its own vocabulary internally — `COMPANY_COLUMNS` and
`TOUCH_COLUMNS` are unchanged, the finder and the loaders read the same as
before — and three pure builders (`company_kwargs`, `touch_kwargs`,
`reply_kwargs`) map it onto B's contract at the boundary. The shim still receives
the untranslated row, because its job is to be a readable record of what this
repo meant.

Two derivations are worth naming because they had to match rules that already
existed elsewhere in the repo:

- `mail_provider` → `uses_m365` uses the MX gate's own test, `provider is
  Provider.MICROSOFT` and nothing else. `unknown` becomes NULL, not false: it
  means the lookup failed, which is not the same as "not Microsoft", and B's
  column is nullable precisely so that stays sayable.
- `dev_team_signal` → `has_dev_team` uses `icp_finder`'s own rule, `False if
  score < 0.5 else None`. The gate hard-fails on `True` and a scored guess is not
  grounds for a hard fail. When the score is too high to say `False`, the number
  itself is written into `hook_seed` as `dev_signal=0.62` rather than lost.

**Nothing is dropped.** `city`, `team_size`, `stage` and `notes` are folded into
the `hook_seed` text column; `sequence_id`, `utm_content`, `status`, `market`,
`company_domain` and `work_email` into `touches.notes`. Both folds are readable
`key=value` text and both are named as schema gaps in BLOCKED.md C-B1 and C-B2,
with the `ALTER TABLE` that would close them.

**`log_touch` now supplies a real `contact_id`.** B exposes no reader, so the
adapter resolves the contact before every touch: an explicit id, else a cached or
explicit `company_id` plus the email, else `upsert_company` (idempotent on
domain) followed by `upsert_contact` (idempotent on the LinkedIn URL, else the
email). The three call sites now pass the identity fields that makes possible —
they are not new touch columns, and `sync_replies.py` matches each reply back to
the contacts export by email for the same reason. When a contact genuinely
cannot be resolved the call raises `LedgerContactUnresolved` naming what was
missing, rather than writing a touch against a made-up person. BLOCKED.md C-B3.

**One thing is refused rather than guessed.** This repo's six reply values and
B's six are different lists (BLOCKED.md C-B4). Mapping `interested` onto
`hot_pain` rather than `curious` would silently change what every reply rate in
the Friday brief means, so `engine/ledger.py` refuses any value B does not know
and prints both vocabularies.

**Tests.** 103 before, 129 after. The 26 new ones are in
`tests/test_ledger_contract.py`, and they do the one thing that would have caught
this on the day: they load `campaign_db.py` from the campaign-ledger repo **by
file path** and `inspect.signature(...).bind(...)` the arguments this repo
builds. Two of them assert the old payloads would *not* have bound, so the
translation cannot be quietly removed. Two more drive `icp_finder.run_market()`
and `load_instantly.log_touches()` end to end against a stand-in whose every
function binds against B's real signature before returning. Nothing connects to
anything: B's client is built lazily, and none of its functions is ever called,
only its signature read. The tests skip rather than fail when campaign-ledger is
not checked out beside this repo.
