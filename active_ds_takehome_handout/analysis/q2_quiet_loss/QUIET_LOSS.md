# Q2: When do I know I'm losing a customer?

Tight analysis on the **1,206 customers with a settled purchase from November 2018 to October 2019**, broken down by Q1 day-one segments (credit limit $10k+, credit under $10k, debit, prepaid).

**Short answer:** among customers we can observe, almost nobody quietly fades. The median gap between purchase days is **1 day** in every segment. A **7-day** silence is already rare (~3% of actives); **14+ days** is almost unheard of; the only people who reach **~30 days** silent are three debit customers who also have **no open card** at the February 2020 snapshot. True leavers before 2020 are invisible in this extract.

![Quiet loss by day-one segment](../../../plots/q2_quiet_loss.png)

## 1. Population and segments

| Day-one segment | Active customers |
|---|---:|
| Credit, limit $10k+ | 226 |
| Credit, limit under $10k | 193 |
| Debit | 693 |
| Prepaid | 94 |
| **All active** | **1,206** |

Day-one segment uses the cards opened in the customer's first-card month (same definition as Q1).

## 2. Gap distribution

| Day-one segment | Median gap | Median of each customer's longest gap | Longest gap anywhere | Median days silent at window end |
|---|---:|---:|---:|---:|
| Credit, limit $10k+ | 1 | 2 | 8 | 0 |
| Credit, limit under $10k | 1 | 3 | 7 | 0 |
| Debit | 1 | 3 | 22 | 0 |
| Prepaid | 1 | 3 | 11 | 0 |
| **All active** | **1** | **3** | **22** | **0** |

- Gaps are between calendar days with a settled purchase (amount > 0, no error).
- Almost everyone's last purchase falls on the window's final days (median terminal silence = 0).

## 3. Silence thresholds: hit rate and return

A customer **hits N-day silence** if they ever have an inter-purchase gap ≥ N days, or are still silent ≥ N days at the window end.

For inter-purchase silences only: **returned within 30 days of the alert** means the next purchase falls within N + 30 days of the previous one. Terminal silence at the window end is reported separately (return unknown).

| N (days) | Hit rate, all active | Inter-purchase episodes | Return rate after alert | Still silent at window end |
|---:|---:|---:|---:|---:|
| 7 | **3.4%** (41 people) | 58 | **100%** | 3 |
| 14 | **0.3%** (4) | 1 | **100%** | 3 |
| 30 | **0.2%** (3) | 0 | — | **3** |
| 60 | **0%** | 0 | — | 0 |

### By segment (hit rate)

| N | Credit $10k+ | Credit under $10k | Debit | Prepaid |
|---:|---:|---:|---:|---:|
| 7 | 2.2% | 2.6% | 3.5% | **7.4%** |
| 14 | 0% | 0% | 0.6% | 0% |
| 30 | 0% | 0% | 0.4% | 0% |
| 60 | 0% | 0% | 0% | 0% |

- **Prepaid** is a bit more likely to have a short (7-day) quiet spell, but every one of those inter-purchase spells was followed by a purchase within the return window.
- **Credit** starters almost never go quiet for a week; none hit 14 days.
- The only **14- and 30-day** hits are debit customers.

## 4. Structural exit: no open card

| Day-one segment | No open card (Feb 2020) | Share |
|---|---:|---:|
| Credit, limit $10k+ | 0 | 0% |
| Credit, limit under $10k | 0 | 0% |
| Debit | **3** | 0.4% |
| Prepaid | 0 | 0% |

Those three debit customers are exactly the ones with 31–35 days of terminal silence at the end of the window. Soft silence and hard exit coincide here.

## 5. What to tell the VP

1. **At risk:** customer-level silence of **7 days** (already unusual; ~3% of actives ever hit it). Prepaid is slightly more exposed.
2. **Likely gone:** **no open card**, or silence of **~30 days**. In this window that is three people, all debit day-one.
3. **What the 7-day flag is worth:** it flags 41 customers. 38 came back within 30 days on their own; the other 3 are the only customers who left. It catches every loss here, but most alerts are false alarms, and three losses are too few to tune it. It's a monitoring flag to calibrate once closures are recorded, not a tested churn predictor.
4. **Do not use a 60-day recency rule** on this base — nobody in the active file reaches it.
5. **Segments barely differ** on quiet loss among people we can see. The value split from Q1 (credit vs debit vs prepaid) is about revenue, not about who fades.

## 6. Caveats (do not stretch)

- This describes **active customers with transactions in the window**, not the full 2,000.
- **~394** customers joined before November 2019 with **no transaction rows** — out of scope; could be missing data or never-activated, not proven quiet loss.
- `users_data` only includes customers **still on file in February 2020**. Customers who left earlier are invisible, so these rates are not historical churn rates.
- Near-daily purchasing may be partly a feature of how this public dataset was built; treat the **relative** finding (short gaps, rare silence) as the actionable part, and instrument closed/charge-off flags for production.

## How to reproduce

```bash
.venv/bin/python src/q2_quiet_loss.py
.venv/bin/python -m pytest tests/test_q2_quiet_loss.py -q
```

Outputs: `active_ds_takehome_handout/analysis/q2_quiet_loss/` and `plots/q2_quiet_loss.png`.
