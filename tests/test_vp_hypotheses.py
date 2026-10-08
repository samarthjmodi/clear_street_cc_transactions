import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vp_hypotheses import credits, flag_acquisitions, journeys  # noqa: E402


def _signups():
    return pd.DataFrame({
        "signup_id": ["s1", "s2", "s3"],
        "client_id": [1, 1, 2],
        "signup_ts": pd.to_datetime(["2020-01-10", "2020-02-20", "2020-01-15"]),
    })


def test_only_first_signup_in_first_card_month_is_an_acquisition():
    # client 1 first card Jan 2020; client 2 had a card in 2015
    cards = pd.DataFrame({"client_id": [1, 1, 2, 2], "open_m": [2020 * 12 + 1, 2020 * 12 + 2, 2015 * 12 + 3, 2020 * 12 + 1]})
    s = flag_acquisitions(_signups(), cards).set_index("signup_id")
    assert s.acquisition.to_dict() == {"s1": True, "s3": False, "s2": False}
    assert s.kind.to_dict() == {"s1": "acquisition", "s3": "existing_customer", "s2": "existing_customer"}


def test_second_card_in_first_month_is_not_an_existing_customer():
    su = pd.DataFrame({"signup_id": ["a", "b"], "client_id": [1, 1],
                       "signup_ts": pd.to_datetime(["2020-01-05", "2020-01-20"])})
    s = flag_acquisitions(su, pd.DataFrame({"client_id": [1, 1], "open_m": [2020 * 12 + 1] * 2})).set_index("signup_id")
    assert s.kind.to_dict() == {"a": "acquisition", "b": "new_customer_extra_card"}


def test_touches_go_to_next_signup_and_post_signup_touches_drop():
    s = flag_acquisitions(_signups(), pd.DataFrame({"client_id": [1, 2], "open_m": [2020 * 12 + 1] * 2}))
    tp = pd.DataFrame({
        "touch_id": ["t1", "t2", "t3", "t4"],
        "client_id": [1, 1, 1, 2],
        "touch_ts": pd.to_datetime(["2020-01-01", "2020-01-12", "2020-03-01", "2020-01-14"]),
        "channel": ["affiliate", "paid_search_brand", "email_lifecycle", "microsoft_ads"],
    })
    j = journeys(tp, s).set_index("touch_id")
    assert j.signup_id.to_dict() == {"t1": "s1", "t2": "s2", "t4": "s3"}


def test_credit_rules():
    j = pd.DataFrame({
        "signup_id": ["s1"] * 3,
        "touch_id": ["a", "b", "c"],
        "touch_ts": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
        "channel": ["affiliate", "paid_search_brand", "paid_search_brand"],
    })
    c = credits(j).set_index("channel")
    assert c.loc["affiliate", ["last", "first", "any"]].tolist() == [0, 1, 1]
    assert c.loc["paid_search_brand", ["last", "first", "any"]].tolist() == [1, 0, 1]
    assert c.loc["affiliate", "linear"] == pytest.approx(1 / 3)
    assert c.loc["paid_search_brand", "linear"] == pytest.approx(2 / 3)
