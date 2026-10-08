# Q1 v2 grains

> **Working tables.** These feed the Q3 three-year pricing (see "How to run" in the root `README.md`); the notes below are not part of the submitted analysis.

Population: customers with at least one card opened before 2018-11-01.
Transaction window: 2018-11-01 inclusive through 2019-11-01 exclusive.

| Object | Grain | Where |
|---|---|---|
| `dim_customers` | one row per eligible customer | `dim_customers.csv` and sqlite |
| `dim_cards` | one row per card for those customers, signup left-joined on card | `dim_cards.csv` and sqlite |
| `fact_transactions` | one window transaction, with card + MCC + that card's signup fields | sqlite only (`q1_v2.sqlite`) |

Dormant eligible customers are in `dim_customers` and absent from `fact_transactions`.

Rebuild: `python src/build_q1_v2_tables.py` from the repo root.
