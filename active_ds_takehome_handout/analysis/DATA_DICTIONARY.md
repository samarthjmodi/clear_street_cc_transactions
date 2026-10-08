# Data dictionary

Reference for the nine source files in `active_ds_takehome_handout/`. Each section covers the grain, keys, coverage, columns, and the quirks found so far. The quirks are things that will silently change a number if you don't handle them.

**Current scope:** the analysis uses only `users_data`, `cards_data`, `transactions_data`, `mcc_codes`, `train_fraud_labels` and `revenue_assumptions`. The three marketing tables (`account_signups`, `marketing_touchpoints`, `channel_spend`) are documented for reference but **not used for now**.

## Overview

| File | Grain | Rows | Key | Coverage | Origin (per brief) |
|---|---|---:|---|---|---|
| `users_data.csv` | Customer | 2,000 | `id` | Snapshot as of Feb 2020 | Public dataset |
| `cards_data.csv` | Card | 6,146 | `id` | Opened Jan 1991 – Feb 2020 | Public dataset |
| `transactions_data.csv` | Transaction | 13,305,915 | `id` | 2010-01-01 – 2019-10-31 | Public dataset |
| `mcc_codes.json` | Merchant category code | 109 | MCC code | n/a | Public dataset |
| `train_fraud_labels.json` | Transaction | 8,914,963 | transaction `id` | Subset of transactions | Public dataset |
| `account_signups.csv` | Signup (= one new card) | 1,588 | `signup_id` | 2016-01 – 2020-02 | Synthetic |
| `marketing_touchpoints.csv` | Ad or site touch | 1,508,860 | `touch_id` | 2016-01-01 – 2020-02-28 | Synthetic |
| `channel_spend.csv` | Day × channel × campaign | 27,378 | (date, channel, campaign), but not unique | 2016-01-01 – 2020-02-29 | Synthetic |
| `revenue_assumptions.csv` | Rate-card item | 7 | `assumption_key` | n/a | Finance |

### How the tables join

```
users_data.id ──┬── cards_data.client_id
                ├── transactions_data.client_id
                ├── account_signups.client_id
                └── marketing_touchpoints.client_id   (only 0.6% of touches carry one)

cards_data.id ──┬── transactions_data.card_id
                └── account_signups.card_id           (one signup per card)

transactions_data.id  ── train_fraud_labels (JSON key)
transactions_data.mcc ── mcc_codes (JSON key)
channel_spend.channel ~ marketing_touchpoints.channel (paid channels only; no direct key)
```

### Coverage across tables

| | Customers |
|---|---:|
| In `users_data` | 2,000 |
| With at least one card | 2,000 |
| With any transaction | 1,219 |
| With a signup, and with touchpoints (the same 994 customers in both) | 994 |
| No transactions because they joined after the data ends (first card Nov 2019 or later) | 387 |
| No transactions despite joining before Nov 2019 (a real gap) | 394 |

---

## `users_data.csv`

**Grain:** one row per customer. **Key:** `id` (0–1999, no gaps). **No nulls.**

| Column | Type | Description | Example |
|---|---|---|---|
| `id` | int | Customer ID. Joins to `client_id` everywhere. | 825 |
| `current_age` | int | Age at the snapshot date (18–101) | 53 |
| `retirement_age` | int | Expected retirement age (50–79) | 66 |
| `birth_year` | int | 1918–2002 | 1966 |
| `birth_month` | int | 1–12 | 11 |
| `gender` | str | Female (1,016) / Male (984) | Female |
| `address` | str | Street address; no city, state or zip | 462 Rose Lane |
| `latitude`, `longitude` | float | 2 decimal places (about 1 km); 12 customers in Alaska or Hawaii | 34.15, -117.76 |
| `per_capita_income` | str ($) | Area-level per-capita income; 15 zeros | $29278 |
| `yearly_income` | str ($) | Labelled as personal income. Mostly derived from `per_capita_income` (see quirks). Median $40.7k. | $59696 |
| `total_debt` | str ($) | Total debt; 102 zeros; median $58.3k | $127613 |
| `credit_score` | int | 480–850; 34 at the 850 cap | 787 |
| `num_credit_cards` | int | Labelled credit cards, but actually the **total cards of all types** (see quirks) | 5 |

**Quirks**
- **The snapshot is February 2020.** Age matches birth year and month for every row at that date and no other. All attributes are measured after the transaction window, so they look ahead in time if used as predictors.
- **`yearly_income` equals 2.039 × `per_capita_income` for 84% of customers.** The rest are mostly retirees (median age 75) on a lower multiple. Treat it as area affluence, not personal income. Eight customers have income under $1,000, minimum $1.
- **`num_credit_cards` counts every card.** It equals the customer's total card count in `cards_data` for 100% of rows, and their credit-card count for only 10%.
- **`credit_score` correlates with nothing:** age 0.00, income 0.01, customer value 0.06. It looks randomly generated.
- **The spike at ages 18–19 (111 customers) is the 2020 cohort.** All of them have signups and none have transactions.
- **Money columns are text with "$".** Strip "$" and "," before parsing.

Full profile: `analysis/deep_dives/users/USERS_DEEP_DIVE.md`.

---

## `cards_data.csv`

**Grain:** one row per card. **Key:** `id`. **Foreign key:** `client_id` → `users_data.id`. Every customer has at least 1 card (mean 3.1, max 9), and there are no orphan cards. **No nulls.**

| Column | Type | Description | Example |
|---|---|---|---|
| `id` | int | Card ID. Joins to `transactions_data.card_id` and `account_signups.card_id`. | 4524 |
| `client_id` | int | Owning customer | 825 |
| `card_brand` | str | Mastercard 3,209 · Visa 2,326 · Amex 402 · Discover 209 | Visa |
| `card_type` | str | Debit 3,511 · Credit 2,057 · Debit (Prepaid) 578 | Debit |
| `card_number` | int | Unique; not needed for analysis | 4344676511950444 |
| `expires` | str (MM/YYYY) | Jul 1997 – Dec 2024 | 12/2022 |
| `cvv` | int | Not needed for analysis | 623 |
| `has_chip` | str | YES 5,500 · NO 646 | YES |
| `num_cards_issued` | int | 1, 2 or 3 (replacement or duplicate cards) | 2 |
| `credit_limit` | str ($) | Limit. Also populated for debit and prepaid cards. | $24295 |
| `acct_open_date` | str (MM/YYYY) | Month the card opened, Jan 1991 – Feb 2020 | 09/2002 |
| `year_pin_last_changed` | int | 2002–2020 | 2008 |
| `card_on_dark_web` | str | "No" for every card, so it carries no information | No |

**Quirks**
- **Open dates are month-level only** (`MM/YYYY`). 309 of 13.3M transactions fall before their card's open month.
- **1,178 cards opened in January–February 2020,** after the transaction data ends. They are the 2020 signups.
- **`credit_limit` on debit and prepaid cards is not a credit line.** Use it only for credit cards when sizing credit.
- **Limits are snapshots.** There is no history of limit changes.
- Credit limit tracks income (rank correlation 0.55) and barely tracks credit score (0.09).

---

## `transactions_data.csv` (1.26 GB)

**Grain:** one row per transaction attempt. **Key:** `id` (7,475,327 – 23,761,870). **Coverage:** 2010-01-01 00:01 to 2019-10-31 23:59. It covers 1,219 customers and 4,071 cards. Read it in chunks.

| Column | Type | Description | Example |
|---|---|---|---|
| `id` | int | Transaction ID. Joins to fraud labels. | 7475327 |
| `date` | str (timestamp) | Minute precision | 2010-01-01 00:01:00 |
| `client_id` | int | Customer | 1556 |
| `card_id` | int | Card | 2972 |
| `amount` | str ($) | Signed amount. Negative values are refunds or reversals. | $-77.00 |
| `use_chip` | str | Swipe / Chip / Online Transaction | Swipe Transaction |
| `merchant_id` | int | Merchant | 59935 |
| `merchant_city` | str | City, or "ONLINE" | Beulah |
| `merchant_state` | str | US state or country name; blank for online | ND |
| `zip` | float | Merchant zip; blank for online and foreign | 58523.0 |
| `mcc` | int | Merchant category code. Joins to `mcc_codes.json`. | 5499 |
| `errors` | str | Blank if successful; otherwise one or more comma-separated reasons | Insufficient Balance |

**Definitions used in the analysis**
- **Settled purchase:** `amount > 0` and `errors` blank. There are 12.43M of these, worth $626M.
- **Refund:** `amount < 0` and `errors` blank, worth $66.8M (about 11% of purchase dollars).
- **Failed attempt:** `errors` not blank. About 1.5% of rows in the first 300k. The most common reasons are Insufficient Balance, Bad PIN and Technical Glitch.
- **Money transfer** (MCC 4829) is the largest category by purchase dollars, at about 8%.

**Quirks**
- **781 of 2,000 customers have no transactions at all.**
  - 387 of them joined after the data ends.
  - 394 joined earlier, and we can't tell whether they never activated or are missing from the extract.
  - It is all or nothing by customer: customers who do appear transacted on every card they opened from 2010 to 2018 in its first year.
- **Missing customers skew younger and more recent.** Among customers who joined before November 2019, 67% of under-30s have no transactions, against 14% of over-60s.
- **Accounts opened before 2010 have no record of their early months,** because the data starts in January 2010.
- **`amount` is text with "$"** and may be negative.
- **Monthly aggregate:** `analysis/q1_scratch/v3/card_month.csv` has spend per card per month, built by `src/build_card_month.py`.

---

## `mcc_codes.json`

**Grain:** one entry per merchant category code. **109 codes.** Structure: `{"5812": "Eating Places and Restaurants", ...}`. Keys are strings, so cast before joining to the integer `transactions_data.mcc`. All 109 codes appear in the transactions.

Notable codes: 4829 Money Transfer (largest by dollars), 5541 Service Stations, 5411 Grocery Stores, 5300 Wholesale Clubs, 5499 Miscellaneous Food Stores, 5912 Drug Stores and Pharmacies.

---

## `train_fraud_labels.json` (159 MB)

**Grain:** one label per transaction. **8,914,963 labels:** 13,332 "Yes" (0.15%) and 8,901,631 "No". Structure: `{"target": {"<transaction id>": "Yes" | "No", ...}}`.

**Quirks**
- **Covers about 67% of transactions,** so unlabelled does not mean "not fraud".
- **The brief says fraud is not the focus.** In the analysis, labelled fraud is 0.2–0.6% of purchase dollars in every segment and doesn't change any ranking.

---

## `account_signups.csv` (synthetic; not used for now)

**Grain:** one row per signup, where a signup is **one newly opened card**, not one new customer. **Key:** `signup_id`. **Foreign keys:** `client_id`, and `card_id` (unique, so one signup per card). **No nulls.**

| Column | Type | Description | Example |
|---|---|---|---|
| `signup_id` | str | `s_000001` … | s_000001 |
| `client_id` | int | 994 distinct customers | 1718 |
| `card_id` | int | The card opened. `signup_ts` is always in the same calendar month as the card's `acct_open_date`, so they are the same event, recorded to the minute here rather than to the month. | 2379 |
| `signup_ts` | str (timestamp) | Exact signup time | 2019-03-21 17:44:00 |
| `self_reported_source` | str | Survey answer: search 572 · social_media 301 · blog_or_review_site 244 · friend_or_family 203 · other 142 · app_store 63 · podcast_or_youtube 63 | search |
| `signup_landing_page` | str | `/blog/credit-basics`, `/cards/rewards`, `/`, `/cards`, `/compare`, `/apply`, each about 250–280 | /cards |

**Quirks**
- **Most signups come from existing customers:** 83–90% each year from 2016 to 2019, and 54% in 2020. Flag a signup as "existing customer" if the customer had a card opened in an earlier month.
- **Volume jumps abruptly.** There are about 7 signups a month through 2019, then 571 in January 2020 and 607 in February 2020. Spend didn't rise anywhere near proportionally, so this is a likely artifact; confirm before relying on 2020 volumes.
- **Every card opened from 2016 on has a signup row,** so signups count card openings since 2016.
- **Exactly the same 994 customers appear in `marketing_touchpoints`.** Their median age is 31, against 51 for customers without signups.

---

## `marketing_touchpoints.csv` (synthetic; not used for now)

**Grain:** one row per ad impression, click or site visit. **Key:** `touch_id`. **Coverage:** 2016-01-01 to 2020-02-28.

| Column | Type | Description | Example |
|---|---|---|---|
| `touch_id` | str | Unique | t_000000001 |
| `anonymous_id` | str | Cookie or device ID; 1,501,588 distinct, so almost one per touch | anon_000000001 |
| `client_id` | float | Customer, **only for 8,836 touches (0.6%)**, belonging to 994 customers | 1718.0 |
| `touch_ts` | str (timestamp) | Touch time | 2019-03-10 19:40:20 |
| `channel` | str | 11 channels (below) | paid_search_brand |
| `utm_source` | str | google, facebook, bing, apple, reddit, braze, partner, referral; blank for direct | google |
| `utm_medium` | str | cpc, paid_social, email, organic, affiliate, referral; blank for direct | cpc |
| `utm_campaign` | str | 23 campaigns | brand_exact |
| `device` | str | mobile / tablet / desktop, about one-third each | mobile |
| `landing_page` | str | Same 6 pages as signups | /compare |

Touches by channel:

| Channel | Touches |
|---|---:|
| paid_social_meta | 387,631 |
| paid_search_brand | 365,702 |
| paid_search_nonbrand | 296,608 |
| microsoft_ads | 182,706 |
| apple_search_ads | 136,586 |
| paid_social_reddit | 114,193 |
| direct | 22,058 |
| email_lifecycle | 2,383 |
| organic_search | 648 |
| affiliate | 319 |
| referral | 26 |

**Quirks**
- **`anonymous_id` almost never repeats,** so anonymous touches can't be stitched into journeys. Only touches with a `client_id` (8,836) can be tied to a customer.
- **Direct touches have no UTM values** (22,058 rows).
- **Affiliate, referral, organic and email have touches but no spend rows.** Their cost isn't in `channel_spend.csv`.
- **The device split is suspiciously even** (about 33% each), consistent with synthetic generation.

---

## `channel_spend.csv` (synthetic; not used for now)

**Grain:** intended to be one row per day × channel × campaign. **Coverage:** 2016-01-01 to 2020-02-29 (1,521 days).

| Column | Type | Description | Example |
|---|---|---|---|
| `spend_date` | str (date) | Day | 2016-01-01 |
| `channel` | str | 6 paid channels | paid_search_brand |
| `campaign` | str | 14 campaigns (below) | brand_exact |
| `spend` | float | Spend in $ | 210.14 |
| `impressions` | int | | 15010 |
| `clicks` | int | | 852 |
| `platform_reported_conversions` | float | Conversions as reported by the ad platform; fractional values | 0.4 |

Campaigns by channel:

| Channel | Campaigns |
|---|---|
| paid_search_brand | brand_exact, brand_phrase |
| paid_search_nonbrand | generic_cards, compare_cards, rewards_terms |
| paid_social_meta | prospecting_lal, retargeting_site, spring_launch |
| paid_social_reddit | r_personalfinance, r_churning |
| microsoft_ads | bing_generic, bing_brand |
| apple_search_ads | asa_exact, asa_discovery |

**Quirks**
- **Apple Search Ads rows are tripled.** There are 9,126 rows for 2 campaigns, against 3,042 for other 2-campaign channels, and 6,084 duplicate (date, channel, campaign) rows. Deduplicate before summing: raw total spend is $9.57M, cleaned $7.71M. Use `clean_spend()` in `src/analyze_channels.py`.
- **Platform conversions are self-reported and jump in 2020.**
  - Microsoft reports 169 conversions for 2016–2019, then 728 in January–February 2020.
  - Blended spend per reported conversion is about $802, close to the VP's "$770".
  - That is about $4,000 per conversion before 2020 and $58 in 2020.
- **Spend per signup is not usable without investigation.** Paid spend divided by signups is about $29k in 2019 and about $390 in early 2020.
- **Only the 6 paid channels have spend.** Affiliate, referral, organic, direct and email do not.

---

## `revenue_assumptions.csv` (Finance rate card)

**Grain:** one row per assumption. **7 rows.**

| `assumption_key` | Value | Unit | Notes |
|---|---:|---|---|
| `interchange_credit_bps` | 180 | bps of settled purchase volume | Blended across merchant categories |
| `interchange_debit_bps` | 5 | bps of settled purchase volume | Regulated (Durbin) rate |
| `interchange_debit_fixed_cents` | 21 | cents per settled transaction | Applies per debit transaction |
| `revolving_apr_pct` | 19.99 | APR | Applies to revolving credit balances |
| `share_of_credit_balance_revolving_pct` | 35 | % | Finance planning assumption |
| `annual_fee_amex_usd` | 95 | $ per card per year | Amex-branded credit cards only |
| `annual_fee_other_usd` | 0 | $ per card per year | All other brands |

**How it is applied in the analysis** (`src/q1_revenue.py`)

| Item | Treatment |
|---|---|
| Credit | 1.8% of net settled volume (purchases minus refunds) |
| Debit | 0.05% of net volume, plus $0.21 per settled purchase |
| Prepaid | **$0**. Not covered by the rate card; sensitivity test uses debit rates. |
| Amex credit cards | $95 a year, pro-rated by months open in the window |
| Revolving interest | **Excluded.** There is no balance data. |

**Gaps:**
- No prepaid rate.
- No money-transfer exception, though issuers often earn little interchange on money transfers.
- No costs: rewards, credit losses, servicing or fraud.

---

## Derived tables worth knowing

| File | Grain | Built by |
|---|---|---|
| `analysis/q1_scratch/v3/card_month.csv` | Card × month spend, 2010–2019 | `src/build_card_month.py` |
| `analysis/q1_scratch/v2/q1_v2.sqlite` (`fact_transactions`) | Transactions Nov 2018 – Oct 2019, with card, merchant category and signup attributes | `src/build_q1_v2_tables.py` |
| `analysis/q1_scratch/v2/customer_metrics.csv` | Customer value Nov 2018 – Oct 2019 | `src/build_q1_v2_customer_metrics.py` |
| `analysis/q1_scratch/v3/base_customers_segmented.csv` | Established customers with day-one and held-today segments | `src/q1_v3_segments.py` |
| `analysis/q1_scratch/v3/card_openings_classified.csv` | Every card opening flagged as new or existing customer, with the customer's day-one segment | `src/q1_v3_segments.py` |
| `analysis/deep_dives/users/users_enriched.csv` | Users plus card counts and links to other tables | `src/deep_dive_users.py` |
