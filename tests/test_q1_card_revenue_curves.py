import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from q1_card_revenue_curves import FIRST_M, card_years  # noqa: E402
from q1_revenue import WINDOW_END_MONTH  # noqa: E402


def _cards(open_m, exp_m, brand="Amex", card_type="Credit"):
    return pd.DataFrame({"card_id": [1], "client_id": [10], "card_type": [card_type], "card_brand": [brand],
                         "open_m": [open_m], "exp_m": [exp_m], "first_card": [True]})


def test_card_years_tenure_expiry_and_amex_fee():
    open_m = FIRST_M  # Jan 2010
    exp_m = open_m + 17  # expires in month 6 of year 2
    cm = pd.DataFrame({"card_id": [1, 1, 1], "m": [open_m, open_m + 11, open_m + 12],
                       "rev": [10.0, 5.0, 7.0], "purchase_count": [1, 1, 1], "purchase_volume": [100.0, 50.0, 70.0]})
    cy = card_years(_cards(open_m, exp_m), cm).set_index("k")
    assert cy.loc[1, "interchange"] == pytest.approx(15.0)
    assert cy.loc[2, "interchange"] == pytest.approx(7.0)
    assert cy.loc[1, "amex_fee"] == pytest.approx(95.0)
    assert cy.loc[2, "amex_fee"] == pytest.approx(95.0 * 6 / 12)
    assert cy.loc[3, "amex_fee"] == 0 and not cy.loc[3, "is_open"]
    assert cy.loc[3, "revenue"] == 0
    assert cy.index.max() == (WINDOW_END_MONTH - open_m + 1) // 12


def test_card_years_outside_window_are_dropped():
    open_m = FIRST_M - 18  # opened Jul 2008: year 1 and 2 start before Jan 2010
    cm = pd.DataFrame({"card_id": [1], "m": [FIRST_M + 6], "rev": [3.0], "purchase_count": [1],
                       "purchase_volume": [10.0]})
    cy = card_years(_cards(open_m, WINDOW_END_MONTH + 60, brand="Visa", card_type="Debit"), cm)
    assert cy.k.min() == 3
    assert (cy.start_m >= FIRST_M).all() and (cy.start_m + 11 <= WINDOW_END_MONTH).all()
    assert cy.amex_fee.eq(0).all()
    assert cy.set_index("k").loc[3, "interchange"] == pytest.approx(3.0)
