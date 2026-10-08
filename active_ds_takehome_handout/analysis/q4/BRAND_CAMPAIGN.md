# Q4: Incremental impact of the March 2019 brand campaign

Backup detail for Findings §4 in the root [`README.md`](../../../README.md): the full method, robustness checks and results. Assumptions specific to Q4 are listed under "Assumptions and limitations" in the README.

**Short answer:** the campaign bought much more brand search exposure, but there's no measurable incremental account or transaction behind it.

| Outcome | Estimate |
|---|---:|
| Accounts | −2 |
| Settled purchases | +1.8%, within what ordinary weeks show once the baseline is checked |
| Interchange | +$519 |

The likely sources of the CMO's claim are the March sign-up count (13, against about 8 in a typical month) and the platform's click numbers. Neither shows lift.

## What "the campaign" is

- **Campaign labels can't identify it.** In `channel_spend.csv` every campaign within a channel is an identical split of the channel's spend and runs every day from 2016 to 2020. `spring_launch` is a Meta label that runs all year. The campaign can therefore only be defined as a burst of channel spend on particular dates.
- **There is only one such burst in 50 months.** Brand search and Meta both doubled on March 4–15, 2019, reaching 2.0× their trailing eight-week average. No other week in any channel from 2016 to February 2020 exceeds 1.18×.
- **The analysis uses three periods of exactly two Monday–Sunday weeks each:**
  - pre: February 18 – March 3
  - campaign: March 4–17
  - post: March 18–31

  The spend burst ends on March 15, so the campaign period includes two normal days.
- **Extra spend during the campaign:**
  - brand search: $13,574
  - Meta: $25,925
  - total: $39,499

  Both were back to normal in the post period (−$135 and −$1,139).

## Method: two difference-in-differences comparisons

The outcomes are recorded at different levels, so there are two designs.

1. **Brand search against control channels, on the same days.** This covers what is recorded by channel: spend, impressions, clicks and site touches.
   - The controls are non-brand search, Apple, Microsoft and Reddit.
   - Meta is excluded because it surged on the same days, so any effect is a joint brand-plus-Meta effect.
   - The estimate is the change in the log gap between brand and the average control. It is identical to a regression with channel and day fixed effects, which a test confirms.
2. **2019 against 2018, for accounts and transactions.** These have no channel dimension, so other channels can't stand in for them. The estimate is the 2019 change from pre to campaign, minus the same change over the same weekdays 364 days earlier.

**How the results are judged: placebo tests.** Each design is rerun on every other six-week window that doesn't overlap the campaign:
- 80 windows for the channel comparison
- 27 for transactions
- 36 for accounts

The p-value is the share of placebo estimates at least as large as the real one. Control channels are also treated, one at a time, as if they were the campaign.

## Results

| Outcome | Comparison | Effect in campaign period | How unusual |
|---|---|---:|---|
| Brand spend | Channels | +85% | p = 0.01 (no placebo window comes close) |
| Brand clicks | Channels | +81% | p = 0.01 |
| Brand site touches | Channels | +2.3% | p = 0.49; placebo 90% range −3.7% to +4.7% |
| Accounts opened | 2019 vs 2018 | −2 (2019: 7 → 6; 2018: 4 → 5) | 90% interval −10 to +6; p = 0.59 |
| Settled purchases | 2019 vs 2018 | +1.8% (+883) | p = 0.07 |
| Purchase dollars | 2019 vs 2018 | +2.4% (+$59.8k) | p = 0.21 |
| Interchange | 2019 vs 2018 | +2.1% (+$519) | p = 0.46 |

Nothing carries into the post period:
- touches −1.6%
- accounts −2
- purchases +0.9%
- interchange −$263

![Brand search vs control channels](../../../plots/q4_brand_vs_controls.png)

### The ads ran, and site traffic didn't respond

- **Brand clicks were well above the controls:** +101% in the first campaign week and +63% in the second, back to baseline the week after. In the six weeks before, the weekly gap stayed between −4% and +6%, so brand and the controls moved in parallel beforehand.
- **Site touches rose by about 5 a day, against about 3,300 extra platform clicks a day.** Placebo windows suggest we would have detected a lift of about 8% or more.
- **The result doesn't depend on the choice of controls:**
  - dropping Microsoft gives +0.8%
  - treating a control channel as if it were the campaign gives between −5.6% and +3.2%
- **Touches don't follow spend in any channel.** The correlation is between −0.12 and +0.03 across 2018–2019, so the touch log may not capture paid traffic at all. Flat touches are uninformative rather than proof of no effect.

![Accounts and transactions vs 2018](../../../plots/q4_yoy_outcomes.png)

### Accounts: no detectable lift, and the March bump is offset by April

- **Counts:** the campaign weeks had 6 accounts, against 7 in the two weeks before. The same weeks of 2018 went from 4 to 5.
- **Signup timestamps can't be trusted at the day level.** A card's first transaction is on the 1st of its open month at the median, while signup times are spread evenly across the month. 94% of cards transact before their own signup timestamp.
- **So I also compared calendar months:**
  - March 2019 (13 accounts) is +5.6 against 2018's pattern.
  - April 2019 (3 accounts) is −6.5.
  - Together that's about −1 over March–April. That looks like timing moving between months, not new demand.
- **All 13 March accounts were existing customers adding a card.** No new customer joined in March 2019 at all.
- **The data can only detect a large lift:** about 14 extra accounts in two weeks, roughly tripling the normal rate. So it can't rule out a modest lift; the top of the range is about 6 extra accounts.

### Transactions: a borderline count that doesn't hold up

Settled purchases rose 1.8% (p = 0.07), but:
- **The 2019 pre period was soft.** The weeks of February 18 and 25 were 1.3% and 1.5% below 2018. The campaign weeks were +0.2% and +0.6%, no better than the weeks of February 11 (+0.5%) and April 15 (+0.4%).
- **Against a January–February baseline, March's lift is only +0.5%.**
- **82% of it (+727 of +883) is on cards more than a month old.** That's existing usage, which a brand search ad wouldn't plausibly move. The cards opened in March added about 156 purchases, worth about $53 of interchange.
- **Interchange shows nothing:** +$519, p = 0.46.

Even at the top of the range, the campaign added at most about 1,650 purchases and $1.5k of interchange over the two weeks. That is about 11 cents per dollar of extra brand spend, or 4 cents per dollar once Meta's extra spend is included. These bounds cover the two campaign weeks only. Any extra account would keep earning afterwards, and this answer doesn't put a value on that.

![Placebo distributions](../../../plots/q4_placebos.png)

**The platform doesn't claim the conversions either.** Brand search reported 1, 0 and 1 conversions in the pre, campaign and post periods.

## What to tell the CMO, and what to instrument

**What I'd tell the CMO:** "We doubled brand search and Meta for two weeks. It bought clicks. We can't see that it bought accounts or transactions, and the account bump in March was given back in April."

**What I'd instrument to measure the next one:**
1. **A geo holdout.** Go dark, or double spend, in matched regions and compare accounts and transactions by region. `users_data` has addresses, so this is possible.
2. **Click IDs** (for example `gclid`) stored at landing and joined to the signup, so paid clicks link to accounts. Touch logging that actually records paid traffic.
3. **Real application and activation timestamps,** to replace signup times that disagree with card activity.
4. **A transaction extract that includes customers acquired after October 2017.** None of them appear in the current file.

## Reproducing these numbers

```bash
.venv/bin/python src/clean_channel_spend.py
.venv/bin/python src/q4_brand_campaign.py
.venv/bin/python -m pytest tests/test_q4_brand_campaign.py tests/test_q4_did.py -q
```

Outputs are in this folder (`step1_*`, `step2_*`, `step3_*`) and `plots/q4_*.png`.
