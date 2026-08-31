# CVR access: what is needed to build the Danish list

> Written 2026-08-31 while building `accounting-DK`. **The list is blocked on
> credentials.** This is the write-up of exactly what is needed, and the
> evidence for why no other route was taken.

## The blocker in one line

Enumerating Danish companies by industry code and employee band requires the
Danish Business Authority's system-to-system CVR API, which is **free but
credentialed**. We do not have credentials. Everything downstream of the list
is built, tested and waiting.

```
$ python -m engine.cli cvr-check
CVR company index: http://distribution.virk.dk/cvr-permanent/virksomhed/_search
  credentials: NOT CONFIGURED
  reachable, HTTP 401 Unauthorized
  the index requires HTTP Basic auth Basic realm="Beskyttet adgang"
```

## How to unblock it

1. **Email `cvrselvbetjening@erst.dk`** asking for system-to-system access to
   CVR data (*"system-til-system adgang til CVR-data"*).
2. They reply with a **declaration to sign** — an undertaking to honour the
   conditions for receiving data on advertising-protected companies. Sign and
   return it.
3. They issue a **username and password**. Put them in the environment:

   ```bash
   export CVR_USER=...
   export CVR_PASSWORD=...
   python -m engine.cli cvr-check      # should print "access is working"
   python -m engine.cli list-dk --vertical accounting --out segments/accounting-dk.json
   ```

There is no payment step and no company-size requirement. The cost is the
turnaround on the email, which is the reason this is worth starting before it
is needed.

Erhvervsstyrelsen reserves the right to block clients that query the index
inefficiently. `engine/cvr.py` pages with `search_after` rather than deep
`from` offsets for that reason.

## The advertising-protection condition — read this before sending

CVR flags companies that have opted out of being approached for marketing
(`reklamebeskyttet`). **This is the substance of the declaration you sign**, and
it lands directly on this project: a cold email to a `reklamebeskyttet` firm is
the thing the agreement forbids.

`engine/cvr.py` drops those firms during the harvest, before the gate sees
them, and counts the drops so they appear in the run report. It is not an
eighth gate and should not be moved into `gate.py` — the gate scores fit, and
this is a permission question that is settled before fit is considered.

Expect this to shrink the list. That is the correct outcome, not a bug.

## Routes probed, and why each was rejected

| Route | Result | Verdict |
|---|---|---|
| `distribution.virk.dk/cvr-permanent/virksomhed/_search` | **401**, Basic realm "Beskyttet adgang" | **The right route.** Blocked on credentials. |
| `datacvr.virk.dk` (web UI) | **403**, `cf-mitigated: challenge` — Cloudflare interactive bot challenge | Human-interactive only. Driving a browser through the challenge to bulk-extract records is scraping and circumvents an access control the registry deliberately placed. Not done. |
| `distribution.virk.dk/offentliggoerelser/_search` | **200**, open, 6,425,988 annual reports | Real and free, but keyed by CVR number only. The index carries **no industry code, no company name, no employee count, no address** (mapping is `cvrNummer`, `dokumenter`, `sagsNummer`, `regnskab.regnskabsperiode`, timestamps). It can enrich a firm you already have; it cannot find one. |
| Datafordeleren (`datafordeler.dk`) CVR service | reachable | Documentation states *"Erhvervsstyrelsen har ikke planlagt at udstille CVR data som filudtræk på Datafordeleren"* — no file extracts, no documented branchekode or employee filtering. Dead end. |
| `datahub.virk.dk`, `hub.virk.dk`, `erhvervsstyrelsen.dk` | unreachable / 403 | Blocked by network policy or Cloudflare from this environment. |
| Statistics Denmark StatBank (`engine/registry.py`) | **200**, working | Counts only, by design. 4,882 accounting enterprises — the denominator, never the list. |
| `cvrapi.dk` and similar third-party APIs | 200 | Third-party re-publisher, lookup-shaped rather than filterable, and bulk harvesting is against its terms. Excluded by the *official registries only* rule. |

## Two smaller routes, if the email stalls

Both are human-operated and neither is automatable from here — noting them so
the choice is visible rather than to recommend them:

- **CVR self-service extract.** A free account on `cvr.dk` gives the advanced
  search on `datacvr.virk.dk` a filter on branchekode and employee interval,
  and an extract of the result. A person can run it in a browser. The output
  would still need mapping into the Lead JSON.
- **Municipality-by-municipality narrowing.** `list-dk --kommune` exists
  because the full-country query is the one most likely to be throttled. It
  changes nothing about the credential requirement.

## What is already built and waiting on this

- `engine/cvr.py` — query, paging, record mapping, advertising-protection drop.
- `engine/cli.py list-dk` — harvest, MX enrichment, provider split, Lead JSON.
- `tests/test_cvr.py` — 11 offline tests over the mapping and the band logic.

**Unexercised against a live response.** The Vrvirksomhed field paths come from
the published CVR schema; the only live behaviour confirmed from here is the
401. First run with real credentials should be a single municipality, with the
raw hits eyeballed before trusting the counts.
