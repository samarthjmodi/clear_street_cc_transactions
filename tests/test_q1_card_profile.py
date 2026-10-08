import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from q1_card_first_year_profile import load_state_polygons, money_bins, state_of  # noqa: E402


def test_state_of_known_cities_and_offshore_fallback():
    polys = load_state_polygons()
    lat = np.array([40.71, 34.05, 41.88, 29.76, 25.76])
    lon = np.array([-74.01, -118.24, -87.63, -95.37, -80.05])
    state, inside = state_of(lat, lon, polys)
    assert list(state[:4]) == ["New York", "California", "Illinois", "Texas"]
    assert inside[:4].all()
    assert state[4] == "Florida"


def test_money_bins_quintiles_cover_all_values():
    s = pd.Series(np.arange(1, 101) * 1000.0)
    b = money_bins(s)
    assert b.notna().all()
    assert b.value_counts().eq(20).all()
