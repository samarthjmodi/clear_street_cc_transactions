"""Card x month spend history for the full transaction file (2010-01 to 2019-10).

Settled purchase = amount > 0 and no error; refund = amount < 0 and no error.
Money transfer (MCC 4829) purchase volume is kept separately for sensitivity tests.

Run from repo root:
  .venv/bin/python src/build_card_month.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
OUT = HANDOUT / "analysis" / "q1_scratch" / "v3"
MONEY_TRANSFER_MCC = 4829


def aggregate_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    amt = pd.to_numeric(chunk["amount"].str.replace(r"[$,]", "", regex=True), errors="coerce")
    settled = chunk["errors"].isna() | chunk["errors"].eq("")
    purchase = settled & (amt > 0)
    refund = settled & (amt < 0)
    df = pd.DataFrame(
        {
            "card_id": chunk["card_id"],
            "client_id": chunk["client_id"],
            "month": chunk["date"].str.slice(0, 7),
            "purchase_volume": amt.where(purchase, 0.0),
            "purchase_count": purchase.astype(int),
            "refund_volume": (-amt).where(refund, 0.0),
            "mt_purchase_volume": amt.where(purchase & chunk["mcc"].eq(MONEY_TRANSFER_MCC), 0.0),
            "mt_purchase_count": (purchase & chunk["mcc"].eq(MONEY_TRANSFER_MCC)).astype(int),
            "txn_count": 1,
        }
    )
    return df.groupby(["card_id", "client_id", "month"], as_index=False).sum()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    parts = []
    reader = pd.read_csv(
        HANDOUT / "transactions_data.csv",
        usecols=["date", "client_id", "card_id", "amount", "mcc", "errors"],
        dtype={"errors": "string", "amount": "string", "date": "string"},
        chunksize=500_000,
    )
    rows = 0
    for chunk in reader:
        rows += len(chunk)
        parts.append(aggregate_chunk(chunk))
    cm = pd.concat(parts).groupby(["card_id", "client_id", "month"], as_index=False).sum()
    assert cm.txn_count.sum() == rows, "row count lost in aggregation"
    cm.to_csv(OUT / "card_month.csv", index=False)
    print(f"rows read {rows:,}; card-months {len(cm):,}; cards {cm.card_id.nunique():,}")


if __name__ == "__main__":
    main()
