"""Rate-card revenue for card x month spend, shared by the Q1 v3 analyses."""
from __future__ import annotations

import numpy as np
import pandas as pd

CREDIT_BPS = 180
DEBIT_BPS = 5
DEBIT_FIXED = 0.21
AMEX_FEE = 95.0
REVOLVE_APR = 0.1999
REVOLVE_SHARE = 0.35
WINDOW_END_MONTH = 2019 * 12 + 10  # Oct 2019, last month with transactions


def month_index(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s)
    return d.dt.year * 12 + d.dt.month


def money(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")


def load_cards(path) -> pd.DataFrame:
    c = pd.read_csv(path)
    c["opened"] = pd.to_datetime(c["acct_open_date"], format="%m/%Y")
    c["open_m"] = c.opened.dt.year * 12 + c.opened.dt.month
    c["credit_limit"] = money(c["credit_limit"])
    return c.rename(columns={"id": "card_id"})


def interchange(
    cm: pd.DataFrame,
    card_type: pd.Series,
    exclude_money_transfer: bool = False,
    prepaid_as_debit: bool = False,
) -> pd.Series:
    """Interchange per card-month row. `card_type` must be aligned to `cm`."""
    pv = cm.purchase_volume - (cm.mt_purchase_volume if exclude_money_transfer else 0)
    cnt = cm.purchase_count - (cm.mt_purchase_count if exclude_money_transfer else 0)
    net = pv - cm.refund_volume
    credit = net * CREDIT_BPS / 10_000
    debit = net * DEBIT_BPS / 10_000 + cnt * DEBIT_FIXED
    is_debit = card_type.eq("Debit") | (prepaid_as_debit & card_type.eq("Debit (Prepaid)"))
    return pd.Series(
        np.select([card_type.eq("Credit"), is_debit], [credit, debit], default=0.0), index=cm.index
    )


def revolving_interest(credit_interchange: pd.Series | float) -> pd.Series | float:
    """Finance's revolve assumption on a balance of one month's net credit spend.

    There is no balance data, so the balance is a stated assumption, not an observation.
    """
    annual_credit_spend = credit_interchange / (CREDIT_BPS / 10_000)
    return annual_credit_spend / 12 * REVOLVE_SHARE * REVOLVE_APR


def amex_fee_months(open_m: pd.Series, start_m: int | pd.Series, end_m: int | pd.Series) -> pd.Series:
    """Months an Amex credit card is open inside [start_m, end_m) month indices."""
    lo = np.maximum(open_m, start_m)
    return np.clip(end_m - lo, 0, None)
