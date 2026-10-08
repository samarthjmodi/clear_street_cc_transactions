# Revenue curves: what a card earns each year as it ages

> **Superseded working notes.** The submitted analysis is the root `README.md`; figures here were not updated and may not match it. The plots they referenced were removed from the submission.

## Summary

- **A card earns the most in its first year, then declines slowly.** A credit card earns $400 in year 1, $340 in year 5 and $311 in year 8. A debit card earns $97, $82 and $79. Prepaid earns $0 throughout under the rate card.
- **The decline is gradual and flattens out.** Following the same cards for eight years, credit falls about 3% a year and debit about 3% a year. On the longest view, credit flattens at about $310–$340 a year from year 8 to year 17, and debit at about $80–$85.
- **About two-thirds of the decline comes from cards ending, and a third from lower spending.** About 2% of cards end each year when they reach their expiry date, so 86% are still open after eight years. Cards that are still open earn almost as much as in year 1: credit $362 in year 8 against $388, and debit $92 against $100.
- **An open card is a used card.** In every year, the share of cards with any purchase equals the share still open. Cards don't go dormant; they end at expiry.
- **When a card ends, the customer usually stays.** 98% of customers are still transacting a year after one of their cards expires. Customers are no more likely to open a new card around an expiry than at any other time, so spending moves to the cards they already hold. The card-level curve therefore overstates how much revenue we lose per customer.
- **First cards start high and decline faster.** A customer's first credit card earns $737 in year 1 and $497 in year 7 (−33%). An extra credit card goes from $364 to $293 (−20%). As customers add cards, spending moves off their first card.

**Rule of thumb for valuing a card:** five-year revenue is about 4.6 times first-year revenue. A credit card opened earns about $1,830 over its first five years, and a debit card about $440.

## Method

- **Tenure year k** is months `[open + 12(k−1), open + 12k)` after the card's open month. Only full card-years inside the transaction window (January 2010 to October 2019) are used.
- **Card end.** Cards almost never transact after their `expires` month (0.0006% of transactions). A card-year that starts after expiry counts as closed and earns $0. The Amex fee stops at expiry.
- **Revenue** is interchange at the Finance rate card plus the Amex $95 annual fee for months the card is open. "Per card opened" keeps closed cards in the average at $0; "per card still open" excludes them.
- **Customers with no transactions at all are excluded**, leaving 4,514 cards and 33,337 card-years.
- **Spending per card is flat by calendar year** ($172–$187 per card a year from 2010 to 2018), so later tenure years aren't inflated by a general rise in spending.
- **Three views:**
  - **Opened 2010 or later:** 10,296 card-years. Every year since opening is visible, but later years only include the earliest-opened cards.
  - **Balanced:** the same cards followed for eight years, for cards opened January 2010 to November 2011 (262 credit, 405 debit, 63 prepaid). The shape isn't affected by which cards are in each year.
  - **Long run:** all cards, including those opened before 2010, using their card-years from 2010 on. This extends the curve to about 20 years, but each year mixes cards opened at different times.
- **95% confidence intervals** resample customers, because one customer's cards move together.

## Results

![Revenue curves by card age](../../../../plots/q1_card_revenue_curves.png)

### Credit and debit cards opened in 2010 or later

| Card age (year) | Credit cards | Credit: revenue per card opened (95% CI) | Debit cards | Debit: revenue per card opened (95% CI) | Still open (credit / debit) |
|---:|---:|---:|---:|---:|---:|
| 1 | 513 | $400 ($371–$435) | 953 | $97 ($92–$102) | 100% / 100% |
| 2 | 497 | $378 ($348–$410) | 914 | $91 ($85–$96) | 96% / 96% |
| 3 | 474 | $363 ($332–$397) | 860 | $88 ($83–$93) | 94% / 93% |
| 4 | 447 | $352 ($322–$387) | 794 | $84 ($79–$89) | 91% / 91% |
| 5 | 406 | $340 ($310–$371) | 726 | $82 ($77–$88) | 90% / 89% |
| 6 | 364 | $338 ($306–$377) | 621 | $82 ($76–$88) | 87% / 88% |
| 7 | 324 | $313 ($283–$345) | 505 | $83 ($76–$90) | 86% / 88% |
| 8 | 262 | $311 ($276–$354) | 405 | $79 ($72–$86) | 86% / 86% |
| 9 | 164 | $288 ($248–$330) | 236 | $83 ($73–$92) | 84% / 85% |

### Same cards followed for eight years

| Card age (year) | Credit: per card opened | Credit: per card still open | Debit: per card opened | Debit: per card still open | Still open (credit / debit) |
|---:|---:|---:|---:|---:|---:|
| 1 | $388 | $388 | $100 | $100 | 100% / 100% |
| 2 | $363 | $375 | $95 | $98 | 97% / 97% |
| 4 | $334 | $363 | $88 | $93 | 92% / 95% |
| 6 | $316 | $356 | $83 | $92 | 89% / 89% |
| 8 | $311 | $362 | $79 | $92 | 86% / 86% |
| **Change, year 1 to 8** | **−20%** | **−7%** | **−21%** | **−8%** | |

Of the 20% drop in credit revenue per card opened, 14 points come from cards ending and about 7 from lower spending on open cards. Debit splits the same way.

### Long run (all cards, card-years from 2010 on)

| Card age (year) | 1 | 3 | 5 | 8 | 10 | 12 | 15 | 17 | 20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Credit: per card | $400 | $382 | $343 | $317 | $313 | $313 | $335 | $315 | $309 |
| Debit: per card | $97 | $91 | $88 | $82 | $82 | $82 | $85 | $85 | $69 |
| Still open (credit) | 100% | 95% | 89% | 85% | 83% | 82% | 83% | 81% | 83% |

- **After about year 8 the curve is flat.** Credit stays around $310–$340 and debit around $80–$85 until about year 17.
- **Survival also levels off** at 81–84% from year 10 to year 17. Most expiries happen in the first decade.
- **Beyond year 17 the samples are small** (fewer than 150 credit cards a year) and the intervals are wide.

### First card versus extra card

![First card versus extra card](../../../../plots/q1_card_revenue_curves_first_vs_extra.png)

| Card age (year) | Credit, first card | Credit, extra card | Debit, first card | Debit, extra card |
|---:|---:|---:|---:|---:|
| 1 | $737 | $364 | $202 | $87 |
| 3 | $618 | $335 | $167 | $80 |
| 5 | $571 | $316 | $143 | $75 |
| 7 | $497 | $293 | $142 | $76 |
| Cards in year 1 | 49 | 464 | 83 | 870 |

- **First cards stay worth more than extra cards at every age,** but the gap narrows. First credit cards fall 33% by year 7, against 20% for extra cards.
- **The faster decline is spending moving to newer cards.** Purchase volume on first credit cards falls from $43.9k to $29.0k by year 7 while the cards stay open: 94% are still open in year 7.
- **The first-card samples are small:** 49 credit and 83 debit cards in year 1.

## What this means for Q1

- **A card's value is mostly front-loaded but long-lived.** Year-1 revenue is a good guide to later years. It falls slowly, about 3% a year, and flattens after about eight years.
- **Card-level decline isn't customer loss.** Cards end at expiry, but customers stay and move spending to other cards. Customer-level value is the right measure for "worth having": in Q1_FINDINGS.md, Debit customers' value rises over their first three years as they add credit cards.
- **The curves support the segment ranking.** Credit cards earn about four times what debit cards earn at every age, so a credit customer's lead doesn't erode over time.

## Limitations

- **Expiry is treated as the card's end.** The data has no account-closure date. Because cards don't transact after expiry and aren't systematically replaced, this is the best proxy available.
- **Cards that ended before the customer file was taken may be missing.** The card file is a February 2020 snapshot, so the true closure rate may be higher than shown.
- **Later years come from earlier cohorts.** In the "opened 2010 or later" view, year 9 only includes cards opened in 2010. The balanced view controls for this up to year 8.
- **Revenue only:** no costs, and no revolving interest.

## Files

| File | Contents |
|---|---|
| `card_years.csv` | One row per card per tenure year: revenue, Amex fee, open and active flags |
| `curve_opened_2010_plus.csv`, `curve_balanced_8y.csv`, `curve_long_run.csv`, `curve_first_vs_extra.csv` | Curves with confidence intervals, survival and revenue per open card |
| `curve_notes.json` | Counts, card life to expiry, the replacement check |
| `src/q1_card_revenue_curves.py`, `tests/test_q1_card_revenue_curves.py` | Code and tests |
