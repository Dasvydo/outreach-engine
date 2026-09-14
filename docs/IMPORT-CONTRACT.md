# The `leads_*.csv` import contract

Lead discovery moved out of this repo to **AI Arc** (external). `engine/icp_finder.py`
is dead weight: Google Custom Search can no longer search the open web. Nothing in
this repo discovers leads any more.

What this repo still owns is the **target shape**: whatever AI Arc emits has to land
in the `leads_*.csv` column contract the rest of the pipeline already reads.

This document records that contract **as measured against two real files**, not as
assumed. Both were read out of Dovy's Drive on 2026-09-14:

| file | id | rows |
|---|---|---|
| `leads_2026-08-11.csv` | `1eZWWBdb9tksYy8Aud6r7S7qjQMwF4P-J` | 15 |
| `leads_2026-08-18.csv` | `1oCJxGorVEUro58bGfgea6J0Jud4EGAhm` | 12 |

Both live in Drive folder `1hhWK8Y4EOmimKAQa3TmrMW7_FIlwUj0l`.

## The ten columns

Exactly ten, in this order, with a plain header row and no BOM:

```
date_added,company,domain,country,vertical,est_size,fit_score,hook_seed,status,notes
```

This matches the first ten entries of `engine/icp_finder.py::CSV_COLUMNS`, which
already says it is copying the Drive contract. The ten remaining columns in that
list (`market`, `segment`, `locale`, `team_size`, `mail_provider`, `mx_host`,
`dev_team_signal`, `dev_team_reasons`, `name_source`, `source`) are campaign
additions and are **not** present in the Drive files. An importer has to derive
them.

### Observed values

| column | type | observed |
|---|---|---|
| `date_added` | ISO date | matches the filename stamp on every row |
| `company` | text | may contain `–`, `&`, `æ`, `å` — UTF-8, quote-wrapped when it has a comma |
| `domain` | bare host | no scheme, no `www.`; includes a non-`.com` TLD (`nrp.management`) |
| `country` | ISO-3166-2 | `DK`, `US` — one file mixes both, so a single file spans two markets |
| `vertical` | enum | `insurance`, `real estate` — **see defect 1** |
| `est_size` | integer | 10–80, always populated in both files |
| `fit_score` | integer **1–5** | **see defect 2** |
| `hook_seed` | free text | quoted, contains `'` and `—` |
| `status` | enum | `new` on every row |
| `notes` | free text | leads with `MX=<host>`, then `;`-separated remarks |

## Two defects that will bite the importer

Both are measured, not predicted.

### Defect 1 — `real estate` is hard-rejected by the gate

`engine/model.py` declares `VERTICALS = ("accounting", "administrative", "insurance")`.
`engine/gate.py::evaluate` treats anything else as a **hard** failure:

```
vertical='insurance'     passed=True   reasons=()
vertical='real estate'   passed=False  reasons=("off-ICP vertical: 'real estate'",)
```

`real estate` is 7 of 12 rows in the 08-18 file and 8 of 15 in the 08-11 file.
**A straight import drops ~58% of a real lead file on the floor.**

It is a vocabulary mismatch, not an ICP disagreement. The same companies carry
different labels in the two sources:

| domain | `lists/*.csv` (this repo) | `leads_*.csv` (Drive) |
|---|---|---|
| `dacas.dk` | `administrative` | `real estate` |
| `realadmin.dk` | `administrative` | `real estate` |
| `dkfm.dk` | `insurance` | `insurance` |

**But `real estate` is not one category.** In the Drive files it covers two
genuinely different businesses:

- *property administrators / HOA managers* — DACAS, Real Administration,
  R.E.M. Residential, Cobblestone, Bay Management Group, IPM Association Services.
  These are `administrative` / `housing_admin` in this repo's vocabulary.
- *estate agents and brokerages* — A&M Bolig, Aarhus Mæglerne, Corcoran Perry & Co.,
  LokalBolig. These sell homes. They are **not** in this repo's ICP at all.

So `real estate -> administrative` cannot be applied blindly. **Open question for
Dovy**, recorded rather than guessed.

### Defect 2 — `fit_score` is on a different scale, and fails silently

This repo scores `0.0`–`1.0` (`lists/*.csv` carries `1.0`, `0.75`). The Drive files
score **integer 1–5**. `engine/ledger.py::fit_score` rescales to Batch B's integer
`0..100` column by multiplying by 100:

```
ledger.fit_score(0.82) -> 82     correct, this repo's scale
ledger.fit_score(5)    -> 5      a best-possible lead stored as 5% fit
ledger.fit_score(3)    -> 3
```

It does not raise. A 5-of-5 lead lands in the ledger as **5% fit** and everything
downstream that ranks on `fit_score` silently inverts. `1.0` is valid on both
scales, so no per-value check can tell them apart — **the importer must normalise
at the boundary**, and `ledger.fit_score`'s input contract stays `0.0`–`1.0`.

Suggested normalisation, pending confirmation: `(n - 1) / 4`, mapping 1→0.0 and
5→1.0. Not applied yet.

## Derived columns

An importer has to supply these; none is in the Drive files.

| column | how |
|---|---|
| `market` | from `country`: `DK`→`dk`, `LT`→`lt`, everything else→`global` |
| `locale` | from market: `dk`→`da`, `lt`→`lt`, `global`→`en` (`LOCALE_BY_MARKET`) |
| `segment` | from `vertical`, once defect 1 is settled |
| `mail_provider`, `mx_host` | **re-run `engine/enrich.py::classify`**, do not parse `notes` |
| `team_size` | `engine/signals.py::to_band(est_size)` |
| `dev_team_signal` | `0.0` unless assessed; never assert `True` from a heuristic |
| `source` | `ai_arc:<market>` — note `engine/ledger.py` strips the `:<market>` tag, and Batch B's `_COMPANY_SOURCES` enum is `icp_finder`, `linkedin`, `inbound`. **`ai_arc` is not in it** — a column value Batch B would reject. Belongs to Session F+B, per the brief. |

The `notes` column already carries `MX=<host>` from whatever produced the file, but
re-resolving is cheap (one DNS query, no key, no cost) and the MX gate is the ICP
filter that matters. Verified working against live DNS on 2026-09-14: 12/12 of the
repo's DK domains reclassified identically, and control domains discriminate
correctly (`gmail.com`→google, `github.com`→microsoft, `protonmail.com`→other,
NXDOMAIN→unknown).

## Still needed

**One real AI Arc export file.** Everything above is the *target* half of the
contract and is now settled. The *source* half — what AI Arc actually emits, under
what column names — is unknown, and the brief is explicit that it should be built
against a real file rather than an assumed shape. Nothing is written until one
arrives.
