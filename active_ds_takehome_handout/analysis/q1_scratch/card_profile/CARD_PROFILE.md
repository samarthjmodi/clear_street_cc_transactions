# First-year revenue per card, by card and by who opened it

> **Superseded working notes.** The submitted analysis is the root `README.md`. These notes argue for an earlier $12k credit cut; the report uses $10k, so figures here won't match it. The plots they referenced were removed from the submission.

## Summary

**Card attributes matter more than customer attributes.** What the card is, and whether it's the customer's first card, explains far more of first-year revenue than who the customer is.

- **Card type is the biggest driver.** A credit card earns $400 in its first year, a debit card $97 and a prepaid card $0. Prepaid cards carry about $8.7k of spending a year; at debit rates that would be about $75.
- **A customer's first card earns about twice as much as an extra card.** First credit cards earn $737 against $364 for extra credit cards; first debit cards earn $202 against $87. First cards carry two to three times the purchase volume, because an extra card splits the customer's existing spending.
- **Above about $11k, a higher credit limit means more revenue.** Credit cards with limits under $11k earn $306–$339 regardless of limit. From $11k to $15k they earn $426, and above $15k $624. This supports the $12k cut used for the Premium credit segment.
- **Brand barely matters.** Amex credit cards earn the most ($467), but only because of the $95 annual fee; their interchange ($372) is the same as Mastercard's. Visa, Mastercard and Discover credit cards earn $348–$400, with overlapping intervals.
- **Opening year shows no trend.** Cards opened in each year from 2010 to 2018 earn $139–$205, with no rise or fall. Credit cards swing more from year to year ($284–$538) because the yearly samples are small.

**Customer attributes**

- **Income is the only customer attribute that clearly moves card value, and only on credit cards.** A credit card opened by a top-fifth-income customer earns $647 in its first year, against $232 for the bottom fifth (2.8×). On debit the range is only $77 to $108.
- **Income works through the credit limit.** The median limit rises from $6.8k to $17.2k across income fifths, and the share of cards that are credit stays at 30–35% in every bucket. Higher-income customers don't pick credit more often; they get bigger limits and spend more on them.
- **Younger customers look more valuable per card, but most of that is card count.** Under-30s earn $270 per card against $143 for over-70s. Older customers hold more cards (5.7 versus 3.5), so their spending is spread thinner. Holding card count fixed, the age gap on credit mostly disappears. A smaller gap remains on debit, where under-30s still earn more.
- **More cards means less revenue per card, not worse customers.** Revenue per card falls from $486 for customers with one card to $120 for six or more, because purchase volume per card falls from $49k to $13k. The same wallet is split across more cards. This is a feature of measuring per card, so don't use card count as a quality signal.
- **Geography is weak.** The Northeast is highest at $225 per card and the Midwest lowest at $162, but the confidence intervals overlap and the gap narrows once card type is accounted for. No state stands out reliably; the 17 states with at least 30 cards all have wide intervals.

## Data and method

- **Cards:** every card opened from January 2010 to November 2018, so each has a full first year of transactions before the data ends in October 2019.
  - That is 1,594 cards from 903 customers: 513 credit, 953 debit and 128 prepaid.
  - 316 cards were dropped because their customers have no transactions at all.
- **First-year revenue** is the card's own first 12 months of interchange plus pro-rated Amex fees, at the Finance rate card. Credit earns 1.8% of net purchases; debit earns 0.05% plus $0.21 per purchase; prepaid earns $0.
- **Customer attributes** come from `users_data`, a February 2020 snapshot:
  - **Age at opening** is current age minus the years since the card opened.
  - **State** comes from latitude and longitude, matched to US state boundaries. 894 customers fall inside a state outline; 9 near the coast are assigned the nearest state. The result matches each customer's most common in-person shopping state for 99.3% of customers.
  - **Income buckets** are fifths (quintiles). `yearly_income` is largely derived from `per_capita_income` (rank correlation 0.91), so the two give nearly identical results.
  - **`num_credit_cards`** counts all cards of every type held in February 2020, including cards opened after the one being measured.
- **Confidence intervals** resample customers rather than cards, because one customer's cards move together.

## Card attributes

![First-year revenue per card by card attributes](../../../../plots/q1_card_y1_by_card_attributes.png)

### Card type, and first card versus extra card

| Card | Cards | First-year revenue (95% CI) | Purchase volume |
|---|---:|---:|---:|
| **Credit** | 513 | **$400** ($369–$431) | $23.4k |
| Customer's first card | 49 | $737 ($619–$868) | $43.9k |
| Extra card | 464 | $364 ($336–$394) | $21.2k |
| **Debit** | 953 | **$97** ($92–$102) | $19.1k |
| Customer's first card | 83 | $202 ($181–$223) | $48.4k |
| Extra card | 870 | $87 ($83–$91) | $16.3k |
| **Prepaid** | 128 | **$0** | $8.7k |

- **The first-card premium is a spending effect.** First cards carry two to three times the purchase volume of extra cards, and the gap in revenue follows.
- **The two figures answer different questions:**
  - The first-card figure is the value of a new customer's starting card.
  - The extra-card figure is what a card adds before netting out spending that moved from the customer's other cards. Q1_FINDINGS.md estimates that only about half of an extra credit card's revenue is genuinely new.
- **Only 139 cards are first cards,** because most customers opened their first card before 2010, when the transaction data starts.
- **Prepaid isn't idle.** Prepaid cards are used 11.6 months a year on average. They earn nothing only because the rate card has no prepaid rate.

### Brand

| Brand and type | Cards | First-year revenue (95% CI) | Of which interchange | Of which Amex fee |
|---|---:|---:|---:|---:|
| Amex credit | 106 | $467 ($410–$533) | $372 | $95 |
| Visa credit | 203 | $400 ($351–$456) | $400 | — |
| Mastercard credit | 147 | $372 ($326–$424) | $372 | — |
| Discover credit | 57 | $348 ($261–$462) | $348 | — |
| Mastercard debit | 577 | $100 ($94–$107) | $100 | — |
| Visa debit | 376 | $91 ($84–$98) | $91 | — |
| Mastercard prepaid | 82 | $0 | $0 | — |
| Visa prepaid | 46 | $0 | $0 | — |

- **Amex and Discover only issue credit cards here,** so their high brand-level averages are a card-type effect.
- **Within each card type, brand makes little difference.** The rate card applies one interchange rate to all brands, so revenue differs only through spending.
- **The Amex premium is the $95 fee alone.** Whether it's real depends on whether customers pay the fee; the data doesn't show fee waivers or refunds.

### Credit limit (credit cards only)

| Credit limit fifth | Cards | First-year revenue (95% CI) | Purchase volume |
|---|---:|---:|---:|
| Under $6k | 104 | $309 ($260–$371) | $17.8k |
| $6k–$9k | 105 | $306 ($265–$351) | $17.8k |
| $9k–$11k | 102 | $339 ($287–$394) | $20.0k |
| $11k–$15k | 99 | $426 ($371–$485) | $25.3k |
| $15k+ | 103 | $624 ($538–$726) | $36.2k |

- **Below about $11k, limit doesn't change spending.** Revenue is flat at about $300–$340. Above that point it climbs steeply, and spending roughly doubles between the bottom and top fifth.
- **This supports the $12k Premium credit cut** used in the segments.
- **Limit tracks income closely** (rank correlation 0.59) and revenue more loosely (0.36).
- **8 credit cards have a $0 limit** and are included in the lowest fifth.
- **On debit cards, the `credit_limit` field isn't a credit line.** Debit revenue only moves from $87 to $105 across its fifths (rank correlation 0.10), though the field tracks income (0.65). On prepaid cards it's a balance with a median of $69. The full debit table is in `profile_debit_limit_bucket.csv`.

### Opening-year cohorts

| Year opened | Cards | All cards (95% CI) | Adjusted for card-type mix | Credit cards | Debit cards | Share credit | Share that are first cards |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 471 | $205 ($186–$228) | $190 | $394 | $106 | 38% | 13% |
| 2011 | 289 | $183 ($158–$213) | $181 | $392 | $93 | 33% | 9% |
| 2012 | 161 | $176 ($150–$205) | $177 | $347 | $109 | 32% | 8% |
| 2013 | 168 | $205 ($157–$260) | $230 | $538 | $95 | 26% | 9% |
| 2014 | 146 | $140 ($109–$178) | $147 | $284 | $93 | 27% | 3% |
| 2015 | 125 | $186 ($147–$232) | $185 | $413 | $88 | 33% | 9% |
| 2016 | 98 | $189 ($142–$247) | $198 | $440 | $94 | 29% | 6% |
| 2017 | 74 | $158 ($113–$213) | $168 | $384 | $75 | 28% | 4% |
| 2018 | 62 | $176 ($109–$272) | $217 | $515 | $86 | 24% | 0% |

- **No cohort is clearly better or worse.** Every year's interval overlaps with the others, and the mix-adjusted figures have no trend.
- **Debit is very stable** at $75–$109 a year. The credit line jumps around because each year has only 15–179 credit cards.
- **The share of credit cards falls from 38% to 24%,** and fewer cards each year are first cards. This reflects who is left in the February 2020 base, more than a change in what people opened.
- The 2018 cohort only includes cards opened through November 2018, so each has a full first year.

## Customer attributes

![First-year revenue per card by customer attributes](../../../../plots/q1_card_y1_by_user_attributes.png)

### Income

| Yearly income fifth | Cards | All cards | Credit cards | Debit cards | Median credit limit |
|---|---:|---:|---:|---:|---:|
| Under $30k | 320 | $124 | $232 | $77 | $6.8k |
| $30k–$37k | 320 | $155 | $312 | $98 | $8.0k |
| $37k–$45k | 318 | $171 | $344 | $98 | $9.8k |
| $45k–$58k | 318 | $220 | $489 | $100 | $12.6k |
| $58k+ | 318 | $262 | $647 | $108 | $17.2k |

- Within credit, income has a rank correlation of 0.48 with first-year revenue; within debit it's 0.16.
- Area per-capita income gives the same pattern: $225 to $648 on credit across its fifths.

### Age at opening

| Age | Cards | All cards (95% CI) | Credit cards | Debit cards | Average cards held |
|---|---:|---:|---:|---:|---:|
| Under 30 | 245 | $270 ($236–$310) | $519 | $144 | 3.5 |
| 30–39 | 316 | $191 ($166–$218) | $390 | $109 | 3.8 |
| 40–49 | 367 | $183 ($155–$217) | $418 | $96 | 4.3 |
| 50–59 | 294 | $153 ($132–$177) | $341 | $79 | 4.5 |
| 60–69 | 161 | $177 ($135–$222) | $410 | $75 | 4.9 |
| 70+ | 211 | $143 ($118–$170) | $305 | $66 | 5.7 |

Holding card count fixed (customers with 1–3, 4–5 or 6+ cards):
- **Credit:** no consistent age pattern. For example, among customers with 4–5 cards, credit cards earn $317–$462 in every age group, with no steady decline.
- **Debit:** under-30s still earn more. Among customers with 1–3 cards, a debit card earns $172 for under-30s against $90–$128 for other ages.

### Number of cards held

| Cards held (Feb 2020) | Cards | All cards (95% CI) | Credit cards | Debit cards | Purchase volume per card |
|---|---:|---:|---:|---:|---:|
| 1 | 29 | $486 ($333–$713) | $800 | $223 | $49.2k |
| 2 | 107 | $316 ($260–$387) | $613 | $166 | $33.8k |
| 3 | 338 | $210 ($182–$241) | $455 | $114 | $23.7k |
| 4 | 476 | $190 ($170–$211) | $380 | $100 | $19.1k |
| 5 | 310 | $155 ($133–$180) | $326 | $83 | $15.9k |
| 6+ | 334 | $120 ($101–$142) | $301 | $61 | $12.8k |

Card count is unrelated to income (rank correlation −0.02), so this isn't an income effect in disguise. The right way to judge multi-card customers is total value per customer, which is in `Q1_FINDINGS.md`.

### Geography

![First-year revenue per card by location](../../../../plots/q1_card_y1_by_geography.png)

| Region | Cards | All cards (95% CI) | Adjusted for card-type mix | Credit cards | Debit cards |
|---|---:|---:|---:|---:|---:|
| Northeast | 294 | $225 ($189–$266) | $219 | $494 | $100 |
| West | 360 | $191 ($164–$221) | $189 | $407 | $98 |
| South | 627 | $178 ($160–$196) | $175 | $365 | $97 |
| Midwest | 313 | $162 ($138–$186) | $174 | $370 | $91 |

- **The regional gap is on credit cards.** Debit earns $91–$100 in every region.
- **States are too small to rank.** New Jersey is highest at $324 per card, but its interval runs from $200 to $503 on 45 cards. Only California (217 cards), Texas (130) and New York (121) have more than 100.
- The full state table is in `profile_state.csv`.

## What this means for Q1

- **Product type and credit limit are the right basis for segments.** They are the two strongest drivers, and both are known on the day a card is approved. The $11k–$12k break in the limit data matches the segment cut.
- **First cards and extra cards should be valued separately.** A new customer's first card is worth about twice an extra card.
- **Brand and opening year don't need their own segments.** The only brand difference is the Amex fee.
- **Income is the useful customer attribute** for describing who is worth having. It works by raising the credit limit, which is why the segments already use the limit.
- **Age is secondary.** Younger customers are slightly more active on debit, but the large raw age gap mostly reflects how many cards people hold.
- **Geography doesn't separate value** beyond what income already explains.
- **Card count should not be used** to judge customer quality on a per-card basis.

## Limitations

- **Attributes are measured in February 2020,** after most of these cards were opened. Income and card count may have changed since opening; age is adjusted back.
- **Per-card value understates multi-card customers.** It answers "what is a new card worth", not "what is a customer worth".
- **Customers with no transaction data are excluded:** 316 cards. They skew younger, so the under-30 group is under-represented.
- **Small groups:** only 29 cards belong to one-card customers, and the oldest groups have few customers with few cards.
- **Credit limits are as of February 2020.** A limit raised after opening would make the card look as if it started with a higher limit.
- **The state boundaries are low resolution.** The fallback affects 9 customers, and the cross-check against shopping location agrees 99.3% of the time.

## Files

| File | Contents |
|---|---|
| `card_first_year_profiled.csv` | One row per card with first-year revenue and the opener's attributes, state and buckets |
| `profile_card_brand.csv`, `profile_brand_type.csv`, `profile_card_type_label.csv`, `profile_card_role_type.csv`, `profile_credit_limit_bucket.csv`, `profile_debit_limit_bucket.csv`, `profile_open_year.csv` | Card-attribute profile tables |
| `profile_age_bucket.csv`, `profile_per_capita_income_bucket.csv`, `profile_yearly_income_bucket.csv`, `profile_num_cards_bucket.csv`, `profile_region.csv`, `profile_state.csv` | Customer-attribute profile tables |
| `card_profile_notes.json` | Counts, correlations within card type, limit checks, state validation |
| `../../reference/us_states.geojson` | US state boundaries used for the state lookup |
| `src/q1_card_first_year_profile.py`, `tests/test_q1_card_profile.py` | Code and tests |
