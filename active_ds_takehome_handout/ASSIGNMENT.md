# Take-home: Growth Data Science

**Time expectation:** ~5 hours of focused work. You have 5 days to return it. We would
rather see five hours of good judgement than twenty hours of polish. If you find yourself
going long, stop and write down what you would have done next.

**What happens after:** you will walk us through your own submission in a 30-minute
session. We will not read it cold and grade it in silence — we will ask you to defend
your choices. The detail behind your headline numbers matters as much as the numbers.

## The situation

You have joined the data team at a consumer card business. The company issues credit,
debit, and prepaid cards, makes money when customers transact, and spends a few million
dollars a year acquiring customers across roughly ten channels.

Your new VP of Growth sends you this on day three:

> We're planning next year's acquisition budget and I need to know where to put it.
>
> A few things I believe, which you should feel free to confirm or correct:
>
> 1. **Microsoft Ads is our most efficient channel.** The platform reports a CAC around
>    $770, which is far better than anything else we run.
> 2. **Apple Search Ads is a money pit.** Spend keeps climbing and I can't see the return.
> 3. **Our affiliate programme is basically free growth**, so we should scale it hard.
>
> What I actually need from you:
>
> 1. **Who are our customers, really?** I want to talk about them in terms of segments,
>    and I want to know which segments are worth having.
> 2. **When does a new customer become a *real* customer — and when do I know I'm losing
>    one?** Marketing counts an approved application. Finance counts the first
>    transaction. I don't think either is right. I also don't have a way to tell when a
>    customer has quietly gone away, and I'd like one, broken down by the segments in (1).
> 3. **Which channels bring us the good segments, and which bring us tyre-kickers?** And
>    what should I do with next year's budget?
> 4. **What was the incremental impact of the brand campaign we ran in March 2019?** The
>    CMO keeps citing it.
>
> Give me two pages I can take to the exec team, plus whatever backup you think I'll get
> asked about. I'm not technical, but the people who challenge me are.

## The data

Nine files, in this directory. The behavioural data comes from a public dataset. The
acquisition layer is synthetic, generated to resemble our production marketing stack.

**We have not cleaned any of it for you.** Treat it exactly as you would a fresh extract
handed over by a partner team: assume nothing about its quality until you have checked.

### Behaviour

| File | Rows | Grain |
|---|---|---|
| `users_data.csv` | 2,000 | one row per customer — demographics, income, credit score, geo |
| `cards_data.csv` | 6,146 | one row per card — type/brand, credit limit, `acct_open_date` |
| `transactions_data.csv` | 13,305,915 | one row per transaction — `date`, `amount`, `merchant_*`, `mcc`, `errors` |
| `mcc_codes.json` | 109 | merchant category code → description |
| `train_fraud_labels.json` | 8,914,963 | transaction id → `Yes`/`No`. Fraud is **not** the focus of this exercise |

### Acquisition

| File | Rows | Grain |
|---|---|---|
| `marketing_touchpoints.csv` | 1,508,860 | one row per ad/site touch — `anonymous_id`, `client_id`, `touch_ts`, `channel`, `utm_*`, `device` |
| `channel_spend.csv` | 27,378 | one row per day × channel × campaign — `spend`, `impressions`, `clicks`, `platform_reported_conversions` |
| `account_signups.csv` | 1,588 | one row per account opened from 2016 on — exact `signup_ts`, plus a `self_reported_source` survey answer |
| `revenue_assumptions.csv` | 7 | our finance rate card — interchange, APR, fees |

On `revenue_assumptions.csv`: it is what Finance gave us, and it is not complete. Where it
does not cover a case you need, make a defensible assumption and say so.

`transactions_data.csv` is 1.2GB. Read it in a way that will not exhaust memory.

## What we're looking for

Answer the VP's four questions. That is the whole assignment — there is no separate task
list.

Two things worth calling out, because they are where submissions usually separate:

**On value.** Deciding which segments are "worth having" requires you to decide what a
customer is worth to *us*. Note that the amount a customer spends is not the same thing as
our revenue. State your revenue model and its weak points.

**On leading indicators.** Some behaviours correlate beautifully with long-term value but
cannot be used to predict it. We are interested in whether you can tell the difference.

And where the data cannot answer one of her questions, say what you would need to
instrument in order to answer it, rather than stretching what you have.

*Optional, not counted toward the time budget:* the fraud labels are in the data. If
anything about them changes how you read a segment or a channel, mention it. Skip it
otherwise.

## Deliverables

Submit a **git repo** (private is fine) or a zip, with `README.md` at the root. We read
submissions on GitHub, so it needs to render there.

```
your-submission/
├── README.md          your report - the primary deliverable
├── plots/             PNGs referenced inline from README.md
├── src/               SQL / Python / dbt - whatever you'd actually use
└── tests/
```

`README.md` must contain these level-2 headings, in this order. Write freely within them:

1. **`## Summary`** — roughly two pages, non-technical, leads with what you would *do*.
   This is the part the VP takes to the exec team.
2. **`## Key numbers`** — a table of your headline figures: CAC, customer value, and
   customer counts by channel and by segment. We compare these across candidates, so put
   them somewhere we can find them.
3. **`## Findings`** — one subsection per VP question, with the detail and plots behind
   the summary. This is what we'll dig into during the walkthrough, so don't thin it out
   to keep the report short.
4. **`## Assumptions and limitations`** — every assumption you had to make, every place
   the data let you down, and anything you found in it that we should know about. Be
   specific: "the data was messy" tells us nothing.
5. **`## How to run`** — how we reproduce your numbers.

**On plots:** we want them, and they should be embedded in `README.md` as relative image
links (`![...](plots/name.png)`) so they render on GitHub. **PNG or SVG only** — no
interactive HTML, and no plots that live only inside a notebook. A handful of plots that
each make a point beats a gallery.

Notebooks are fine for your own working, but the deliverable is the markdown. If you work
in a notebook, export what matters.

## Using AI

**AI assistance is welcome and expected.** We use these tools daily and we are not
interested in testing whether you can work without them. Use whatever you like.

Two things we do ask:

- **Note where you used it substantially**, in a short section at the end of `README.md`.
  This is not held against you — we would rather know how the work was produced.
- **Make sure it is yours.** You will present this submission and defend it live, without
  your tools, in a 30-minute session. We will ask why you made specific choices and what
  the weaknesses of your own submission are. An agent can write an analysis you cannot
  explain; that shows up immediately in the walkthrough and it is the most common way
  strong-looking submissions fail.

There is an `AGENTS.md` in this directory describing the required output format. If you
are using a coding agent, point it there and it should produce the right structure.

## How we assess it

- Whether your conclusions are correct, and whether your code supports them
- Whether you surfaced the ambiguity in the problem rather than answering cleanly past it
- Whether you can tell a leading indicator from a consequence, and a correlation from a cause
- Whether the summary would survive contact with an executive
- Code and model quality, including tests where a silent error would change a conclusion

A tidy answer that confidently reports the wrong number will score below a partial answer
that shows its working and flags what it could not resolve.

## Practicalities

- Any language, library, or tooling.
- If you hit something genuinely blocking, email us. Asking a good question is not a
  penalty.
