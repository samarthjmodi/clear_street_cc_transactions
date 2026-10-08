"""Build Q1 v2 grains: dim_customers, dim_cards, fact_transactions.

Run from repo root:
  .venv/bin/python src/build_q1_v2_tables.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = ROOT / "analysis" / "q1_scratch" / "v2"
START = "2018-11-01"
END = "2019-11-01"

CARD_ATTRS = [
    "card_brand",
    "card_type",
    "credit_limit",
    "opened",
    "has_chip",
    "signup_id",
    "signup_ts",
    "signup_self_reported_source",
    "signup_landing_page",
]


def money(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace("$", "", regex=False), errors="coerce")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    users = pd.read_csv(ROOT / "users_data.csv")
    cards = pd.read_csv(ROOT / "cards_data.csv")
    signups = pd.read_csv(ROOT / "account_signups.csv")
    mcc = json.loads((ROOT / "mcc_codes.json").read_text())

    for col in ["yearly_income", "per_capita_income", "total_debt"]:
        users[col] = money(users[col])
    cards["credit_limit"] = money(cards["credit_limit"])
    cards["opened"] = pd.to_datetime(cards["acct_open_date"], format="%m/%Y")

    if signups.duplicated(["client_id", "card_id"]).any():
        raise ValueError("Multiple signups per card; card-grain join is not one-to-one")

    eligible_ids = set(cards.loc[cards.opened < START, "client_id"])
    dim_customers = (
        users[users.id.isin(eligible_ids)].rename(columns={"id": "client_id"}).copy()
    )
    dim_customers.to_csv(OUT / "dim_customers.csv", index=False)

    signup_on_card = signups.rename(columns={"card_id": "id"}).drop(columns=["client_id"])
    dim_cards = cards[cards.client_id.isin(eligible_ids)].merge(
        signup_on_card, on="id", how="left", validate="one_to_one"
    )
    dim_cards = dim_cards.rename(
        columns={
            "id": "card_id",
            "self_reported_source": "signup_self_reported_source",
        }
    )
    dim_cards.to_csv(OUT / "dim_cards.csv", index=False)

    db_path = OUT / "q1_v2.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    dim_customers.to_sql("dim_customers", con, index=False)
    # SQLite-friendly card dim (timestamps as text)
    cards_sql = dim_cards.copy()
    cards_sql["opened"] = pd.to_datetime(cards_sql.opened).dt.strftime("%Y-%m-%d")
    cards_sql.to_sql("dim_cards", con, index=False)

    owner = dim_cards.set_index("card_id").client_id
    lookup = dim_cards.set_index("card_id")[CARD_ATTRS]
    n_rows = 0
    for chunk in pd.read_csv(ROOT / "transactions_data.csv", chunksize=250_000):
        chunk = chunk[chunk.client_id.isin(eligible_ids)]
        chunk = chunk[(chunk.date >= START) & (chunk.date < END)]
        if chunk.empty:
            continue
        if not chunk.client_id.eq(chunk.card_id.map(owner)).all():
            raise ValueError("Transaction/card owner mismatch")
        chunk = chunk.copy()
        chunk["amount_usd"] = money(chunk["amount"])
        chunk["mcc_description"] = chunk.mcc.map(lambda x: mcc.get(str(int(x))))
        attrs = lookup.loc[chunk.card_id].reset_index(drop=True)
        attrs = attrs.rename(columns={"credit_limit": "card_credit_limit", "opened": "card_open_month", "has_chip": "card_has_chip"})
        fact = pd.concat([chunk.reset_index(drop=True), attrs], axis=1)
        fact["card_open_month"] = pd.to_datetime(fact.card_open_month).dt.strftime("%Y-%m-%d")
        fact["signup_ts"] = pd.to_datetime(fact.signup_ts, errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        fact.to_sql("fact_transactions", con, index=False, if_exists="append")
        n_rows += len(fact)
        if n_rows % 400_000 < 250_000 and n_rows > 250_000:
            print(f"wrote {n_rows:,}", flush=True)

    con.execute("CREATE INDEX fact_client ON fact_transactions(client_id)")
    con.execute("CREATE INDEX fact_card ON fact_transactions(card_id)")
    con.commit()
    customers_in_fact = con.execute(
        "SELECT COUNT(DISTINCT client_id) FROM fact_transactions"
    ).fetchone()[0]
    con.close()

    audit = {
        "eligible_customers": int(len(dim_customers)),
        "cards_for_eligible": int(len(dim_cards)),
        "cards_with_signup": int(dim_cards.signup_id.notna().sum()),
        "fact_rows": int(n_rows),
        "customers_with_window_txn": int(customers_in_fact),
        "eligible_without_window_txn": int(len(dim_customers) - customers_in_fact),
        "window_start_inclusive": START,
        "window_end_exclusive": END,
        "grains": {
            "dim_customers": "one row per eligible customer (users_data only)",
            "dim_cards": "one row per card owned by an eligible customer, with signup left-joined on card_id",
            "fact_transactions": "one row per window transaction for eligible customers, with card, MCC, and that card's signup attributes",
        },
    }
    (OUT / "build_audit.json").write_text(json.dumps(audit, indent=2))
    (OUT / "README.md").write_text(
        """# Q1 v2 grains

Population: customers with at least one card opened before 2018-11-01.
Transaction window: 2018-11-01 inclusive through 2019-11-01 exclusive.

| Object | Grain | Where |
|---|---|---|
| `dim_customers` | one row per eligible customer | `dim_customers.csv` and sqlite |
| `dim_cards` | one row per card for those customers, signup left-joined on card | `dim_cards.csv` and sqlite |
| `fact_transactions` | one window transaction, with card + MCC + that card's signup fields | sqlite only (`q1_v2.sqlite`) |

Dormant eligible customers are in `dim_customers` and absent from `fact_transactions`.

Rebuild: `python src/build_q1_v2_tables.py` from the repo root.
"""
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
