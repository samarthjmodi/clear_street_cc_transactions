"""Q1: who our customers are, and which segments are worth having.

Step 1 cuts the customer base by every candidate dimension and shows each group's size,
transaction behaviour and provisional revenue, so we can see which dimensions separate value
and which of those are known when a customer is acquired.

Step 2 sets the revenue model (BASE_MODEL) and tests each assumption. Revenue is rate-card
interchange on settled transactions (no error) in Nov 2018 - Oct 2019, net of refunds and
reversals, with prepaid at the debit rate, plus the Amex $95 annual fee pro-rated by months open.
Revolving interest is left out: there is no balance data.

Run from repo root:  .venv/bin/python src/q1_customer_value.py [1 ...]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vp_hypotheses import flag_acquisitions, journeys, load_linked_touches  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
OUT = HANDOUT / "analysis" / "q1_value"
PLOTS = REPO / "plots"

WINDOW = ("2018-11", "2019-10")
WINDOW_IDX = (2018 * 12 + 11, 2019 * 12 + 10)
MIN_GROUP = 30

MCC_CATEGORY = {
    **dict.fromkeys(["5411", "5499", "5300", "5310", "5912", "5921"], "Grocery, wholesale and pharmacy"),
    **dict.fromkeys(["5812", "5813", "5814"], "Restaurants and bars"),
    **dict.fromkeys(["5541", "5533", "7531", "7538", "7542", "7549", "4784"], "Gas and auto"),
    **dict.fromkeys(["3722", "3771", "4111", "4112", "4121", "4131", "4411", "4511", "4722", "7011"],
                    "Travel and transport"),
    "4829": "Money transfer",
    **dict.fromkeys(["4814", "4899", "4900", "6300", "9402", "7276", "8111", "8931"],
                    "Bills, utilities and professional services"),
    **dict.fromkeys(["8011", "8021", "8041", "8043", "8049", "8062", "8099"], "Health"),
    **dict.fromkeys(["5045", "5094", "5192", "5193", "5211", "5251", "5261", "5311", "5621", "5651", "5655",
                     "5661", "5712", "5719", "5722", "5732", "5733", "5932", "5941", "5942", "5947", "5970",
                     "5977", "3132", "3144", "3174", "3504", "3640"], "Retail and home"),
    **dict.fromkeys(["5815", "5816", "7801", "7802", "7832", "7922", "7995", "7996"],
                    "Entertainment and digital"),
    **dict.fromkeys(["7210", "7230", "7349", "7393", "1711"], "Personal and home services"),
    # Real MCCs 3000-3999 are airline, hotel and car-rental codes; mcc_codes.json labels them as
    # manufacturing, so they are kept apart rather than guessed at.
    **dict.fromkeys(["3000", "3001", "3005", "3006", "3007", "3008", "3009", "3058", "3066", "3075", "3256",
                     "3260", "3359", "3387", "3389", "3390", "3393", "3395", "3405", "3509", "3596", "3684",
                     "3730", "3775", "3780", "4214"], "Industrial and wholesale (as labelled)"),
}

CENSUS_REGION = {
    **dict.fromkeys(["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont",
                     "New Jersey", "New York", "Pennsylvania"], "Northeast"),
    **dict.fromkeys(["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota",
                     "Missouri", "Nebraska", "North Dakota", "South Dakota"], "Midwest"),
    **dict.fromkeys(["Delaware", "Florida", "Georgia", "Maryland", "North Carolina", "South Carolina", "Virginia",
                     "District of Columbia", "West Virginia", "Alabama", "Kentucky", "Mississippi", "Tennessee",
                     "Arkansas", "Louisiana", "Oklahoma", "Texas"], "South"),
    **dict.fromkeys(["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah", "Wyoming",
                     "Alaska", "California", "Hawaii", "Oregon", "Washington"], "West"),
}
STATE_ALIASES = {"Washington, D.C.": "District of Columbia"}
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}

BASE_MODEL = {"net_refunds": True, "prepaid": "debit", "money_transfer": "full", "amex_fee": True}
SENSITIVITIES = {
    "base": {},
    "gross_of_refunds": {"net_refunds": False},
    "prepaid_earns_nothing": {"prepaid": "zero"},
    "money_transfer_earns_nothing": {"money_transfer": "zero"},
    "no_amex_fee": {"amex_fee": False},
    "step1_provisional": {"net_refunds": False, "prepaid": "zero"},
}
WINDOW_FLOWS = ["purchases", "spend", "refunds", "refund_amount"]

SCORE_BANDS = [(0, 580, "Under 580"), (580, 670, "580–669"), (670, 740, "670–739"), (740, 800, "740–799"),
               (800, 1000, "800+")]


# ---------- parsing and the revenue model ----------

def money(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(r"[$,]", "", regex=True), errors="coerce").astype(float)


def mm_yyyy_idx(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, format="%m/%Y")
    return d.dt.year * 12 + d.dt.month


def load_rates() -> dict:
    r = pd.read_csv(HANDOUT / "revenue_assumptions.csv").set_index("assumption_key").assumption_value
    return {"credit": r.interchange_credit_bps / 1e4, "debit": r.interchange_debit_bps / 1e4,
            "debit_fixed": r.interchange_debit_fixed_cents / 100, "amex_fee": r.annual_fee_amex_usd}


def interchange(volume, count, card_type, rates: dict, prepaid: str = "debit") -> np.ndarray:
    """Rate-card interchange: credit on volume; debit on volume plus a fee per purchase. Prepaid
    isn't on the rate card: 'debit' charges it at the debit rate, 'zero' earns nothing."""
    card_type = np.asarray(card_type)
    v, n = np.asarray(volume, float), np.asarray(count, float)
    debit = v * rates["debit"] + n * rates["debit_fixed"]
    return np.select([card_type == "Credit", card_type == "Debit", card_type == "Debit (Prepaid)"],
                     [v * rates["credit"], debit, debit if prepaid == "debit" else np.zeros_like(v)], 0.0)


def chargeable(by_card: pd.DataFrame, model: dict) -> tuple[pd.Series, pd.Series]:
    """Volume and purchase count that earn interchange under a revenue model. Netting refunds
    takes their dollars off volume and one per-purchase fee off the count for each refund."""
    sign = 1.0 if model["net_refunds"] else 0.0
    volume = by_card.spend + sign * by_card.refund_amount
    count = by_card.purchases - sign * by_card.refunds
    if model["money_transfer"] == "zero":
        volume = volume - (by_card.mt_spend + sign * by_card.mt_refund_amount)
        count = count - (by_card.mt_purchases - sign * by_card.mt_refunds)
    return volume, count


def amex_fee(brand, card_type, open_idx, expires_idx, fee: float,
             window: tuple[int, int] = WINDOW_IDX) -> np.ndarray:
    """Annual fee on Amex credit cards, pro-rated by months open in the window. The open and
    expiry months both count; cards don't transact after expiry, so the fee stops there."""
    last = np.minimum(np.asarray(expires_idx), window[1])
    months = np.clip(last - np.maximum(np.asarray(open_idx), window[0]) + 1, 0, 12)
    return np.where((np.asarray(brand) == "Amex") & (np.asarray(card_type) == "Credit"), fee * months / 12, 0.0)


# ---------- grouping helpers ----------

def as_of_month_share(birth_year: pd.Series, birth_month: pd.Series, current_age: pd.Series,
                      months: range) -> pd.Series:
    """Share of customers whose current_age is right if the file were taken in each month.
    Day of birth is unknown, so a customer born in the as-of month can go either way."""
    birth = birth_year * 12 + birth_month
    return pd.Series({m: float(((m - birth) // 12 == current_age).mean()) for m in months})


def score_band(score: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=score.index, dtype="string")
    for lo, hi, label in SCORE_BANDS:
        out[(score >= lo) & (score < hi)] = label
    return out


def age_band(age: pd.Series) -> pd.Series:
    return pd.cut(age, [0, 30, 40, 50, 60, 70, 200], right=False,
                  labels=["18–29", "30–39", "40–49", "50–59", "60–69", "70+"]).astype("string")


def quintiles(x: pd.Series, fmt=lambda v: f"{v:,.0f}") -> pd.Series:
    """Five equal-size groups, labelled by the range of values actually in each."""
    codes = pd.qcut(x, 5, labels=False, duplicates="drop")
    rng = x.groupby(codes).agg(["min", "max"])
    names = {c: f"Q{int(c) + 1} ({fmt(r['min'])}–{fmt(r['max'])})" for c, r in rng.iterrows()}
    return codes.map(names).astype("string")


def dollars(v: float) -> str:
    return f"${v / 1000:,.1f}k" if abs(v) >= 1000 else f"${v:,.0f}"


def percent(v: float) -> str:
    return f"{v:.0%}"


def products_label(types: set) -> str:
    names = [n for n, t in [("Credit", "Credit"), ("debit", "Debit"), ("prepaid", "Debit (Prepaid)")] if t in types]
    if not names:
        return "No open card in window"
    label = " + ".join(names)
    label = label[0].upper() + label[1:]
    return label + " only" if len(names) == 1 else label


def brand_label(brands: set) -> str:
    if not brands:
        return "No open card in window"
    if "Amex" in brands:
        return "Any Amex"
    return f"{next(iter(brands))} only" if len(brands) == 1 else "Multi-brand, no Amex"


def eta_squared(values: pd.Series, groups: pd.Series) -> float:
    """Share of the variance in values explained by group means."""
    m = values.mean()
    ss_total = float(((values - m) ** 2).sum())
    t = values.groupby(groups).agg(["size", "mean"])
    return float((t["size"] * (t["mean"] - m) ** 2).sum() / ss_total) if ss_total else 0.0


def adjusted_eta_squared(eta2: float, n: int, k: int) -> float:
    """Eta squared net of what k groups would explain by chance (like adjusted R squared)."""
    return 1 - (1 - eta2) * (n - 1) / (n - k) if n > k else np.nan


def permutation_p(values: pd.Series, groups: pd.Series, n_perm: int = 999, seed: int = 0) -> float:
    """Share of label shuffles whose between-group sum of squares is at least the real one."""
    codes, _ = pd.factorize(groups)
    v = values.to_numpy(float)
    size = np.bincount(codes)

    def between(x):
        return float((np.bincount(codes, weights=x) ** 2 / size).sum())

    real = between(v)
    rng = np.random.default_rng(seed)
    hits = sum(between(rng.permutation(v)) >= real for _ in range(n_perm))
    return (1 + hits) / (n_perm + 1)


# ---------- loading ----------

def load_users() -> pd.DataFrame:
    u = pd.read_csv(HANDOUT / "users_data.csv")
    for c in ["per_capita_income", "yearly_income", "total_debt"]:
        u[c] = money(u[c])
    return u


def load_cards() -> pd.DataFrame:
    c = pd.read_csv(HANDOUT / "cards_data.csv")
    c["credit_limit"] = money(c.credit_limit)
    c["open_idx"] = mm_yyyy_idx(c.acct_open_date)
    c["open_m"] = c.open_idx
    c["expires_idx"] = mm_yyyy_idx(c.expires)
    return c


def states_from_coords(lat: pd.Series, lon: pd.Series) -> pd.DataFrame:
    """Nearest populated place (GeoNames, offline) for each point; admin1 is the state."""
    import reverse_geocoder as rg
    res = rg.search(list(zip(lat.astype(float), lon.astype(float))), mode=1, verbose=False)
    return pd.DataFrame({"country": [r["cc"] for r in res],
                         "state": [STATE_ALIASES.get(r["admin1"], r["admin1"]) for r in res]}, index=lat.index)


def flows(s: pd.DataFrame) -> pd.DataFrame:
    """Purchase and refund counts and dollars per row, plus the money-transfer part of each."""
    buy, mt = s.amt > 0, s.mcc.astype(str).eq("4829")
    f = pd.DataFrame({"purchases": buy.astype(int), "spend": s.amt.where(buy, 0.0),
                      "refunds": (~buy).astype(int), "refund_amount": s.amt.where(~buy, 0.0)}, index=s.index)
    return f.join(f.mul(mt, axis=0).add_prefix("mt_"))


def scan_transactions(cards: pd.DataFrame, user_ids: pd.Index) -> tuple[dict, dict]:
    """One chunked pass: data checks over all rows, and per-customer behaviour in the window."""
    card = cards.set_index("id")
    cols = ["id", "date", "client_id", "card_id", "amount", "use_chip", "merchant_id", "merchant_state", "mcc",
            "errors"]
    reader = pd.read_csv(HANDOUT / "transactions_data.csv", usecols=cols, chunksize=1_000_000,
                         dtype={"date": "string", "amount": "string", "errors": "string", "use_chip": "string",
                                "merchant_state": "string"})
    ids, hist, monthly, by_cat, online, merchants, home, rows = [], [], [], [], [], [], [], []
    cat_monthly, online_monthly = [], []
    checks, errors, use_chip = Counter(), Counter(), Counter()
    first_date, last_date = "9999", "0000"
    for ch in reader:
        ids.append(ch.id.to_numpy())
        month = ch.date.str[:7]
        midx = month.str[:4].astype(int) * 12 + month.str[5:7].astype(int)
        amt = money(ch.amount)
        ok = ch.errors.isna()
        known = ch.card_id.isin(card.index)
        checks["rows"] += len(ch)
        checks["unknown_card"] += int((~known).sum())
        checks["unknown_client"] += int((~ch.client_id.isin(user_ids)).sum())
        checks["client_is_not_card_owner"] += int((ch.card_id.map(card.client_id) != ch.client_id)[known].sum())
        checks["before_card_open_month"] += int((midx < ch.card_id.map(card.open_idx)).sum())
        checks["after_card_expiry_month"] += int((midx > ch.card_id.map(card.expires_idx)).sum())
        checks["amount_unparsed"] += int(amt.isna().sum())
        checks["amount_negative"] += int((amt < 0).sum())
        checks["amount_zero"] += int((amt == 0).sum())
        checks["with_error"] += int((~ok).sum())
        checks["negative_with_error"] += int(((amt < 0) & ~ok).sum())
        checks["mcc_not_in_codes"] += int((~ch.mcc.astype(str).isin(MCC_CATEGORY)).sum())
        errors.update(ch.errors.dropna().value_counts().to_dict())
        use_chip.update(ch.use_chip.value_counts().to_dict())
        first_date, last_date = min(first_date, ch.date.min()), max(last_date, ch.date.max())
        hist.append(ch.groupby("card_id").agg(rows=("id", "size"), first=("date", "min"), last=("date", "max")))
        local = ch[~ch.use_chip.eq("Online Transaction") & ch.merchant_state.isin(STATE_NAMES)]
        home.append(local.groupby(["client_id", "merchant_state"]).size())

        moved = ok & (amt != 0)
        s = ch.loc[moved, ["client_id", "card_id", "merchant_id", "mcc", "date"]].assign(amt=amt[moved], m=midx[moved])
        monthly.append(flows(s).groupby([s.client_id, s.card_id, s.m.rename("month")]).sum())
        rows.append(s[s.m.between(*WINDOW_IDX)].drop(columns="m"))
        pa = ch.loc[ok & (amt > 0), ["client_id", "mcc", "use_chip"]].assign(amt=amt[ok & (amt > 0)],
                                                                             m=midx[ok & (amt > 0)])
        cat_monthly.append(pa.assign(cat=pa.mcc.astype(str).map(MCC_CATEGORY)).groupby(
            ["client_id", pa.m.rename("month"), "cat"]).amt.sum())
        online_monthly.append(pa[pa.use_chip.eq("Online Transaction")].groupby(
            ["client_id", pa.m.rename("month")]).amt.sum())
        in_window = (month >= WINDOW[0]) & (month <= WINDOW[1]) & ok
        p = ch.loc[in_window & (amt > 0)].assign(amt=amt[in_window & (amt > 0)])
        by_cat.append(p.assign(cat=p.mcc.astype(str).map(MCC_CATEGORY)).groupby(["client_id", "cat"]).amt.sum())
        online.append(p[p.use_chip.eq("Online Transaction")].groupby("client_id").amt.sum())
        merchants.append(p[["client_id", "merchant_id"]].drop_duplicates())

    all_ids = np.concatenate(ids)
    checks["duplicate_ids"] = int(len(all_ids) - len(np.unique(all_ids)))
    checks["first_date"], checks["last_date"] = first_date, last_date
    hist = pd.concat(hist).groupby(level=0).agg({"rows": "sum", "first": "min", "last": "max"})
    home = pd.concat(home).groupby(level=[0, 1]).sum().sort_values(ascending=False)
    home = home.reset_index().drop_duplicates("client_id").set_index("client_id").merchant_state.map(STATE_NAMES)
    monthly = pd.concat(monthly).groupby(level=[0, 1, 2]).sum()
    in_window = monthly.index.get_level_values("month").to_series().between(*WINDOW_IDX).to_numpy()
    out = {
        "merchant_home_state": home,
        "card_history": hist,
        "monthly": monthly,
        "category_monthly": pd.concat(cat_monthly).groupby(level=[0, 1, 2]).sum(),
        "online_monthly": pd.concat(online_monthly).groupby(level=[0, 1]).sum(),
        "by_card": monthly[in_window].groupby(level=[0, 1]).sum(),
        "by_category": pd.concat(by_cat).groupby(level=[0, 1]).sum().unstack(fill_value=0),
        "online_spend": pd.concat(online).groupby(level=0).sum(),
        "distinct_merchants": pd.concat(merchants).drop_duplicates().groupby("client_id").size(),
        "window_rows": pd.concat(rows, ignore_index=True),
    }
    checks = dict(checks)
    checks["errors_top"] = dict(errors.most_common(10))
    checks["use_chip"] = dict(use_chip)
    return out, checks


# ---------- step 1: segment every way ----------

def first_signup_fields(signups: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    """Source, landing page and channel of each customer's first signup. Channel uses the
    beliefs work's journey rules: touches go to the customer's next signup."""
    s = flag_acquisitions(signups, cards)
    first = s.drop_duplicates("client_id").set_index("client_id")
    touches, _ = load_linked_touches(HANDOUT / "marketing_touchpoints.csv")
    j = journeys(touches, s)
    j = j[j.signup_id.isin(first.signup_id)].sort_values(["signup_id", "touch_ts", "touch_id"])
    g = j.groupby("client_id").channel
    return pd.DataFrame({
        "first_signup_ts": first.signup_ts,
        "first_signup_kind": first.kind,
        "self_reported_source": first.self_reported_source,
        "signup_landing_page": first.signup_landing_page,
        "channel_last_touch": g.last(),
        "channel_first_touch": g.first(),
    })


def held_in_window(cards: pd.DataFrame) -> pd.DataFrame:
    """Cards open at some point in the window: opened by its end, not expired before its start."""
    return cards[(cards.open_idx <= WINDOW_IDX[1]) & (cards.expires_idx >= WINDOW_IDX[0])].copy()


def with_card_type(by_card: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    return by_card.reset_index().merge(cards[["id", "card_type", "card_brand"]], left_on="card_id",
                                       right_on="id", how="left").drop(columns="id")


def customer_revenue(by_card: pd.DataFrame, cards: pd.DataFrame, rates: dict, model: dict,
                     active: pd.Series) -> pd.DataFrame:
    """Interchange and Amex fees per customer in the window under a revenue model. Fees count
    only for customers active in the window."""
    b = with_card_type(by_card, cards)
    volume, count = chargeable(b, model)
    b["interchange"] = interchange(volume, count, b.card_type, rates, model["prepaid"])
    held = held_in_window(cards)
    held["fee"] = amex_fee(held.card_brand, held.card_type, held.open_idx, held.expires_idx,
                           rates["amex_fee"]) * float(model["amex_fee"])
    out = pd.DataFrame(index=active.index)
    out["interchange"] = b.groupby("client_id").interchange.sum().reindex(out.index, fill_value=0.0)
    out["amex_fee"] = held.groupby("client_id").fee.sum().reindex(out.index, fill_value=0.0).where(active, 0.0)
    out["revenue"] = out.interchange + out.amex_fee
    return out


def build_customers(users, cards, txn, signup_fields, rates) -> tuple[pd.DataFrame, pd.DataFrame]:
    held = held_in_window(cards)
    bc = with_card_type(txn["by_card"], cards)

    c = users.set_index("id")[["current_age", "birth_year", "birth_month", "gender", "latitude", "longitude",
                               "per_capita_income", "yearly_income", "total_debt", "credit_score",
                               "num_credit_cards"]].copy()
    c.index.name = "client_id"
    c = c.join(states_from_coords(c.latitude, c.longitude)).rename(columns={"state": "geocoded_state"})
    c["merchant_home_state"] = txn["merchant_home_state"].reindex(c.index)
    c["state"] = c.geocoded_state.where(c.country == "US", c.merchant_home_state)
    c["region"] = c.state.map(CENSUS_REGION)

    hg = held.groupby("client_id")
    c["cards_held"] = hg.size().reindex(c.index, fill_value=0)
    c["credit_cards_held"] = held[held.card_type == "Credit"].groupby("client_id").size().reindex(c.index, fill_value=0)
    c["products_held"] = hg.card_type.agg(set).reindex(c.index).apply(lambda v: products_label(v if isinstance(v, set) else set()))
    c["brands_held"] = hg.card_brand.agg(set).reindex(c.index).apply(lambda v: brand_label(v if isinstance(v, set) else set()))
    c["total_credit_limit"] = held[held.card_type == "Credit"].groupby("client_id").credit_limit.sum().reindex(c.index)
    c["first_card_month"] = cards.groupby("client_id").open_idx.min().reindex(c.index)

    per = bc.groupby("client_id")
    for col in WINDOW_FLOWS + ["mt_spend"]:
        c[col] = per[col].sum().reindex(c.index, fill_value=0)
    c["credit_spend"] = bc[bc.card_type == "Credit"].groupby("client_id").spend.sum().reindex(c.index, fill_value=0.0)
    c["active"] = c.purchases > 0
    c = c.join(customer_revenue(txn["by_card"], cards, rates, BASE_MODEL, c.active))
    c["online_share"] = (txn["online_spend"].reindex(c.index, fill_value=0.0) / c.spend).where(c.active)
    c["distinct_merchants"] = txn["distinct_merchants"].reindex(c.index)
    cats = txn["by_category"]
    c["main_category"] = cats[cats.sum(axis=1) > 0].idxmax(axis=1).reindex(c.index).where(c.active)
    c["ever_transacted"] = c.index.isin(txn["card_history"].index.map(cards.set_index("id").client_id))
    c = c.join(signup_fields)

    na = "No signup record"
    groups = pd.DataFrame(index=c.index)
    groups["age"] = age_band(c.current_age)
    groups["state"] = c.state.fillna("Unresolved location")
    groups["region"] = c.region.fillna("Unresolved location")
    groups["yearly_income"] = quintiles(c.yearly_income, dollars)
    debt = quintiles(c.total_debt.where(c.total_debt > 0), dollars)
    groups["total_debt"] = debt.where(c.total_debt > 0, "No debt")
    groups["credit_score"] = score_band(c.credit_score)
    groups["num_credit_cards"] = c.num_credit_cards.clip(upper=6).astype(int).astype(str).replace("6", "6+")
    groups["card_type"] = c.products_held
    groups["card_brand"] = c.brands_held
    lim = quintiles(c.total_credit_limit.where(c.credit_cards_held > 0), dollars)
    groups["credit_limit"] = lim.where(c.credit_cards_held > 0, "No credit card")
    none = "No purchases in window"
    groups["transaction_count"] = quintiles(c.purchases.where(c.active)).fillna(none)
    groups["transaction_amount"] = quintiles(c.spend.where(c.active), dollars).fillna(none)
    groups["merchant_category"] = c.main_category.fillna(none)
    groups["online_share"] = quintiles(c.online_share, percent).fillna(none)
    groups["distinct_merchants"] = quintiles(c.distinct_merchants.where(c.active)).fillna(none)
    groups["self_reported_source"] = c.self_reported_source.fillna(na)
    groups["signup_landing_page"] = c.signup_landing_page.fillna(na)
    has_signup = c.first_signup_ts.notna()
    groups["channel_last_touch"] = c.channel_last_touch.where(has_signup, na).fillna("No linked touches")
    groups["channel_first_touch"] = c.channel_first_touch.where(has_signup, na).fillna("No linked touches")
    return c, groups


DIMENSIONS = [
    # name, known at acquisition?, labels left out of the separation measure
    ("age", "Yes, roughly (age is a snapshot)", []),
    ("region", "Yes", ["Unresolved location"]),
    ("state", "Yes", ["Unresolved location"]),
    ("yearly_income", "Yes", []),
    ("total_debt", "Partly (snapshot)", []),
    ("credit_score", "Yes", []),
    ("num_credit_cards", "No: counts every card in the file, any type or date", []),
    ("card_type", "No: products held in the window", ["No open card in window"]),
    ("card_brand", "No: brands held in the window", ["No open card in window"]),
    ("credit_limit", "Partly: each limit is set at approval, the total grows with cards", []),
    ("transaction_count", "No: consequence", []),
    ("transaction_amount", "No: consequence", []),
    ("merchant_category", "No: consequence", []),
    ("online_share", "No: consequence", []),
    ("distinct_merchants", "No: consequence", []),
    ("self_reported_source", "Yes", ["No signup record"]),
    ("signup_landing_page", "Yes", ["No signup record"]),
    ("channel_last_touch", "Yes", ["No signup record", "No linked touches"]),
    ("channel_first_touch", "Yes", ["No signup record", "No linked touches"]),
]
ORDERED = {"credit_score": [b[2] for b in SCORE_BANDS]}
BY_SIZE = {"region", "state", "card_type", "card_brand", "merchant_category", "self_reported_source",
           "signup_landing_page", "channel_last_touch", "channel_first_touch"}


def segment_table(c: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    total_revenue = c.loc[c.active, "revenue"].sum()
    rows = []
    for dim, known, _ in DIMENSIONS:
        for label, idx in groups.groupby(dim, dropna=False).groups.items():
            x = c.loc[idx]
            a = x[x.active]
            kinds = x.first_signup_kind.dropna()
            rows.append({
                "dimension": dim, "known_at_acquisition": known, "group": label,
                "customers": len(x), "share_of_customers": len(x) / len(c),
                "active_in_window": len(a), "never_transacted": int((~x.ever_transacted).sum()),
                "revenue_mean": a.revenue.mean(), "revenue_median": a.revenue.median(),
                "spend_mean": a.spend.mean(), "purchases_mean": a.purchases.mean(),
                "credit_share_of_spend": a.credit_spend.sum() / a.spend.sum() if len(a) else np.nan,
                "share_of_revenue": a.revenue.sum() / total_revenue,
                "first_signup_was_new_customer": (kinds == "acquisition").mean() if len(kinds) else np.nan,
            })
    t = pd.DataFrame(rows)
    order = []
    for dim, _, _ in DIMENSIONS:
        d = t[t.dimension == dim]
        if dim in ORDERED:
            d = d.set_index("group").reindex([g for g in ORDERED[dim] if g in set(d.group)]).reset_index()
        elif dim in BY_SIZE:
            d = d.sort_values("customers", ascending=False)
        else:
            d = d.sort_values("group")
        order.append(d)
    return pd.concat(order, ignore_index=True)[t.columns]


def separation_table(c: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    rows = []
    active = c.active
    for dim, known, excluded in DIMENSIONS:
        g = groups.loc[active, dim]
        use = ~g.isin(excluded)
        v, g = c.loc[active, "revenue"][use], g[use]
        means = v.groupby(g).agg(["size", "mean"])
        big = means[means["size"] >= MIN_GROUP]
        rows.append({
            "dimension": dim, "known_at_acquisition": known,
            "active_customers_used": int(use.sum()), "coverage_of_active": float(use.mean()),
            "groups": len(means), "groups_with_30_plus": len(big),
            "eta_squared": eta_squared(v, g),
            "eta_squared_adjusted": adjusted_eta_squared(eta_squared(v, g), len(v), len(means)),
            "permutation_p": permutation_p(v, g),
            "highest_group": big["mean"].idxmax() if len(big) else None,
            "highest_mean": big["mean"].max() if len(big) else np.nan,
            "lowest_group": big["mean"].idxmin() if len(big) else None,
            "lowest_mean": big["mean"].min() if len(big) else np.nan,
        })
    t = pd.DataFrame(rows)
    t["high_to_low"] = t.highest_mean / t.lowest_mean
    return t.sort_values("eta_squared_adjusted", ascending=False)


def card_level_table(cards: pd.DataFrame, txn: dict, rates: dict) -> pd.DataFrame:
    held = held_in_window(cards).set_index("id")
    w = txn["by_card"].reset_index("client_id", drop=True).reindex(held.index).fillna(0)
    held = held.join(w)
    held["active"] = held.purchases > 0
    volume, count = chargeable(held, BASE_MODEL)
    held["revenue"] = interchange(volume, count, held.card_type, rates, BASE_MODEL["prepaid"]) + np.where(
        held.active, amex_fee(held.card_brand, held.card_type, held.open_idx, held.expires_idx, rates["amex_fee"]),
        0.0)
    held["limit_group"] = held.groupby("card_type").credit_limit.transform(lambda s: quintiles(s, dollars))
    rows = []
    for dim in ["card_type", "card_brand", "limit_group"]:
        keys = ["card_type", dim] if dim != "card_type" else ["card_type"]
        for k, x in held.groupby(keys):
            a = x[x.active]
            k = k if isinstance(k, tuple) else (k,)
            rows.append({"dimension": dim, "card_type": k[0], "group": k[-1], "cards": len(x),
                         "active_in_window": len(a), "revenue_per_active_card": a.revenue.mean(),
                         "spend_per_active_card": a.spend.mean(), "purchases_per_active_card": a.purchases.mean()})
    return pd.DataFrame(rows)


def data_checks(users, cards, c, txn_checks, as_of, card_history) -> dict:
    exp = cards[cards.expires_idx < WINDOW_IDX[0]].set_index("id")
    last = card_history["last"].reindex(exp.index).dropna()
    gap = exp.expires_idx.reindex(last.index) - (last.str[:4].astype(int) * 12 + last.str[5:7].astype(int))
    expired_gap = {"cards_with_transactions": int(len(gap)), "median": float(gap.median()),
                   "share_within_2_months": float((gap <= 2).mean())}
    credit_in_cards = cards[cards.card_type == "Credit"].groupby("client_id").size().reindex(users.id, fill_value=0)
    all_cards = cards.groupby("client_id").size().reindex(users.id, fill_value=0)
    ratio = users.yearly_income / users.per_capita_income
    best = as_of[as_of == as_of.max()]
    return {
        "users": {
            "rows": len(users), "id_unique": bool(users.id.is_unique),
            "nulls": {k: int(v) for k, v in users.isna().sum().items() if v},
            "age_range": [int(users.current_age.min()), int(users.current_age.max())],
            "credit_score_range": [int(users.credit_score.min()), int(users.credit_score.max())],
            "zero_debt": int((users.total_debt == 0).sum()),
            "as_of_month_best": [f"{(m - 1) // 12}-{(m - 1) % 12 + 1:02d}" for m in best.index],
            "as_of_month_share_matching": float(best.iloc[0]),
            "yearly_over_per_capita_income": {"median": float(ratio.median()),
                                              "share_within_1pct_of_median": float(((ratio / ratio.median() - 1).abs() < 0.01).mean())},
            "num_credit_cards_equals_credit_cards_in_cards_table": float((users.num_credit_cards.to_numpy() == credit_in_cards.to_numpy()).mean()),
            "num_credit_cards_equals_all_cards_in_cards_table": float((users.num_credit_cards.to_numpy() == all_cards.to_numpy()).mean()),
            "geocoded_outside_us": c.loc[c.country != "US", ["latitude", "longitude", "geocoded_state", "state"]].reset_index().to_dict(orient="records"),
            "states": int(c.state.nunique()),
            "geocoded_state_equals_main_in_person_merchant_state": float(
                (c.geocoded_state == c.merchant_home_state)[c.merchant_home_state.notna()].mean()),
            "customers_with_in_person_merchant_state": int(c.merchant_home_state.notna().sum()),
        },
        "cards": {
            "rows": len(cards), "id_unique": bool(cards.id.is_unique),
            "card_number_unique": bool(cards.card_number.is_unique),
            "owner_not_in_users": int((~cards.client_id.isin(users.id)).sum()),
            "users_without_cards": int((~users.id.isin(cards.client_id)).sum()),
            "credit_limit_zero_by_type": cards[cards.credit_limit == 0].card_type.value_counts().to_dict(),
            "opened_after_oct_2019": int((cards.open_idx > WINDOW_IDX[1]).sum()),
            "expired_before_window": int((cards.expires_idx < WINDOW_IDX[0]).sum()),
            "open_in_window": int(len(held_in_window(cards))),
            "expired_before_window_last_txn_months_before_expiry": expired_gap,
            "open_range": [cards.acct_open_date.iloc[cards.open_idx.argmin()], cards.acct_open_date.iloc[cards.open_idx.argmax()]],
        },
        "transactions": txn_checks,
        "customers": {
            "active_in_window": int(c.active.sum()),
            "never_transacted": int((~c.ever_transacted).sum()),
            "never_transacted_first_card_by_oct_2019": int((~c.ever_transacted & (c.first_card_month <= WINDOW_IDX[1])).sum()),
            "transacted_before_but_not_in_window": int((c.ever_transacted & ~c.active).sum()),
            "with_signup_record": int(c.first_signup_ts.notna().sum()),
            "with_signup_record_and_active": int((c.first_signup_ts.notna() & c.active).sum()),
            "first_signup_kind": c.first_signup_kind.value_counts().to_dict(),
            "first_signup_kind_among_active": c.loc[c.active].first_signup_kind.value_counts().to_dict(),
            "revenue_total": float(c.revenue.sum()), "amex_fee_total": float(c.amex_fee.sum()),
            "refund_amount_total": float(c.refund_amount.sum()), "spend_total": float(c.spend.sum()),
        },
    }


def plot_separation(sep: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = sep.sort_values("eta_squared_adjusted")
    colour = s.known_at_acquisition.map(lambda k: "tab:blue" if k.startswith("Yes") else
                                        "tab:orange" if k.startswith("Partly") else "lightgrey")
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.barh(s.dimension.str.replace("_", " "), s.eta_squared_adjusted.clip(lower=0) * 100, color=colour)
    ax.set_xlabel("Share of revenue variance explained by the groups, net of chance (%)")
    ax.set_title("How sharply each dimension separates customer revenue\n(active customers, Nov 2018 – Oct 2019)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="tab:blue", label="known at acquisition"),
                       Patch(color="tab:orange", label="partly known"),
                       Patch(color="lightgrey", label="consequence of value")], loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_dimension_separation.png", dpi=150)
    plt.close(fig)


@lru_cache(maxsize=1)
def prepare() -> dict:
    """Load, scan transactions once and build the customer table; shared by every step."""
    rates = load_rates()
    users, cards = load_users(), load_cards()
    signups = pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"])
    txn, txn_checks = scan_transactions(cards, pd.Index(users.id))
    c, groups = build_customers(users, cards, txn, first_signup_fields(signups, cards), rates)
    return {"rates": rates, "users": users, "cards": cards, "txn": txn, "txn_checks": txn_checks,
            "c": c, "groups": groups}


def step1() -> dict:
    p = prepare()
    users, cards, c, groups, txn = p["users"], p["cards"], p["c"], p["groups"], p["txn"]
    as_of = as_of_month_share(users.birth_year, users.birth_month, users.current_age,
                              range(2015 * 12 + 1, 2026 * 12 + 1))
    segments = segment_table(c, groups)
    separation = separation_table(c, groups)
    card_level = card_level_table(cards, txn, p["rates"])

    c.join(groups.add_prefix("group_")).to_csv(OUT / "step1_customers.csv")
    segments.to_csv(OUT / "step1_segments.csv", index=False)
    separation.to_csv(OUT / "step1_separation.csv", index=False)
    card_level.to_csv(OUT / "step1_card_level.csv", index=False)
    checks = data_checks(users, cards, c, p["txn_checks"], as_of, txn["card_history"])
    txn["card_history"].to_csv(OUT / "step1_card_history.csv")
    (OUT / "step1_checks.json").write_text(json.dumps(checks, indent=2, default=str))
    PLOTS.mkdir(exist_ok=True)
    plot_separation(separation)
    return {"checks": checks, "separation": separation.round(3).to_dict(orient="records")}


# ---------- step 2: the revenue model ----------

def refund_profile(rows: pd.DataFrame, cards: pd.DataFrame) -> dict:
    """What the negative amounts in the window are: where they happen, how big they are, and how
    many exactly cancel an earlier purchase on the same card at the same merchant."""
    mcc = json.loads((HANDOUT / "mcc_codes.json").read_text())
    neg, pos = rows[rows.amt < 0], rows[rows.amt > 0]
    k = ["card_id", "merchant_id"]
    p = pos.assign(a=pos.amt.round(2))[k + ["a", "date"]].rename(columns={"date": "purchase_date"})
    n = neg.assign(a=(-neg.amt).round(2))[k + ["a", "date"]].reset_index()
    m = n.merge(p, on=k + ["a"])
    matched = m.loc[m.purchase_date < m.date, "index"].nunique()
    ctype = rows.card_id.map(cards.set_index("id").card_type)
    by_type = (-neg.amt.groupby(ctype[neg.index]).sum() / pos.amt.groupby(ctype[pos.index]).sum())
    return {
        "negative_rows": int(len(neg)), "share_of_rows": float(len(neg) / len(rows)),
        "negative_dollars_over_purchase_dollars": float(-neg.amt.sum() / pos.amt.sum()),
        "negative_dollars_over_purchase_dollars_by_card_type": by_type.round(4).to_dict(),
        "top_merchant_categories_share_of_negative_rows": neg.mcc.astype(str).map(mcc).value_counts(
            normalize=True).head(4).round(3).to_dict(),
        "share_matching_an_earlier_purchase_same_card_merchant_amount": float(matched / len(neg)),
        "median_negative": float(neg.amt.median()), "median_purchase": float(pos.amt.median()),
        "money_transfer_share_of_purchase_dollars": float(
            pos.loc[pos.mcc.astype(str).eq("4829"), "amt"].sum() / pos.amt.sum()),
        "money_transfer_negative_rows": int(neg.mcc.astype(str).eq("4829").sum()),
    }


def reconciliation(txn: dict, cards: pd.DataFrame, rates: dict, active: pd.Series) -> pd.DataFrame:
    """From gross interchange to base revenue, one assumption at a time."""
    steps = [
        ("Interchange on gross purchases, prepaid earning nothing",
         {"net_refunds": False, "prepaid": "zero", "amex_fee": False}),
        ("Plus prepaid at the debit rate", {"net_refunds": False, "amex_fee": False}),
        ("Less refunds and reversals", {"amex_fee": False}),
        ("Plus Amex annual fees (base revenue)", {}),
    ]
    rows, prev = [], 0.0
    for label, change in steps:
        total = float(customer_revenue(txn["by_card"], cards, rates, {**BASE_MODEL, **change}, active).revenue.sum())
        rows.append({"step": label, "change": total - prev, "running_total": total})
        prev = total
    return pd.DataFrame(rows)


def by_card_type(txn: dict, cards: pd.DataFrame, rates: dict) -> pd.DataFrame:
    b = with_card_type(txn["by_card"], cards)
    for name, model in [("gross", {**BASE_MODEL, "net_refunds": False}), ("base", BASE_MODEL)]:
        v, n = chargeable(b, model)
        b[f"interchange_{name}"] = interchange(v, n, b.card_type, rates, model["prepaid"])
    t = b.groupby("card_type")[["purchases", "spend", "refunds", "refund_amount", "mt_spend",
                                "interchange_gross", "interchange_base"]].sum()
    t["refunds_over_spend"] = -t.refund_amount / t.spend
    t["interchange_per_100_spend"] = 100 * t.interchange_base / t.spend
    t["share_of_interchange"] = t.interchange_base / t.interchange_base.sum()
    return t


def sensitivity_tables(c: pd.DataFrame, groups: pd.DataFrame, txn: dict, cards: pd.DataFrame,
                       rates: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Each alternative assumption: total revenue, and whether it reorders the groups that
    separated value in step 1 (groups with 30+ active customers)."""
    dims = ["card_type", "credit_limit", "yearly_income", "card_brand"]
    act = c.active
    rows, totals = [], []
    for name, change in SENSITIVITIES.items():
        r = customer_revenue(txn["by_card"], cards, rates, {**BASE_MODEL, **change}, act).revenue[act]
        totals.append({"variant": name, "total_revenue": float(r.sum()), "mean_per_active_customer": float(r.mean())})
        for d in dims:
            m = r.groupby(groups.loc[act, d]).agg(["size", "mean"])
            m = m[m["size"] >= MIN_GROUP].sort_values("mean", ascending=False)
            for rank, (grp, row) in enumerate(m.iterrows(), 1):
                rows.append({"variant": name, "dimension": d, "group": grp, "active_customers": int(row["size"]),
                             "revenue_mean": float(row["mean"]), "rank": rank})
    groups_t = pd.DataFrame(rows)
    base_rank = groups_t[groups_t.variant == "base"].set_index(["dimension", "group"])["rank"]
    groups_t["base_rank"] = groups_t.set_index(["dimension", "group"]).index.map(base_rank)
    same = groups_t.assign(same=groups_t["rank"] == groups_t.base_rank).groupby(["variant", "dimension"]).same.all()
    totals_t = pd.DataFrame(totals).set_index("variant")
    totals_t["change_vs_base"] = totals_t.total_revenue / totals_t.loc["base", "total_revenue"] - 1
    totals_t = totals_t.join(same.unstack().add_prefix("same_order_"))
    return totals_t.reset_index(), groups_t


def step2() -> dict:
    p = prepare()
    c, groups, txn, cards, rates = p["c"], p["groups"], p["txn"], p["cards"], p["rates"]
    recon = reconciliation(txn, cards, rates, c.active)
    types = by_card_type(txn, cards, rates)
    totals, group_ranks = sensitivity_tables(c, groups, txn, cards, rates)
    b = with_card_type(txn["by_card"], cards)
    volume, _ = chargeable(b, BASE_MODEL)
    out = {
        "model": BASE_MODEL,
        "rates": rates,
        "refunds": refund_profile(txn["window_rows"], cards),
        "reconciliation": recon.round(2).to_dict(orient="records"),
        "by_card_type": types.round(4).reset_index().to_dict(orient="records"),
        "cards_with_negative_net_volume": int((volume < 0).sum()),
        "sensitivities": totals.round(4).to_dict(orient="records"),
    }
    (OUT / "step2_revenue_model.json").write_text(json.dumps(plain(out), indent=2))
    totals.to_csv(OUT / "step2_sensitivity.csv", index=False)
    group_ranks.to_csv(OUT / "step2_sensitivity_by_group.csv", index=False)
    return out


# ---------- step 3: new-customer value by day-one and held-today segments ----------

COHORT = (2010 * 12 + 1, 2018 * 12 + 12)
TENURE_YEARS = 3
TODAY_IDX = WINDOW_IDX[1]
N_BOOT = 2000


def tenure_year(month_idx, first_idx) -> np.ndarray:
    """1, 2 or 3 for months in the customer's first three years (month 1 is the first-card month), else 0."""
    t = np.asarray(month_idx) - np.asarray(first_idx)
    return np.where((t >= 0) & (t < 12 * TENURE_YEARS), t // 12 + 1, 0)


def full_years_observed(first_idx, last_idx: int = WINDOW_IDX[1]) -> np.ndarray:
    return np.clip((last_idx - np.asarray(first_idx) + 1) // 12, 0, TENURE_YEARS)


def months_overlap(a0, a1, b0, b1) -> np.ndarray:
    return np.clip(np.minimum(a1, b1) - np.maximum(a0, b0) + 1, 0, None)


def monthly_card_revenue(txn: dict, cards: pd.DataFrame, rates: dict) -> pd.DataFrame:
    """Interchange per card per month under the base model."""
    m = txn["monthly"].reset_index().merge(cards[["id", "card_type"]], left_on="card_id", right_on="id",
                                           how="left").drop(columns="id")
    volume, count = chargeable(m, BASE_MODEL)
    m["interchange"] = interchange(volume, count, m.card_type, rates, BASE_MODEL["prepaid"])
    return m[["client_id", "card_id", "month", "card_type", "interchange", "spend", "purchases"]]


def amex_fee_by_tenure_year(cards: pd.DataFrame, first: pd.Series, fee: float) -> pd.DataFrame:
    """Amex fee accrued at fee/12 for each month an Amex credit card is open, by tenure year."""
    a = cards[(cards.card_brand == "Amex") & (cards.card_type == "Credit") & cards.client_id.isin(first.index)].copy()
    f = a.client_id.map(first)
    out = {}
    for k in range(1, TENURE_YEARS + 1):
        lo, hi = f + 12 * (k - 1), f + 12 * k - 1
        a[f"year{k}"] = months_overlap(a.open_idx, a.expires_idx, lo, hi) * fee / 12
        out[f"year{k}"] = a.groupby("client_id")[f"year{k}"].sum()
    return pd.DataFrame(out).reindex(first.index, fill_value=0.0).fillna(0.0)


def customer_years(c: pd.DataFrame, cards: pd.DataFrame, txn: dict, rates: dict) -> pd.DataFrame:
    """Revenue in each of the first three years for customers whose first card opened in the cohort
    window. Years not fully observed by Oct 2019 are left blank."""
    first = c.first_card_month[c.first_card_month.between(*COHORT)]
    rev = monthly_card_revenue(txn, cards, rates)
    rev = rev[rev.client_id.isin(first.index)]
    rev["year"] = tenure_year(rev.month, rev.client_id.map(first))
    inter = rev[rev.year > 0].pivot_table(index="client_id", columns="year", values="interchange", aggfunc="sum")
    inter = inter.reindex(index=first.index, columns=range(1, TENURE_YEARS + 1)).fillna(0.0)
    inter.columns = [f"year{k}" for k in inter.columns]
    fees = amex_fee_by_tenure_year(cards, first, rates["amex_fee"])
    out = inter + fees
    observed = pd.Series(full_years_observed(first), index=first.index)
    for k in range(1, TENURE_YEARS + 1):
        out[f"year{k}"] = out[f"year{k}"].where(observed >= k)
    out["value_3yr"] = out[[f"year{k}" for k in range(1, TENURE_YEARS + 1)]].sum(axis=1, min_count=TENURE_YEARS)
    out.insert(0, "first_card_month", first)
    out.insert(1, "cohort_year", (first - 1) // 12)
    out.insert(2, "years_observed", observed)
    out.insert(3, "has_data", c.ever_transacted.reindex(first.index))
    for col in out.columns[4:]:
        out[col] = out[col].where(out.has_data)
    return out


def card_first_year(cards: pd.DataFrame, txn: dict, rates: dict, with_data: pd.Index,
                    card_types: tuple = ("Credit",)) -> pd.DataFrame:
    """First-year revenue of every card of the given types opened 2010-2017 by a customer with
    transaction data: interchange in its first 12 months plus the Amex fee for months open."""
    cc = cards[cards.card_type.isin(card_types) & cards.open_idx.between(2010 * 12 + 1, 2017 * 12 + 12)
               & cards.client_id.isin(with_data)].set_index("id")
    rev = monthly_card_revenue(txn, cards, rates)
    rev = rev[rev.card_id.isin(cc.index)]
    rev = rev[(rev.month >= rev.card_id.map(cc.open_idx)) & (rev.month <= rev.card_id.map(cc.open_idx) + 11)]
    cc["first_year_interchange"] = rev.groupby("card_id").interchange.sum().reindex(cc.index, fill_value=0.0)
    cc["first_year_fee"] = np.where((cc.card_brand == "Amex") & (cc.card_type == "Credit"), months_overlap(
        cc.open_idx, cc.expires_idx, cc.open_idx, cc.open_idx + 11) * rates["amex_fee"] / 12, 0.0)
    cc["first_year_revenue"] = cc.first_year_interchange + cc.first_year_fee
    return cc[["client_id", "card_type", "card_brand", "credit_limit", "open_idx", "first_year_revenue"]]


def best_split(x: pd.Series, y: pd.Series, min_share: float = 0.2, step: float = 500.0) -> tuple[float, pd.DataFrame]:
    """The single threshold on x that explains the most variance in y, searched in steps with at
    least min_share of points on each side."""
    lo, hi = x.quantile(min_share), x.quantile(1 - min_share)
    m = y.mean()
    rows = []
    for t in np.arange(np.ceil(lo / step) * step, hi + step / 2, step):
        above = x >= t
        n1, n0 = int(above.sum()), int((~above).sum())
        ss = n1 * (y[above].mean() - m) ** 2 + n0 * (y[~above].mean() - m) ** 2
        rows.append({"cut": float(t), "above": n1, "below": n0, "between_ss": float(ss),
                     "mean_above": float(y[above].mean()), "mean_below": float(y[~above].mean())})
    t = pd.DataFrame(rows)
    return float(t.loc[t.between_ss.idxmax(), "cut"]), t


def holdings(cards: pd.DataFrame, at: pd.Series) -> pd.DataFrame:
    """Product, highest credit limit and raw product mix of the cards selected by `at`."""
    sel = cards[at]
    g = sel.groupby("client_id")
    types = g.card_type.agg(set)
    product = types.map(lambda s: "Credit" if "Credit" in s else "Debit or prepaid")
    raw = types.map(lambda s: "Credit" if "Credit" in s else "Debit" if "Debit" in s else "Prepaid")
    limit = sel[sel.card_type == "Credit"].groupby("client_id").credit_limit.max()
    return pd.DataFrame({"product": product, "product_raw": raw, "max_credit_limit": limit})


def day_one_and_today(cards: pd.DataFrame, first: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Day one: cards opened in the customer's first-card month. Today: cards open in Oct 2019."""
    cohort = cards[cards.client_id.isin(first.index)]
    day1 = holdings(cohort, cohort.open_idx == cohort.client_id.map(first))
    today = holdings(cohort, (cohort.open_idx <= TODAY_IDX) & (cohort.expires_idx >= TODAY_IDX))
    return day1.reindex(first.index), today.reindex(first.index)


def scheme_labels(h: pd.DataFrame, income: pd.Series, cut: float, income_cut: float) -> pd.DataFrame:
    """The four candidate schemes: product; product + credit limit; product + income;
    credit split by limit and debit-or-prepaid split by income."""
    base = h["product"].fillna("No open card")
    credit = base.eq("Credit")
    other = base.eq("Debit or prepaid")
    lim = np.where(h.max_credit_limit >= cut, f"limit {dollars(cut)}+", f"limit under {dollars(cut)}")
    inc = np.where(income >= income_cut, f"income {dollars(income_cut)}+", f"income under {dollars(income_cut)}")
    with_inc = base.where(~(credit | other), base + ", " + pd.Series(inc, index=base.index))
    return pd.DataFrame({
        "product": base,
        "product_limit": base.where(~credit, "Credit, " + pd.Series(lim, index=base.index)),
        "product_income": with_inc,
        "product_limit_income": base.where(~credit, "Credit, " + pd.Series(lim, index=base.index)).where(
            ~other, with_inc),
    })


def bootstrap_ci(v: pd.Series, n: int = N_BOOT, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    x = v.to_numpy(float)
    means = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def rank_stability(v: pd.Series, g: pd.Series, n: int = N_BOOT, seed: int = 0) -> float:
    """Share of bootstrap resamples (of customers) that keep the full-sample order of group means."""
    order = v.groupby(g).mean().sort_values(ascending=False).index.tolist()
    codes = pd.Categorical(g, categories=order).codes
    x = v.to_numpy(float)
    rng = np.random.default_rng(seed)
    keep = 0
    for _ in range(n):
        i = rng.integers(0, len(x), len(x))
        s = np.bincount(codes[i], weights=x[i], minlength=len(order))
        k = np.bincount(codes[i], minlength=len(order))
        if (k > 0).all():
            m = s / k
            keep += bool(np.all(np.diff(m) < 0))
    return keep / n


def step3() -> dict:
    p = prepare()
    c, cards, txn, rates = p["c"], p["cards"], p["txn"], p["rates"]
    years = customer_years(c, cards, txn, rates)
    with_data = years.index[years.has_data]

    card_fy = card_first_year(cards, txn, rates, c.index[c.ever_transacted])
    cut, split_curve = best_split(card_fy.credit_limit, card_fy.first_year_revenue)
    card_fy["limit_decile"] = pd.qcut(card_fy.credit_limit, 10, labels=False, duplicates="drop") + 1
    deciles = card_fy.groupby("limit_decile").agg(cards=("credit_limit", "size"), limit_min=("credit_limit", "min"),
                                                  limit_max=("credit_limit", "max"),
                                                  first_year_revenue=("first_year_revenue", "mean"))

    first = years.first_card_month
    day1, today = day_one_and_today(cards, first)
    income = c.yearly_income.reindex(first.index)
    income_cut = float(income[with_data].median())
    versions = {"day_one": scheme_labels(day1, income, cut, income_cut),
                "held_today": scheme_labels(today, income, cut, income_cut)}

    value = years.value_3yr
    scored = value.notna()
    schemes, seg_rows = [], []
    for version, labels in versions.items():
        for scheme in labels.columns:
            g_all = labels[scheme]
            use = scored & g_all.ne("No open card")
            v, g = value[use], g_all[use]
            e = eta_squared(v, g)
            sizes = g.value_counts()
            schemes.append({"version": version, "scheme": scheme, "customers": int(use.sum()), "groups": len(sizes),
                            "smallest_group": int(sizes.min()), "eta_squared": e,
                            "eta_squared_adjusted": adjusted_eta_squared(e, len(v), len(sizes)),
                            "permutation_p": permutation_p(v, g), "rank_stability": rank_stability(v, g)})
            for grp in g_all.dropna().unique():
                in_g = g_all.eq(grp)
                d = years[in_g & years.has_data]
                v3 = d.value_3yr.dropna()
                lo, hi = bootstrap_ci(v3) if len(v3) > 1 else (np.nan, np.nan)
                seg_rows.append({
                    "version": version, "scheme": scheme, "group": grp,
                    "cohort_customers": int(in_g.sum()), "with_data": len(d), "no_data": int((in_g & ~years.has_data).sum()),
                    "with_3_years": len(v3), "year1": d.year1.mean(), "year2": d.year2.mean(), "year3": d.year3.mean(),
                    "value_3yr": v3.mean(), "value_3yr_low": lo, "value_3yr_high": hi, "value_3yr_median": v3.median(),
                    "share_of_cohort_value": v3.sum() / value.sum(),
                })
    schemes = pd.DataFrame(schemes).sort_values(["version", "eta_squared_adjusted"], ascending=[True, False])
    segments = pd.DataFrame(seg_rows).sort_values(["version", "scheme", "value_3yr"], ascending=[True, True, False])

    d1, td = versions["day_one"], versions["held_today"]
    migration = pd.crosstab(d1.product_limit_income[with_data], td.product_limit_income[with_data],
                            rownames=["day_one"], colnames=["held_today"], margins=True)
    raw_mix = pd.crosstab(day1.product_raw[with_data], today.product_raw.fillna("No open card")[with_data],
                          rownames=["day_one"], colnames=["held_today"], margins=True)

    customer_out = years.join(day1.add_prefix("day1_")).join(today.add_prefix("today_")).join(
        d1.add_prefix("day1_scheme_")).join(td.add_prefix("today_scheme_"))
    customer_out["yearly_income"] = income
    customer_out.to_csv(OUT / "step3_customer_years.csv")
    schemes.to_csv(OUT / "step3_schemes.csv", index=False)
    segments.to_csv(OUT / "step3_segment_value.csv", index=False)
    migration.to_csv(OUT / "step3_migration.csv")
    split_curve.to_csv(OUT / "step3_limit_split_search.csv", index=False)
    deciles.to_csv(OUT / "step3_card_first_year_by_limit_decile.csv")
    summary = {
        "cohort": {"customers": len(years), "with_data": int(years.has_data.sum()),
                   "with_3_years": int(value.notna().sum()),
                   "by_cohort_year": pd.crosstab(years.cohort_year, years.has_data).to_dict()},
        "credit_limit_cut": cut, "income_cut": income_cut,
        "limit_cut_sample": {"credit_cards": len(card_fy), "customers": int(card_fy.client_id.nunique())},
        "day_one_raw_product_with_data": day1.product_raw[with_data].value_counts().to_dict(),
        "raw_product_day_one_to_today": raw_mix.to_dict(),
        "mean_value_3yr": float(value.mean()),
    }
    (OUT / "step3_summary.json").write_text(json.dumps(plain(summary), indent=2, default=str))
    plot_step3(segments)
    return {"summary": summary, "schemes": schemes.round(3).to_dict(orient="records")}


def plot_step3(segments: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharex=True)
    for ax, (version, title) in zip(axes, [("day_one", "By the card opened on day one"),
                                           ("held_today", "By what they hold in Oct 2019")]):
        s = segments[(segments.version == version) & (segments.scheme == "product_limit_income")
                     & segments.value_3yr.notna() & segments.group.ne("No open card")].sort_values("value_3yr")
        err = [s.value_3yr - s.value_3yr_low, s.value_3yr_high - s.value_3yr]
        ax.barh(s.group + "  (n=" + s.with_3_years.astype(str) + ")", s.value_3yr, xerr=err, color="tab:blue",
                alpha=0.8, capsize=3)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("3-year revenue per customer ($, 95% CI)")
    fig.suptitle("New customers' first three years of revenue (customers acquired 2010–2017)")
    fig.tight_layout(w_pad=3)
    fig.savefig(PLOTS / "q1_new_customer_value_by_segment.png", dpi=150)
    plt.close(fig)


# ---------- step 4: who each segment is, how big it is, and its first-year value ----------

SEGMENT_SCHEME = "product_limit"
AGE_BANDS = ([0, 30, 40, 50, 60, 200], ["Under 30", "30–39", "40–49", "50–59", "60+"])


def age_at(month_idx, birth_year, birth_month) -> np.ndarray:
    """Completed years of age in a month (day of birth unknown, so the birth month counts as reached)."""
    return (np.asarray(month_idx) - (np.asarray(birth_year) * 12 + np.asarray(birth_month))) // 12


def auc(score: pd.Series, positive: pd.Series) -> float:
    """Chance a random positive scores above a random negative (ties count half); 0.5 is a coin flip."""
    r = score.rank()
    pos = positive.astype(bool)
    n1, n0 = int(pos.sum()), int((~pos).sum())
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else np.nan


def join_period(first_idx: pd.Series) -> pd.Series:
    return pd.Series(np.select(
        [first_idx < 2010 * 12 + 1, first_idx <= 2017 * 12 + 12, first_idx <= WINDOW_IDX[1]],
        ["Joined before 2010", "Joined 2010–2017", "Joined 2018 – Oct 2019"], "Joined Nov 2019 – Feb 2020"),
        index=first_idx.index)


def year_one_behaviour(c: pd.DataFrame, cards: pd.DataFrame, txn: dict, first: pd.Series) -> pd.DataFrame:
    """Spend in the first 12 months: total, share on credit, share online, and share by merchant category."""
    m = txn["monthly"].reset_index()
    m = m[m.client_id.isin(first.index)]
    m = m[tenure_year(m.month, m.client_id.map(first)) == 1]
    m["card_type"] = m.card_id.map(cards.set_index("id").card_type)
    out = pd.DataFrame(index=first.index)
    out["year1_spend"] = m.groupby("client_id").spend.sum()
    out["year1_credit_share"] = m[m.card_type == "Credit"].groupby("client_id").spend.sum().reindex(
        out.index, fill_value=0.0) / out.year1_spend
    o = txn["online_monthly"].reset_index()
    o = o[o.client_id.isin(first.index) & (tenure_year(o.month, o.client_id.map(first)) == 1)]
    out["year1_online_share"] = o.groupby("client_id").amt.sum().reindex(out.index, fill_value=0.0) / out.year1_spend
    k = txn["category_monthly"].reset_index()
    k = k[k.client_id.isin(first.index) & (tenure_year(k.month, k.client_id.map(first)) == 1)]
    cats = k.pivot_table(index="client_id", columns="cat", values="amt", aggfunc="sum").reindex(out.index)
    return out.join(cats.add_prefix("cat_"))


def step4() -> dict:
    p = prepare()
    c, cards, txn, rates = p["c"], p["cards"], p["txn"], p["rates"]
    years = customer_years(c, cards, txn, rates)
    card_fy = card_first_year(cards, txn, rates, c.index[c.ever_transacted])
    cut, _ = best_split(card_fy.credit_limit, card_fy.first_year_revenue)

    first = c.first_card_month
    day1, _ = day_one_and_today(cards, first)
    snapshot = 2020 * 12 + 2
    today = holdings(cards, (cards.open_idx <= snapshot) & (cards.expires_idx >= snapshot)).reindex(first.index)
    seg = scheme_labels(day1, c.yearly_income, cut, float(c.yearly_income.median()))[SEGMENT_SCHEME]
    order = [f"Credit, limit {dollars(cut)}+", f"Credit, limit under {dollars(cut)}", "Debit or prepaid"]
    period = join_period(first)
    in_cohort = years.index
    has_data = c.ever_transacted

    # sizes by join period
    status = period.where(~period.eq("Joined 2010–2017"),
                          np.where(has_data, "Joined 2010–2017, with data", "Joined 2010–2017, no data"))
    sizes = pd.crosstab(seg, status).reindex(order)
    sizes["All customers"] = sizes.sum(axis=1)
    shares = sizes / sizes.sum()

    # first-year value: customers acquired 2010-2017 with data
    fy = years.year1[years.has_data & years.year1.notna()]
    g = seg.reindex(fy.index)
    value_rows = []
    for s in order:
        v = fy[g.eq(s)]
        lo, hi = bootstrap_ci(v)
        value_rows.append({"segment": s, "customers": len(v), "first_year_revenue": v.mean(), "low_95": lo,
                           "high_95": hi, "median": v.median(), "share_of_first_year_revenue": v.sum() / fy.sum(),
                           "cohort_customers_no_data": int((seg.reindex(in_cohort).eq(s) & ~years.has_data).sum())})
    value = pd.DataFrame(value_rows)
    e = eta_squared(fy, g)
    score = {"customers": len(fy), "eta_squared_adjusted": adjusted_eta_squared(e, len(fy), len(order)),
             "permutation_p": permutation_p(fy, g), "rank_stability": rank_stability(fy, g)}

    # larger-sample check: every card opened 2010-2017, by type and limit
    allc = card_first_year(cards, txn, rates, c.index[c.ever_transacted],
                           card_types=("Credit", "Debit", "Debit (Prepaid)"))
    allc["first_card"] = allc.open_idx.eq(allc.client_id.map(first))
    allc["group"] = np.select([allc.card_type.eq("Credit") & (allc.credit_limit >= cut), allc.card_type.eq("Credit"),
                               allc.card_type.eq("Debit")], order[:2] + ["Debit"], "Prepaid")
    card_check = allc.groupby(["group", "first_card"]).first_year_revenue.agg(["size", "mean"]).unstack("first_card")
    card_check.columns = [f"{'first_card' if f else 'extra_card'}_{s}" for s, f in card_check.columns]
    card_check["all_cards"] = allc.groupby("group").size()
    card_check["all_cards_mean"] = allc.groupby("group").first_year_revenue.mean()
    card_check = card_check.reindex(order[:2] + ["Debit", "Prepaid"])

    # who they are
    u = c.assign(segment=seg, age_at_first_card=age_at(first, c.birth_year, c.birth_month),
                 income_fifth=pd.qcut(c.yearly_income, 5, labels=["Bottom", "2nd", "3rd", "4th", "Top"]),
                 holds_credit_feb_2020=today["product"].eq("Credit"))
    behaviour = year_one_behaviour(c, cards, txn, first.reindex(in_cohort))
    profile_rows = []
    for s in order:
        x = u[u.segment.eq(s)]
        b = behaviour.reindex(fy.index[g.eq(s).to_numpy()])
        cat_cols = [k for k in b.columns if k.startswith("cat_")]
        cat_share = (b[cat_cols].sum() / b.year1_spend.sum()).sort_values(ascending=False)
        row = {"segment": s, "customers": len(x),
               "median_income": x.yearly_income.median(), "top_income_fifth": (x.income_fifth == "Top").mean(),
               "bottom_income_fifth": (x.income_fifth == "Bottom").mean(),
               "median_age_at_first_card": x.age_at_first_card.median(),
               "under_30_at_first_card": (x.age_at_first_card < 30).mean(),
               "median_credit_score": x.credit_score.median(), "median_total_debt": x.total_debt.median(),
               "female": (x.gender == "Female").mean(), "holds_credit_feb_2020": x.holds_credit_feb_2020.mean(),
               "median_day_one_credit_limit": day1.max_credit_limit.reindex(x.index).median(),
               "cohort_customers_with_data": len(b), "year1_spend_mean": b.year1_spend.mean(),
               "year1_credit_share": (b.year1_spend * b.year1_credit_share).sum() / b.year1_spend.sum(),
               "year1_online_share": (b.year1_spend * b.year1_online_share).sum() / b.year1_spend.sum()}
        row.update({f"region_{r}": (x.region == r).mean() for r in ["South", "West", "Midwest", "Northeast"]})
        row.update({f"top_category_{i + 1}": f"{k[4:]} ({v:.0%})" for i, (k, v) in enumerate(cat_share.head(3).items())})
        profile_rows.append(row)
    profiles = pd.DataFrame(profile_rows)

    # can Growth find them? customers who joined 2010 or later, plus the whole base as a check
    recent = u[first >= 2010 * 12 + 1]
    shares_rows = []
    for dim, col in [("income fifth", "income_fifth"), ("age at first card", "age_band"), ("region", "region")]:
        base = recent.assign(age_band=pd.cut(recent.age_at_first_card, AGE_BANDS[0], right=False, labels=AGE_BANDS[1]))
        t = pd.crosstab(base[col], base.segment, normalize="index").reindex(columns=order)
        t["customers"] = base[col].value_counts()
        shares_rows.append(t.assign(dimension=dim).reset_index().rename(columns={col: "group"}))
    targeting_shares = pd.concat(shares_rows, ignore_index=True)
    auc_rows = []
    for pop_name, pop in [("joined 2010 or later", recent), ("all customers", u)]:
        credit = pop.segment.str.startswith("Credit")
        cr = pop[credit]
        for score_col in ["yearly_income", "per_capita_income", "age_at_first_card", "credit_score", "total_debt"]:
            auc_rows.append({"population": pop_name, "attribute": score_col,
                             "credit_vs_debit_or_prepaid": auc(pop[score_col], credit),
                             "high_vs_low_limit_among_credit": auc(cr[score_col], cr.segment.eq(order[0])),
                             "customers": len(pop), "credit_customers": len(cr)})
    targeting_auc = pd.DataFrame(auc_rows)

    sizes.to_csv(OUT / "step4_segment_sizes.csv")
    value.to_csv(OUT / "step4_first_year_value.csv", index=False)
    card_check.to_csv(OUT / "step4_card_first_year.csv")
    profiles.to_csv(OUT / "step4_profiles.csv", index=False)
    targeting_shares.to_csv(OUT / "step4_targeting_shares.csv", index=False)
    targeting_auc.to_csv(OUT / "step4_targeting_auc.csv", index=False)
    u[["segment", "age_at_first_card", "income_fifth", "holds_credit_feb_2020"]].assign(join_period=period).to_csv(
        OUT / "step4_customer_segments.csv")
    summary = {"credit_limit_cut": cut, "segments": order, "first_year_value_score": score,
               "segment_shares_by_join_period": shares.round(4).to_dict()}
    (OUT / "step4_summary.json").write_text(json.dumps(plain(summary), indent=2, default=str))
    plot_step4(value, shares, order)
    return {"summary": summary, "value": value.round(1).to_dict(orient="records")}


def plot_step4(value: pd.DataFrame, shares: pd.DataFrame, order: list) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    v = value.set_index("segment").reindex(order[::-1])
    y = np.arange(len(v))
    ax.barh(y, v.first_year_revenue, xerr=[v.first_year_revenue - v.low_95, v.high_95 - v.first_year_revenue],
            color="tab:blue", alpha=0.8, capsize=3, label="per new customer (95% CI)")
    ax.set_yticks(y, [f"{s}  (n={n})" for s, n in zip(v.index, v.customers)])
    ax.set_xlabel("First-year revenue ($)")
    ax.set_title("First-year revenue of customers acquired 2010–2017", fontsize=10)
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[1]
    cols = [k for k in ["Joined before 2010", "Joined 2010–2017, with data", "Joined 2010–2017, no data",
                        "Joined 2018 – Oct 2019", "Joined Nov 2019 – Feb 2020"] if k in shares.columns]
    left = np.zeros(len(cols))
    colours = ["tab:blue", "lightsteelblue", "lightgrey"]
    for s, col in zip(order, colours):
        vals = shares.loc[s, cols].to_numpy()
        ax.barh(range(len(cols)), vals * 100, left=left * 100, color=col, label=s)
        left += vals
    ax.set_yticks(range(len(cols)), cols)
    ax.invert_yaxis()
    ax.set_xlabel("Share of customers by day-one segment (%)")
    ax.set_title("Day-one segment mix by when customers joined", fontsize=10)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.4, -0.16), ncol=3, frameon=False)
    fig.tight_layout(w_pad=3)
    fig.savefig(PLOTS / "q1_first_year_value_and_mix.png", dpi=150)
    plt.close(fig)


def plain(x):
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, (np.integer, np.floating, np.bool_)):
        return x.item()
    return x


STEPS = {1: step1, 2: step2, 3: step3, 4: step4}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n in [int(a) for a in sys.argv[1:]] or STEPS:
        print(f"=== step {n} ===")
        print(json.dumps(STEPS[n](), indent=2, default=str))


if __name__ == "__main__":
    main()
