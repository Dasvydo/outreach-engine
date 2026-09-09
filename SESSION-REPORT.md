# Session report - outreach-engine (batch C)

Branch `claude/campaign-build-status-9j9194`. Date 2026-09-09.

## Verified

Every number below was observed in this session, from this clean clone.

| What I ran | Result |
|---|---|
| `pip install -r requirements.txt` | installed dnspython 2.8.0; PyYAML already present |
| `pip install pytest` | pytest 9.1.1. Not in `requirements.txt` by design - it is a documented dev dependency |
| `python3 -m pytest tests/ -q` (PYTHONPATH unset) | **138 passed**, 9.99s - matches the expected number exactly |
| same, after my change | **141 passed**, 5.70s (138 + the 3 new parametrised cases) |
| `git clone` campaign-ledger to `../campaign-ledger` | cloned; checked out `claude/campaign-build-status-9j9194`, HEAD `8bc38f3` |
| `python3 -m pytest tests/test_ledger_contract.py -q` | **28 passed**, 0.53s |
| `python3 -m engine.cli counts` | live StatBank, no key: accounting **4,882**, administrative **1,793**, insurance **448** |
| `python3 -m engine.cli mx cbs.dk pwc.dk doviloop.dev` | `cbs.dk` microsoft (passes G1) / `pwc.dk` unknown / `doviloop.dev` google |
| `python3 -m engine.cli gate segments/example-leads.json` | **qualified 1 / 3** |
| `python3 -m engine.cli build ... --out queue/acc-dk.csv` | **exit 2, REFUSED.** No CSV written |
| `python3 -m pytest tests/test_danish_exclusion.py -q` | 8 passed |

The 28 contract tests **passed, they did not skip.** I checked this specifically:
the summary line reads `28 passed` with no skip count, and
`../campaign-ledger/src/campaign_db.py` exists at the relative path the tests
resolve. `PYTHONPATH` was empty for the whole session and I ran every pytest
invocation under `env -u PYTHONPATH` so the shim-directory fixtures could not
be defeated by an inherited path.

### The gate result in full

3 firms in, **1 survived, 2 rejected.** Every rejection carries a reason; none
were dropped silently.

| Firm | Provider | Employees | Dev team | Verdict | Score | Reasons |
|---|---|---|---|---|---|---|
| Nordic Revision ApS | microsoft | 14 | false | **keep** | 1.0 | none |
| Tiny Books | other | 3 | false | drop | 0.8 | `G4: 3 employees, need >= 10` (hard) + `G1: neither Microsoft nor Google` (soft) |
| DevShop Accounting | microsoft | 40 | true | drop | 1.0 | `G6: has an in-house development team` (hard) |

Rejection reasons by gate, counting every reason the gate emitted across all 3
firms: **G1 x1, G4 x1, G6 x1. G2, G3, G5, G7 x0.** Only two of those were
decisive - G4 and G6 are the hard failures; the single G1 reason is a soft
downrank that rode along on a firm already failing G4.

### The three specific checks requested

- **G1 downranks, does not disqualify.** Confirmed. `engine/gate.py` appends the
  Google case to `soft` and applies `score -= 0.35`. Exactly 0.35, and it never
  reaches the `hard` list.
- **G4 (under 10 seats) and G6 (in-house developers) are hard failures.**
  Confirmed. Both append to `hard`, and `passed = not hard`.
- **`&source=outreach` in all three phone sequences.** Confirmed present in
  `sequences/phone/da.md`, `en.md` and `lt.md`, on the filled
  `utm_source=phone` link in each. The 2026-09-08 fix is intact.

  Each file also contains a second URL *without* `&source=outreach`, on the line
  above. That one is correct as-is: it is the campaign spec's
  `utm_source=linkedin&utm_medium=dm` template, quoted verbatim for contrast
  before the phone-specific link overrides it. `test_carries_the_spec_utm_template_verbatim` requires it to stay exactly that way.

## Produced

- **`tests/test_sequences.py`** - added `test_phone_links_carry_the_outreach_source`
  (3 parametrised cases, one per phone file). Commit `7ae1a40`.
- **`SESSION-REPORT.md`** - this file.

**No CSV was produced.** `queue/` does not exist on disk; the build refused
before `engine/export.py` was reached, so the directory was never created. I
have no row count to report and am not going to invent one.

The new test is the only code change. I added it because `&source=outreach` had
**no test holding it in place** - `grep -rn "source=outreach" tests/ engine/`
returns nothing on the pre-existing tree. A parameter that was already lost once
in production, and whose loss is invisible (the link still works, the attribution
just silently becomes `direct`), was resting on nothing but the next editor's
memory.

I verified the test actually catches the bug rather than merely passing: with
`&source=outreach` stripped from `sequences/phone/en.md`, it fails with the
offending URL in the message; restored, it passes. **The mutation was applied to
the English file only** and reverted with `git checkout`; `git status` confirms
`sequences/` is clean. No Danish or Lithuanian copy was touched at any point.

## Found

**1. The build stops at the proofread gate, by design.** `--variant capacity`
refuses with `variant 'capacity' step day 0 is not proofread in 'da'` and exits
2. Both variants are equally blocked: `capacity.json` and `hours.json` each
carry 5 `NEEDS_NATIVE_PROOFREAD` fields in `da` and 5 in `lt`, across 3 steps.
Nothing can be built for a DK or LT contact until a native speaker clears them.
This is the gate working, not a bug - but it does mean the end-to-end Danish
segment cannot be completed by anyone without that review.

**2. G2, G3 and G5 are documented but not implemented.** `engine/gate.py` opens
"The seven qualification gates" and `docs/ICP-BRIEF.md` lists all seven, but only
**G1, G4, G6 and G7** are evaluated in code. G2 (email is the primary client
channel), G3 (recurring questions have stable answers) and G5 (no regulatory bar
on AI client comms) are never checked. The gate also applies two checks that are
*not* in the brief's table: off-ICP vertical, and missing domain.

This is the one place where "every rejection carries a reason" is weaker than it
looks. Nothing is dropped silently - but a firm that would fail G3 is not
rejected either; it is *passed*, with no reason recorded in either direction.
G3 is the brief's own emphasised gate and the one shared with the reel content
rule, so a lead surviving this gate has not been assessed against it at all.
Worth the founder's attention before the survivor list is treated as qualified.

**3. A null MX is classified `other`, not `unknown`.** `example.com` publishes
MX `.` - RFC 7505, meaning *this domain accepts no mail ever*. `engine/enrich.py`
strips the trailing dot, producing a one-element tuple containing the empty
string, which is truthy, so the `if not hosts` guard does not fire and it falls
through to `Provider.OTHER`. The lead is then soft-downranked 0.20 and labelled
"needs a manual look".

Its own docstring says `UNKNOWN` covers "NXDOMAIN, no MX, or lookup failed", so
the code contradicts its documented contract. I did **not** fix it, for a reason
worth stating: changing it to `UNKNOWN` would align the label but **would not fix
the actual risk**, because `UNKNOWN` is also only a soft downrank (0.15). Either
way the firm still passes the gate and can still be exported into a send queue,
where every message hard-bounces and costs sender reputation. The real fix -
hard-failing a provably undeliverable domain - is an ICP policy change and the
founder's call, not mine. Flagging both halves rather than applying the cosmetic
one.

No live lead was affected here: `Tiny Books` was already hard-failed by G4.

**4. `score` is not zeroed on a hard failure.** `DevShop Accounting` fails G6
outright yet scores **1.0** - a higher score than a firm that merely has an
unknown employee count. Harmless today, because `partition()` sorts only the
`kept` list and keys off `passed`. It becomes a live bug the moment anything
ranks or thresholds on `score` without first checking `passed`.

**5. `pwc.dk` has no MX record at all**, which I confirmed directly against DNS
(`NoAnswer`, not a timeout). The `unknown` classification is correct. But it is
worth knowing what it means for enrichment quality: a real firm can be
soft-downranked 0.15 purely because its apex domain does not host mail, when in
fact mail lives on a parent domain (`pwc.com`). Absence of an apex MX is not
absence of a mail provider, and G1 currently cannot tell the two apart.

**6. G4 compares total headcount, not the ICP's actual criterion.** The brief
says "10+ **people writing client email**"; the code compares `firm.employees`,
total headcount. For a small accounting firm these are close enough. For the
administrative and insurance verticals they may not be, and the gate would let
through a firm with 40 staff and 4 client-facing writers.

**7. The example segment is a fixture, not a Danish segment.** Its three domains
are `cbs.dk` (Copenhagen Business School), `example.com` (IANA reserved) and
`github.com`. The gate numbers above are real observations of the gate's
behaviour, but they are not observations about real Danish firms. See Blocked.

**8. The Danish cold-email block is intact and correctly layered.** Worth
recording precisely, since the refusal I hit was a *different* gate. The
marketing-law exclusion does not live in `engine/cli.py build` at all - it lives
in `load_instantly.eligible()`, at the boundary where addresses would actually
reach Instantly, with four independent signals (dk market, `.dk` address,
country code, `+45` phone) plus a `DanishAddressRefused` raise at
`load_instantly.py:128` as a last line of defence. All 8 of its tests pass. I
did not remove, weaken, or route around it.

## Blocked

**A genuine Danish segment could not be built.** This is the headline: the task
asked for a real segment end to end, and I could not produce one. `segments/`
contains only `example-leads.json`, the 3-row fixture above. `engine.cli counts`
returns live *aggregate* counts (4,882 accounting enterprises) but no per-firm
rows, and there is no list-building command that turns those into leads.
*Needs:* either a real segment file committed to `segments/`, or CVR API
credentials from the Danish Business Authority - free, but credentials, which I
must not request or hold. `engine/registry.py:56-63` notes the same limit for
size bands: DST publishes only "<10" vs "10-49" publicly, so any 10+ figure
derived from StatBank alone is an estimate and must be labelled as one.

**The CSV could not be produced.** Blocked by the strict proofread gate (Found
#1). *Needs:* a native Danish speaker to clear the 5 `da` sentinel fields in
`copy/capacity.json`. The `--allow-english-fallback` flag would bypass it and
write the CSV, but that flag exists to send English where DA copy is not ready,
which is a campaign decision and not mine to take. **I did not use it**, and so
I have no row count, no example rows, and no `queue/` directory to report.

**Not acted on, by instruction:** the six parked decisions P-1 to P-6. They are
not present anywhere in this repository - `grep` across `docs/`, `BLOCKED.md`
and `README.md` returns nothing - so they presumably live in
`campaign-n8n/ops/DECISIONS.md`. I did not go looking for them cross-repo and
did not act on any of them.

**Reported, not fixed,** per the same instruction: Found #2 (unimplemented G2/G3/
G5), #3 (null MX), #4 (score not zeroed), #5 (apex MX absence), #6 (G4
headcount). Each is a semantic or policy change to a live gate, so each is the
founder's call. The one change I did make is additive, guards a bug that was
already fixed once, and changes no gate behaviour.
