import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from build_card_month import aggregate_chunk  # noqa: E402
from q1_revenue import amex_fee_months, interchange, revolving_interest  # noqa: E402


def _cm(**kw):
    base = dict(purchase_volume=1000.0, purchase_count=10, refund_volume=100.0,
                mt_purchase_volume=200.0, mt_purchase_count=2)
    base.update(kw)
    return pd.DataFrame([base])


def test_credit_interchange_is_180bps_of_net():
    out = interchange(_cm(), pd.Series(["Credit"]))
    assert out.iloc[0] == pytest.approx(900 * 0.018)


def test_debit_interchange_has_fixed_fee_per_purchase():
    out = interchange(_cm(), pd.Series(["Debit"]))
    assert out.iloc[0] == pytest.approx(900 * 0.0005 + 10 * 0.21)


def test_prepaid_earns_zero_unless_flagged():
    assert interchange(_cm(), pd.Series(["Debit (Prepaid)"])).iloc[0] == 0
    alt = interchange(_cm(), pd.Series(["Debit (Prepaid)"]), prepaid_as_debit=True)
    assert alt.iloc[0] == pytest.approx(900 * 0.0005 + 10 * 0.21)


def test_money_transfer_exclusion_removes_volume_and_count():
    out = interchange(_cm(), pd.Series(["Debit"]), exclude_money_transfer=True)
    assert out.iloc[0] == pytest.approx(700 * 0.0005 + 8 * 0.21)


def test_revolving_interest_uses_one_month_balance_at_finance_rates():
    # $12,000 of annual credit spend earns $216 interchange; balance $1,000, 35% revolves at 19.99%
    assert revolving_interest(216.0) == pytest.approx(1_000 * 0.35 * 0.1999)


def test_amex_fee_months_clipped_to_window():
    open_m = pd.Series([100, 105, 120])
    months = amex_fee_months(open_m, 102, 114)
    assert list(months) == [12, 9, 0]


def test_aggregate_chunk_separates_purchases_refunds_and_errors():
    chunk = pd.DataFrame({
        "date": ["2019-01-05 10:00:00"] * 4,
        "client_id": [1] * 4,
        "card_id": [7] * 4,
        "amount": ["$100.00", "$-20.00", "$50.00", "$30.00"],
        "mcc": [5411, 5411, 5411, 4829],
        "errors": [pd.NA, pd.NA, "Bad PIN", pd.NA],
    })
    row = aggregate_chunk(chunk).iloc[0]
    assert row.purchase_volume == pytest.approx(130.0)
    assert row.purchase_count == 2
    assert row.refund_volume == pytest.approx(20.0)
    assert row.mt_purchase_volume == pytest.approx(30.0)
    assert row.txn_count == 4
