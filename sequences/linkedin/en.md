# LinkedIn sequence, English, market `global`

Markets: US, UK, IE, NL. Starts 8 September 2026.

**Cap: 20 connection requests per day.** That is the existing
`linkedin-automator` limit and it is not a suggestion. `build_linkedin_queue.py`
enforces it when it writes the queue.

**Segment-swappable opening lines live in `config/hooks.yaml`.** The accounting
variant is written out in full below because that is the largest segment. The
insurance and housing variants of each line follow it, and they are the same
strings the loader pulls from the YAML. Nothing else in the sequence changes
between segments.

## UTM

Template, exactly as the campaign spec sets it:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

Only step 3 carries a link. For this file `{market}` is `global`:

```
https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=global_3
```

Step 4 links to the reel, not the site, so it carries `global_4`:

```
https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=global_4
```

## Facts this copy is allowed to use

$89 per seat per month plus a $500 setup fee covering the workshop, onboarding
and setup. Teams of 10 and up. Free two week pilot, workshop and setup included,
billing starts on day 14. It works inside Outlook. It never sends anything on
its own. It runs in Europe.

The ROI figures (roughly 9x, around 400 euro a month, payback in about 40 days)
are MODELLED, not measured. They come from a model that assumes a fixed amount
of time saved per person per day. No customer has reported them. The copy may
use them as a worked example, and only when it says so in the same breath.
Never write that firms are saving, seeing, getting or reporting them.

No testimonials and no named pilots exist. Do not invent either. Where social
proof would normally sit, the copy says plainly that there is none yet and
shows the model instead.

---

## Step 1. Connection request. Day 0.

Under 300 characters. No pitch, no link, no ask beyond connecting.

> Hi Sarah, I work with accounting firms on the client email that stacks up in
> the weeks before a deadline. Happy to connect.

Segment swaps for the first sentence:

- **Insurance:** Hi Sarah, I work with insurance brokers on the client email
  around claims and renewals. Happy to connect.
- **Housing and property admin:** Hi Sarah, I work with property and housing
  administrators on the tenant and board email that fills the office inbox.
  Happy to connect.

If the first name is missing, drop it and start at "I work with". Never send
"Hi there".

---

## Step 2. Two days after they accept.

One line on the pain, one question. No link, no product name, no pitch.

> The week before a filing deadline the same four client questions come in over
> and over, and every one of them still needs a written answer.
>
> How does your team handle that stretch at Harper & Co?

Segment swaps:

- **Insurance:** A claim goes in and the client wants an update every couple of
  days, in writing, while the carrier takes its time. Renewals do the same thing
  every quarter. Who ends up writing most of those updates at Harper & Co?
- **Housing and property admin:** Tenants and board members write to the office
  all day, and most of it is the same short list of questions about rent,
  repairs and move outs. How many people at Harper & Co are in that inbox on a
  normal day?

If they answer, stop the sequence and talk to them like a person. The remaining
steps are for silence, not for conversation.

---

## Step 3. Day 5.

The link, framed as the thing that explains it faster than another message.

> Thanks Sarah. I will not turn this into a pitch in your inbox.
>
> Short version: we build your firm's own answers into Outlook, so the reply is
> already drafted when someone opens the message. Their wording, not ours, and
> nothing sends until a person reads it.
>
> I put together a page that explains it faster than I can in a message:
> https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=global_3
>
> If it is not for you, say so and I will leave you alone.

That last line stays in. It costs one sentence and it is the difference between
a sequence and a nuisance.

---

## Step 4. Day 12. Last touch.

Short, one number, a reel, and an actual goodbye.

> Last one from me. Short clip showing what it looks like sitting in Outlook, no
> setup, no new app:
> https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=global_4
>
> One number, and it is a model rather than a customer figure, because nobody
> has measured it yet: assume about twenty minutes a day back per person and a
> team of ten works out to around 400 euro a month, with the setup cost back in
> about six weeks. Two week pilot is free and we do the setup work, so the only
> thing it costs you up front is the workshop afternoon.
>
> If the timing is wrong, it is wrong. Good luck with the season.

Attach the week's English reel to this message. Do not send step 4 without it.
The message is thin on its own and the clip is the whole point of the touch.

---

## Rules for whoever runs this

1. Stop the sequence the moment a human replies anything at all.
2. Never send two steps on the same day.
3. Twenty connects a day, across all three markets combined, not per market.
4. If they look under 10 people when you open the profile, skip them. The offer
   starts at 10 seats and wasting their time is worse than an empty queue.
5. Do not paste the price into a DM. It is on the page.
