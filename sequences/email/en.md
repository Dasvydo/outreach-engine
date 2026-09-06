# Email sequence, English, market `global` only

Four touches over twelve days, sent through Instantly.

## This sequence is not available in Denmark, and that is enforced in code

Danish marketing law is stricter than the rest of the EU on unsolicited
commercial email. Until Dovy confirms otherwise in writing, **no Danish address
goes into Instantly.** That is not a convention anyone has to remember. It is a
hard filter inside `load_instantly.py`, it runs before the payload is built, it
cannot be turned off by a flag, and `tests/test_danish_exclusion.py` fails the
build if anyone weakens it.

Denmark gets LinkedIn and phone instead. See `sequences/linkedin/da.md` and
`sequences/phone/da.md`. Lithuania gets email only once addresses are verified,
which is why this file is English and `global` only.

## Timing

Sending domains need two to three weeks of mailbox warmup, so this sequence
cannot start before roughly **22 September 2026**. LinkedIn and phone start
8 September in all three markets. Weeks 1 and 2 of the A/B read LinkedIn across
three markets. Email joins for `global` in week 3.

## UTM

Template, exactly as the campaign spec sets it:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

This is the email channel, so `utm_source` and `utm_medium` carry the channel
that actually sent the click. Campaign and content are untouched, and
`{market}_{step}` is filled the same way everywhere:

```
https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_1
https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_2
https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_3
https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_4
```

Leaving `utm_source=linkedin` on an email would put every email click in the
LinkedIn column of Batch B's `get_channel_funnel`, which is the one number this
whole A/B exists to read.

## Variables

Instantly fills these from the CSV `load_instantly.py` builds. Only three are
used, and every one of them has a fallback written into the copy:

- `{{firstName}}` falls back to nothing, and the sentence still reads
- `{{companyName}}` never empty, it is the ledger's own company name
- `{{segmentOpener}}` the segment line from `config/hooks.yaml`

A worked example of touch 1, fully rendered for an insurance broker, sits at the
bottom of this file so nobody has to imagine what it looks like.

## Facts this copy is allowed to use

$89 per seat per month plus $500 setup covering the workshop, onboarding and
setup. Teams of 10 and up. Free two week pilot with the workshop and setup
included, billing starts on day 14. Inside Outlook. Never auto sends. Runs in
Europe.

The ROI figures (around 9x, about 400 euro a month, payback in roughly 40 days)
are MODELLED, not measured. They come from a model that assumes a fixed amount
of time saved per person per day, priced at a team's own cost. No customer has
reported them and nothing has been measured. The copy may use them as a worked
example, and only when it says so in the same breath. Never write that firms
are saving, seeing, getting or reporting them.

No testimonials and no named pilots exist. Do not invent either.

---

## Touch 1. Day 0.

**Subject:** The week before the deadline at {{companyName}}

**Preview text:** the same four questions, every year

> Hi {{firstName}},
>
> {{segmentOpener}}
>
> Most firms answer them the same way every time, from memory, one person at a
> time. That is the part that does not scale, and it is the part hiring does not
> fix quickly.
>
> We take your firm's own answers, the fee schedule, the deadlines, the document
> checklists, the policy wording, and put them into Outlook. When someone opens
> a client email, the reply is already drafted in your firm's own words. They
> read it, change what they want, and send. Nothing goes out on its own.
>
> Teams of ten and up, and it runs in Europe.
>
> Worth fifteen minutes?
>
> Dovy

---

## Touch 2. Day 3.

**Subject:** Re: The week before the deadline at {{companyName}}

> {{firstName}}, one thing I left out of the last message.
>
> We build the knowledge base for you. Most tools hand you an empty upload box
> and wish you luck, which is why most firms never finish setting them up. The
> $500 setup fee is that work: a workshop with your team, the build, and the
> onboarding.
>
> The first two weeks are free and include all of it. If it is not drafting
> replies you would actually send by day 14, you stop and pay nothing.
>
> Dovy

---

## Touch 3. Day 7.

**Subject:** The numbers, since you did not ask

> {{firstName}},
>
> I will keep this one to the arithmetic, and I will be straight that it is a
> model, not a customer number. Nobody has measured this yet.
>
> Assume each person gets about twenty minutes a day back from routine client
> email. For a team of ten that models out to somewhere around 400 euro a month.
> Against $89 a seat and the one off $500 setup, that would be roughly 9x and
> the setup paying for itself in about 40 days. Your own numbers will replace
> the assumption in the first two weeks.
>
> I would rather show you than send you a spreadsheet:
> https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_3
>
> Dovy

---

## Touch 4. Day 12. Last one.

**Subject:** Closing the loop

> {{firstName}}, last one from me.
>
> Three things worth knowing even if the answer is no:
>
> It never leaves Outlook, so nobody has to learn a new app or change where they
> work. It never sends anything by itself, a person always reads the draft
> first. And it runs on European servers, which matters more to most of our
> buyers than anything else on this list.
>
> If you want to see it later, the page stays up:
> https://teams.doviloop.dev/?utm_source=instantly&utm_medium=email&utm_campaign=teams_q4&utm_content=global_4
>
> Otherwise I will stop here. Thanks for the time.
>
> Dovy

---

## Worked example, touch 1, rendered

Insurance broker, first name present. This is what actually lands:

> **Subject:** The week before the deadline at CoverLink Insurance
>
> Hi Sarah,
>
> A claim goes in and the client wants an update every couple of days, in
> writing, while the carrier takes its time. Renewals do the same thing every
> quarter.
>
> Most firms answer them the same way every time, from memory, one person at a
> time. That is the part that does not scale, and it is the part hiring does not
> fix quickly.
>
> We take your firm's own answers, the fee schedule, the deadlines, the document
> checklists, the policy wording, and put them into Outlook. When someone opens
> a client email, the reply is already drafted in your firm's own words. They
> read it, change what they want, and send. Nothing goes out on its own.
>
> Teams of ten and up, and it runs in Europe.
>
> Worth fifteen minutes?
>
> Dovy

## Rules for whoever runs this

1. Any reply at all stops the sequence. `sync_replies.py` does this
   automatically once it has an API key.
2. An `unsubscribe` classification suppresses the contact everywhere, across
   every channel and every market, permanently. Not just in Instantly.
3. Bounce rate stays under 1 percent. Verify twice before loading.
4. Three mailboxes per sending domain, no more.
5. Do not send touch 3 to anyone who clicked touch 1. Call them instead.
