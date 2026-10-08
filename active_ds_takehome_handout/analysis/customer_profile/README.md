# Framework step 2: customer description

> **Superseded working notes.** The submitted analysis is the root `README.md`; figures here were not updated and may not match it.

Source: the working master table. Population: 1,603 users with at least one card opened before November 2018. Observation window: November 2018 through October 2019.

`customer_summary.csv` has exactly one row per eligible user. Activity outputs describe positive amounts with no error recorded. This is a descriptive filter, not confirmation of settlement or a final definition of revenue-generating purchases. Money transfers and labeled fraud are included. Negative amounts are reported separately, not assumed to be refunds. The source master is unchanged.

The 397 users with no transaction records have zero *observed* activity totals. This does not establish zero real-world activity, churn, or zero customer value. Null dates and average transaction amounts remain missing.

Files:

- `customer_summary.csv`: customer attributes and activity aggregates.
- `demographics_by_observation.csv`: customer-level demographic medians by presence of records.
- `activity_distributions.csv`: distributions among 1,206 users with positive, error-free transactions.
- `card_usage.csv`: usage by card type; customer counts overlap across types.
- `merchant_categories.csv`: activity by merchant category, ordered by positive amount.
- `monthly_activity.csv`: monthly counts, users and positive amounts.
- `statistics.json`: overall descriptive statistics.
- `customer_summary.sql`: aggregation query.

Reported age, income, debt and credit score are undated source profiles. Cards used are observed transacting cards, not all cards owned. Reported card count is a separate profile attribute. No customer-value model or segment definitions have been applied.

Validation checks customer grain, population and transaction totals, card-type amount reconciliation, and transaction counts across the customer, card-type, merchant-category and monthly summaries.

Reproduce with `python analysis/profile_customers.py` using pandas. The script reads the SQLite master without modifying it and writes these summaries.
