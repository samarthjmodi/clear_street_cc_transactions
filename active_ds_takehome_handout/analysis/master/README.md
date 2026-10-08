# Working customer–transaction master

`customer_transaction_master.sqlite` contains the physical table `master`.
This is a working dataset, not the Q1 analysis or final submission.

## Population and grain

- Start with users who own at least one card with `acct_open_date` before November 2018.
- Include transactions at or after 2018-11-01 00:00:00 and before 2019-11-01 00:00:00.
- Eligibility is at customer level: transactions on their subsequently opened cards are included too.
- One row per transaction. Each eligible user without a transaction in the window has exactly one placeholder row.
- Placeholder rows retain user and eligibility fields; all transaction, card, MCC-description, fraud and signup fields are SQL NULL.
- No transaction filtering by error, amount sign, merchant category, or fraud label has been applied.

## Joins and columns

All joins are left joins. User ID matches transaction `client_id`; transaction card ID and customer ID match the card; transaction MCC matches the lookup; transaction ID matches fraud labels; customer ID plus transaction card ID match signups. Signup records describe the transacting card's account opening, not necessarily the customer's original acquisition.

Customer, card, MCC, fraud and signup join keys are unique for the selected inputs, preventing fan-out. `join.sql` records the exact SELECT, referring to temporary staging tables under the `src` database alias; it is documentation of the build and is not standalone against the finished database.

Columns use `user_`, `transaction_`, `card_`, and `signup_` prefixes where applicable. Shared IDs are `client_id`, `transaction_id`, and `card_id`. `mcc_description` and `fraud_label` are descriptive joins. The CSV `column_names.csv` contains all 46 column names.

- `eligibility_first_card_open_month`: earliest recorded opening month across the user's cards.
- `eligibility_cards_opened_before_window`: number of cards recorded as opened before November 2018.
- `card_open_month`: normalized opening month of the transacting card. Day 01 represents month precision, not a known exact opening day.
- `transaction_amount`: original dollar-formatted source string.
- `transaction_amount_cents`: numeric amount in integer cents for exact sums.
- Missing fraud labels remain NULL, never converted to `No`.
- Source user profiles have no historical snapshot date. Their inclusion does not make their attributes point-in-time correct.

## Validation and access

`validation.json` records population, transaction and join counts. The build checks unique keys, card ownership, selected transaction uniqueness, date bounds, user retention, exact amount reconciliation, and null placeholder structure. A unique transaction index permits multiple NULL transaction IDs for different nontransactors.

Use SQLite or Python's standard `sqlite3` library. For example:

```sql
SELECT COUNT(DISTINCT client_id) AS customers,
       COUNT(transaction_id) AS transactions,
       SUM(transaction_id IS NULL) AS users_without_transactions
FROM master;
```

Customer-level attributes repeat across transactions. Use distinct customer IDs or aggregate by customer before calculating customer-level statistics.

To reproduce, run `python analysis/build_master.py` from the source-data directory with pandas and numpy installed. The script refuses to overwrite an existing database; preserve or move the existing output first. All raw input files remain unchanged.
