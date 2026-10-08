# The VP's three beliefs about channels

Backup detail for the three priors the VP asked us to confirm or correct. The Q3 answer that uses this evidence (good segments vs tyre-kickers, and next year's budget) is in [`CHANNEL_QUALITY.md`](CHANNEL_QUALITY.md). Each section below gives the verdict first, then the evidence.

Sources: `channel_spend` (Apple Search Ads' tripled rows removed), `marketing_touchpoints` and `account_signups`, with `cards_data` used to tell new customers from existing ones. Spend runs from January 2016 to February 2020.

## Belief 1: "Microsoft Ads is our most efficient channel. The platform reports a CAC around $770, which is far better than anything else we run."

**Verdict: the number is wrong, but the instinct is partly right.** The $770 comes from Microsoft's own conversion count, which looks broken. On our own records, Microsoft costs about $2,200 per new customer, second to Google branded search. On first touch it is the cheapest channel, level with brand within the uncertainty, which makes it the natural channel to test growing.

![Microsoft Ads spend vs platform-reported conversions](../../../plots/belief1_microsoft_spend_vs_platform_conversions.png)

- **The claim rests on platform-reported conversions, not conversions we observed.** The $770 is Microsoft spend divided by the conversions Microsoft's ad platform says it drove.
- **Spend tripled while reported conversions stayed flat, until two odd months.**
  - Monthly spend grew steadily from about $7.0k in January 2016 to about $21.5k in January 2020.
  - Reported conversions never exceeded 26 a month from 2016 to 2019, and 29 of those 48 months had none.
  - Then they jumped to 293 in January 2020 and 436 in February 2020.
  - That looks like an instrumentation issue, not a change in performance: spend and ad activity were flat from December 2019 to January 2020.
- **Those two months create the $770.** Over the whole period, cost per reported conversion is about $800. Without January–February 2020, it is about $4,000.

| Period | Spend | Platform-reported conversions | Cost per reported conversion |
|---|---:|---:|---:|
| Jan 2016 – Feb 2020 (the "$770" basis) | $719,540 | 897 | **$802** |
| Jan 2016 – Dec 2019 (excluding the last 2 months) | $677,128 | 169 | **$4,007** |
| Jan – Feb 2020 only | $42,412 | 728 | $58 |

- **The right measure comes from our own attribution: new customers whose journeys Microsoft touched.**
  - In January–February 2020, splitting each customer's credit evenly across the channels in their journey, Microsoft costs about **$2,200 per new customer**. That is almost 3× the platform's figure.
  - Google branded search costs about $700, so Microsoft is second, not first.
  - Crediting each customer to the first channel they saw, Microsoft is cheapest: $1,368 (95% range $1,010–$2,020) against brand's $1,644 ($1,281–$2,291). The ranges overlap, so the two are effectively level at starting journeys.

**What to do:**

- **Don't move budget into Microsoft on the $770,** but do test growing it, with a holdout, on our own cost figures.
- **Ask ad operations** what Microsoft counts as a conversion, and why the count jumped in January 2020.
- **Report channel acquisition costs from our own signups,** not from platform counts.

### Backup: detail behind belief 1

**Why the platform count looks like over-counting:**

- **More conversions than new customers.** Microsoft claims 728 conversions in January–February 2020, more than the 385 new customers we acquired from every channel combined. It is also over three times the 220 signups Microsoft touched at all.
- **Impossible days.** On 38 of those 60 days, Microsoft's daily count was higher than our total new customers that day. On 10 days it was higher than every signup we recorded, new and existing.
- **The jump isn't only Microsoft's.** Every platform's count and our own recorded signups rise in January 2020:
  - Apple: at most 3 a month before, then 26 and 45.
  - Google branded search: at most 4, then 70 and 85.
  - Meta: at most 6, then 108 and 106.

  Microsoft's jump is the largest, and it is the only one claiming more conversions than we have customers.

**Cost per new customer, January–February 2020, by attribution rule:**

| Attribution rule | Microsoft new customers | Microsoft cost per new customer | Google branded search |
|---|---:|---:|---:|
| Last touch | 9 | $4,712 | $470 |
| First touch | 31 | $1,368 (95% CI $1,010–$2,020) | $1,644 ($1,281–$2,291) |
| **Linear: credit split evenly across the journey (headline)** | **19.3** | **$2,197** (95% CI $1,795–$2,806) | **$699** |
| Any touch: every channel in the journey gets full credit | 89 | $477 | $262 |

- **Only January–February 2020 can be measured.** Earlier periods have too few recorded new customers to give a believable cost; 2019 implies about $281k per new customer across paid channels.
- **Only first cards count.** Existing customers' extra cards are excluded.
- **The ranking is stable.** On linear attribution, branded search is cheapest in 100% of 4,000 resamples, and Microsoft is second in 87%. Google's branded and non-branded search together cost about $1,270.
- **Microsoft supports journeys rather than closing them.** It appears in 23% of new-customer journeys but was the last touch for only 9. Google branded search is present in 80% of the journeys Microsoft appears in.
- **The true cost is probably higher.** These journeys started in mid-November 2019. Matching spend to that window raises Microsoft to about $3,800, and branded search to about $1,200.

**Caveats:**

- **Attribution isn't causation.** Only a holdout test, such as pausing Microsoft in some regions or weeks, shows what it adds.
- **The measurable window is two months,** during an unexplained surge in signups, so treat the cost levels as indicative.
- **Campaigns can't be separated.** Spend is split exactly equally between Microsoft's branded and generic campaigns every day, so their performance can't be told apart.

## Belief 2: "Apple Search Ads is a money pit. Spend keeps climbing and I can't see the return."

**Verdict: partly right.** The return is poor: Apple is our most expensive paid channel per new customer. But its spend is climbing no faster than any other channel's, and the raw spend file triple-counts it, so any report built on that file shows Apple at three times its real cost.

![Apple Search Ads spend and cost per new customer](../../../plots/belief2_apple_spend_and_cost_per_customer.png)

- **Spend is climbing, but so is every channel's.**
  - Apple went from about $9.3k a month in January 2016 to about $28.6k in January 2020 (3.1×). Microsoft grew by the same multiple.
  - All six paid channels grew 122–132% from 2016 to 2019.
  - Apple's share of paid spend stayed between 10% and 12.5% every month, about 12% each year. Apple isn't taking a growing share of the budget; the whole budget is growing.
- **The raw spend file counts every Apple row three times.**
  - Raw Apple spend totals $2.78M; the actual figure is $0.93M.
  - In the raw file Apple looks like 29% of paid spend; the real share is 12%.
  - Any dashboard built on the raw table would make Apple look like a much bigger money pit than it is.
- **The return really is poor, on every measure:**
  - **Platform count:** Apple reported 94 conversions in total, $9,872 each. Only 23 were before 2020.
  - **Our attribution:** in January–February 2020, with credit split evenly across each customer's journey, Apple costs about **$8,400 per new customer**. That is the most expensive paid channel, against $700 for Google branded search and $2,200 for Microsoft.
  - **Closing journeys:** Apple was the last touch before signup for only 1 new customer.
- **But Apple tends to start journeys rather than finish them.**
  - If each customer is credited to the first channel they saw, Apple costs about $2,650, in line with Meta ($2,300) and Reddit ($2,600).
  - Cutting it could weaken journeys that other channels go on to close.

| Measure, Jan–Feb 2020 | Apple Search Ads | Google branded search | Microsoft Ads |
|---|---:|---:|---:|
| Spend | $55,703 | $75,604 | $42,412 |
| New customers, credit split evenly | 6.6 | 108.1 | 19.3 |
| **Cost per new customer, credit split evenly** | **$8,404** | **$699** | **$2,197** |
| Cost per new customer, first touch | $2,653 | $1,644 | $1,368 |
| Cost per new customer, last touch | $55,703 (1 customer) | $470 | $4,712 |

**What to do:**

- **Fix the spend reporting first.** Remove the duplicate Apple rows at the source, so the VP and Finance see $0.93M, not $2.78M.
- **Don't cut Apple outright. Test it.** Pause it in some regions or weeks and measure whether new customers fall, including those who later arrive through other channels. Its role as an opener makes a straight cut risky.
- **Don't grow it while the test runs.** On current evidence it is the least efficient paid channel.

### Backup: detail behind belief 2

**How sure is the ranking?**

- **95% CI on Apple's linear cost:** $5,990–$12,786 per new customer.
- **Resampling:** Apple is the most expensive paid channel in 100% of 4,000 resamples.
- **Before 2020:** it was also among the most expensive (about $520k per new customer, ahead of only Reddit), though that period's costs aren't believable on their own.
- **Matching spend to when these journeys began** (from mid-November 2019) raises Apple to about $14,600 per new customer.
- **Touch volume:** Apple needs about 3,500 tracked ad touches per new customer, twice Microsoft's 1,774. Its touches come early, a median of 18 days before signup.

**Is Apple under-tracked?** This is the likely objection: app-store installs are hard to trace.

- **Low link rate:** only 0.07% of Apple's touches can be tied to a customer, against 0.55% for Google branded search. The low rate could reflect weak performance or weak tracking.
- **Survey cross-check:**
  - 48 of the 63 signups who said they found us through the app store do have Apple touches, so tracking isn't missing them wholesale.
  - In January–February 2020, 12 new customers said they found us through the app store. Charging Apple's spend for those months to them gives about $4,600 per customer. That's better than $8,400 but still the worst tier.

**Customer quality and value:**

- Apple-touched new customers skew towards Premium credit (45% of them, against about 22% of all new customers), but that rests on about 8 customers, which is too few to rely on.
- On expected three-year revenue, Apple returns about 22¢ per dollar of spend, against $1.86 for Google branded search and 58¢ for Microsoft. This is before costs, and rests on the same small sample.

**Caveats:**

- **Attribution isn't causation.** Only the holdout test shows what Apple adds.
- **The measurable window is two months,** during an unexplained surge in signups, so treat cost levels as indicative.
- **Campaigns can't be separated.** Apple's spend is split exactly equally between its exact-match and discovery campaigns every day.

## Belief 3: "Our affiliate programme is basically free growth, so we should scale it hard."

**Verdict: wrong as stated.** Affiliates look free only because their cost is missing from the spend table. Depending on how partners are paid, affiliates could be as cheap as our best channel or cost more than the customers they bring are worth. We need the payout data before scaling.

![Affiliate volume and commission scenarios](../../../plots/belief3_affiliate_volume_and_commission_scenarios.png)

- **There is no affiliate spend in the data, which looks like an instrumentation gap.**
  - `channel_spend` has rows for only the six paid channels; affiliate has none in any month.
  - Affiliates are almost never unpaid; partners typically earn a commission per signup or approved card.
  - The affiliate touch log also behaves like a partner's conversion report: every one of its 319 touches belongs to someone who signed up. For paid channels, at most 0.55% of touches lead to a signup. A log that records only conversions is what partners send when they are paid per conversion.
- **The programme is tiny and only started to matter recently.**
  - Affiliate touches never exceeded 7 a month from 2016 to October 2019.
  - They jumped to 89 in December 2019 and 131 in January 2020, then fell to 31 in February. That puts affiliates inside the unexplained January 2020 surge.
- **Affiliates start journeys; branded search finishes them.**
  - Of the 112 new customers in January–February 2020 with an affiliate touch, affiliate was the first touch for 81 and the last for only 11.
  - The next touch after an affiliate is most often Google branded search (97 times) or direct (76). Some of the customers credited to branded search began with an affiliate.
- **About half of affiliate-touched signups come from customers we already have.** In January–February 2020, 123 of the 245 affiliate-touched signups were existing customers adding a card. If partners are paid per signup, roughly half the payout buys cards from people who were already customers.
- **Customer quality is slightly lower, not higher.** Affiliate-touched new customers are expected to bring about $1,281 of revenue over three years, against $1,365 for others. They lean more towards Prepaid (12.8% against 7.9%), but the gap isn't statistically significant.

What the programme costs depends on the commission and on which signups it is paid on. With credit split evenly across each journey, affiliates brought 30.9 new customers in January–February 2020:

| Commission per signup | Paid on every affiliate-touched signup (245) | Paid only when affiliate is the last touch (21) |
|---:|---:|---:|
| $50 | $396 per new customer | $34 |
| $100 | $792 | $68 |
| **$162** | **$1,281, equal to three-year revenue** | $110 |
| $200 | $1,583 | $136 |
| $300 | $2,375 | $204 |

For comparison, Google branded search costs $699 per new customer and Microsoft $2,197. If partners are paid on every signup they touch, any commission above about $160 means affiliates cost more than the customers are worth.

**What to do:**

- **Get the payout data.** Pull commission invoices from Finance or the affiliate network and load them into the spend table as an `affiliate` channel, by partner and month.
- **Pay on new customers only.** Exclude existing customers' extra cards from commissions, and pay on approved accounts, not applications.
- **Don't scale hard yet.** Once the cost is known, grow the partners whose cost per new customer beats branded search, and test incrementality by pausing a partner for a few weeks.

### Backup: detail behind belief 3

**New customers credited to affiliates, January–February 2020, under each attribution rule:**

| Rule | New customers |
|---|---:|
| Last touch | 11 |
| First touch | 81 |
| Credit split evenly (linear) | 30.9 |
| Any touch in the journey | 112 (29% of the 385 new customers) |

**Is the tracking real?** Yes, as far as it goes.

- 154 of the 305 affiliate-touched signups since 2016 said they found us through a "blog or review site".
- 154 of the 244 people who gave that answer have an affiliate touch (63%).
- The log is complete for converters but tells us nothing about partner traffic that didn't sign up, so we can't calculate a conversion rate.

**By partner type** (2020 signups; a signup touched by two partner types counts in both):

| Campaign | New customers | Existing customers' cards | New customers' extra cards |
|---|---:|---:|---:|
| partner_blog | 47 | 45 | 3 |
| comparison_site | 35 | 45 | 4 |
| cashback_portal | 36 | 36 | 3 |

Comparison sites lean most towards existing customers (45 of 84 signups).

**Before 2020,** affiliates touched 60 signups, 47 of them existing customers (78%).

**Break-even commission:**

- Paid on every touched signup, with credit split evenly: about **$162**.
- The most generous reading, giving affiliates full credit for every new customer they touched: about **$586**.
- Both compare commission to three-year revenue, before servicing, credit losses and rewards costs, so the true break-even is lower.

**Caveats:**

- **The commission scenarios are illustrative.** The handout gives no payout rates.
- **Attribution isn't causation.** Only a pause test shows what affiliates add.
- **The window is two months,** during the unexplained surge in signups, and February's drop to 31 touches is unexplained.

## Reproducing these numbers

- `src/vp_hypotheses.py` builds the attribution and cost tables; its outputs are in this folder.
- `src/plot_vp_beliefs.py` draws the charts.
- Tests are in `tests/test_vp_hypotheses.py`.
