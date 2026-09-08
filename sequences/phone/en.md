# Phone, English, market `global`. Optional channel.

One page. Read it before you dial, not while you dial.

Denmark is the market where phone replaces cold email, so `sequences/phone/da.md`
is the primary version of this script and this one is the optional English
translation for `global`. Use it when a good account goes quiet after LinkedIn
step 4, or when someone clicks the landing page and does not book.

## UTM

Template, exactly as the campaign spec sets it:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

A call is not a click. The link lives in the follow up email you send afterwards
to someone you just spoke to, so source and medium carry the channel that
actually sent the click. Campaign and content are unchanged:

```
https://teams.doviloop.dev/?utm_source=phone&utm_medium=call&utm_campaign=teams_q4&utm_content=global_1&source=outreach
```

The step number is which call in the run you are on. First call is `global_1`,
follow up call is `global_2`.

## Before you dial

Spend two minutes on the company. You need one concrete thing in your head: the
segment, a rough size, and something from their own website. Never dial cold
blind.

Call between 9 and 11 or between 1 and 3 in their timezone. Not Friday afternoon.
For US accounts the evening slot works too, which is why the booking page runs
09:00 to 17:00 CET plus US evenings.

You are not selling on the phone. You are booking fifteen minutes.

---

## The opener

Say who you are, why you are calling, and give them a way out immediately.

> Hi, this is Dovy from DoviLoop. I work with accounting firms on the client
> email that piles up before a deadline. Quick question and then I will let you
> go. Do you have thirty seconds?

Segment swaps for the middle sentence:

- **Insurance:** I work with brokers on the client email around claims and
  renewals.
- **Property and housing admin:** I work with property administrators on the
  tenant email that fills the office inbox.

If they say yes, ask the question. One question, not three.

> How many people there are writing client email on a normal day?

Under ten, thank them and hang up. That is not a loss. The offer starts at ten
seats and they have not earned five minutes of a pitch they cannot use.

Ten or more:

> Then you know this already. It is the same five questions every week and every
> one of them still needs a written answer. We put your own answers into Outlook,
> so the reply is already drafted when someone opens the message. Your wording.
> Nothing sends until a person reads it.
>
> It is not something I can show you over the phone. Do you have fifteen minutes
> next week?

Then stop talking. Let them answer.

---

## The three brush offs you will get

### 1. "We do not have time right now."

True, and usually the whole point. Do not push.

> That is actually why I called, but I get that it does not help today. Should I
> call back in three weeks once the deadline is behind you? I will not send you
> anything in the meantime.

Then do exactly that. Put it in the calendar while you are on the call.

### 2. "We already use something" or "we handle that ourselves."

Do not argue. Ask about it.

> Fair enough, what are you using? ... Right, that covers a chunk of it. The part
> people usually find missing is that the answers have to be yours, your fees,
> your deadlines, your wording, and that it sits inside Outlook where they
> already work. That is the part we do. Have you got that solved?

### 3. "Send me something."

Often means no. Treat it as a real answer and make it cheap for them.

> Happy to. I will send one email with a link to a page that explains it in two
> minutes, and a clip that shows it inside Outlook. If you like it after that,
> you book a time on the page yourself. If I do not hear back I will leave it
> there. Fair?

Send that email the same day with the link above. One email. Not three.

---

## If they ask the price

Say it. Never dodge a price question on the phone, it costs more trust than the
number costs.

> $89 per seat per month, and a $500 setup fee that covers the workshop, the
> setup and onboarding. Teams of ten and up. The first two weeks are free and
> include all of it, so you see it working before anything is charged.

## If they ask who else uses it

There are no named customers and no testimonials yet. Do not invent either.

> I do not have names I can use yet, and I would rather tell you that than make
> something up. What I do have is a model, not a customer number: assume about
> twenty minutes a day back per person, and a team of ten works out to around
> 400 euro a month, with the setup cost back in about 40 days. That is an
> assumption until the pilot replaces it with your own figures.

Say the word model. Never say the figures were measured, seen or reported by
anyone, because they were not.

## After the call

Write it into `campaign.touches` with channel `phone`, the step number and the
outcome, the same day. If you do not, the call did not happen as far as the A/B
test is concerned.
