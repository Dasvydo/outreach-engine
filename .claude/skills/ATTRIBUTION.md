# Attribution

The four skills in this directory are adapted from **AI Sales Team for Claude Code**
by Zubair Trabzada, MIT licensed.

<https://github.com/zubair-trabzada/ai-sales-team-claude>

```
MIT License

Copyright (c) 2026 Zubair Trabzada

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## What changed, and why

| Source | Here | Reason |
|---|---|---|
| `skills/sales-objections` | `outreach-objections` | Feel-Felt-Found replaced with **LAER** (from the upstream `templates/objection-playbook.md`, which no upstream skill loaded). Feel-Felt-Found is an English idiom with no idiomatic Danish equivalent; LAER is a four-step procedure and translates. |
| `skills/sales-followup` | `outreach-followup` | Cold-sequence scenarios dropped — `engine/sequence.py` owns cold. Kept only post-reply scenarios. |
| `skills/sales-prep` | `outreach-call-prep` | Research phase cut: it fetched 9 hardcoded English URL paths that miss `/om-os`, `/medarbejdere`. Firm facts now come from the Lead JSON, which is registry-sourced. |
| `skills/sales-proposal` | `outreach-proposal` | **ROI-math sections removed entirely.** `docs/ICP-BRIEF.md` records a prospect rejecting that lever outright: *"what do I make per hour? That's not the issue."* Case-study sections replaced with the 30-day guarantee — there are no customers yet and inventing one is a fireable error. |

Not ported: `sales-prospect`, `sales-research`, `sales-contacts`, `sales-competitors`,
`sales-icp`, `sales-report`, `sales-report-pdf`, `sales-outreach`. They duplicate or
contradict `engine/` — see the PR that added this directory.

No upstream Python was ported. Both upstream fetchers disable TLS verification
(`ssl.CERT_NONE`), and the two scoring scripts are invoked by no upstream skill.
