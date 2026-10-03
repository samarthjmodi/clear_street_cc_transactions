"""Read-only source analysis for Q1. Run from the data directory. Requires pandas/numpy."""
from pathlib import Path
import json
from collections import Counter
import numpy as np
import pandas as pd

OUT = Path('analysis/q1')
users = pd.read_csv('users_data.csv')
cards = pd.read_csv('cards_data.csv')
assert users.id.is_unique and cards.id.is_unique
assert cards.client_id.isin(users.id).all()
rates = pd.read_csv('revenue_assumptions.csv').set_index('assumption_key').assumption_value
for col in ['yearly_income', 'per_capita_income', 'total_debt']:
    users[col] = pd.to_numeric(users[col].str.replace('$', '', regex=False))
cards['opened'] = pd.to_datetime(cards.acct_open_date, format='%m/%Y')
card_owner = cards.set_index('id').client_id
audit = Counter()
parts, ids, firsts = [], [], []
mcc_counts = Counter()
for d in pd.read_csv('transactions_data.csv', chunksize=250_000):
    audit['rows'] += len(d)
    ids.append(d.id.to_numpy())
    d['date'] = pd.to_datetime(d.date)
    d['amount'] = pd.to_numeric(d.amount.str.replace('$', '', regex=False))
    audit['unknown_customer'] += int((~d.client_id.isin(users.id)).sum())
    audit['unknown_card'] += int((~d.card_id.isin(cards.id)).sum())
    audit['card_owner_mismatch'] += int((d.client_id != d.card_id.map(card_owner)).sum())
    audit['before_card_open_month'] += int((d.date < d.card_id.map(cards.set_index('id').opened)).sum())
    good = d.errors.isna() & (d.amount > 0)
    firsts.append(d[good].groupby('client_id').date.min())
    w = d[(d.date >= '2018-11-01') & (d.date < '2019-11-01')].copy()
    audit['window_rows'] += len(w)
    audit['window_error_rows'] += int(w.errors.notna().sum())
    audit['window_negative_rows'] += int((w.amount < 0).sum())
    w = w[w.errors.isna()].copy()
    w['month'] = w.date.dt.to_period('M').astype(str)
    w['purchases'] = w.amount.clip(lower=0)
    w['refunds'] = -w.amount.clip(upper=0)
    w['purchase_count'] = (w.amount > 0).astype(int)
    w['refund_count'] = (w.amount < 0).astype(int)
    w['last_purchase'] = w.date.where(w.amount > 0)
    mcc_counts.update(w.loc[w.amount > 0, 'mcc'])
    parts.append(w.groupby(['client_id', 'card_id', 'month']).agg(
        purchases=('purchases', 'sum'), refunds=('refunds', 'sum'),
        purchase_count=('purchase_count', 'sum'), refund_count=('refund_count', 'sum'),
        last_purchase=('last_purchase', 'max')).reset_index())
    if audit['rows'] % 2_000_000 == 0:
        print('Scanned', audit['rows'], flush=True)
all_ids = np.concatenate(ids)
audit['duplicate_transaction_ids'] = len(all_ids) - len(np.unique(all_ids))
del ids, all_ids
g = pd.concat(parts).groupby(['client_id', 'card_id', 'month']).agg(
    purchases=('purchases', 'sum'), refunds=('refunds', 'sum'),
    purchase_count=('purchase_count', 'sum'), refund_count=('refund_count', 'sum'),
    last_purchase=('last_purchase', 'max')).reset_index()
g = g.merge(cards[['id', 'card_type', 'card_brand']], left_on='card_id', right_on='id', validate='many_to_one')
g['net_volume'] = g.purchases - g.refunds
credit = g.card_type.eq('Credit')
debit = g.card_type.eq('Debit')
prepaid = g.card_type.eq('Debit (Prepaid)')
g['credit_volume'] = g.purchases.where(credit, 0)
g['debit_volume'] = g.purchases.where(debit, 0)
g['prepaid_volume'] = g.purchases.where(prepaid, 0)
g['interchange'] = np.where(credit, g.net_volume * rates['interchange_credit_bps']/10000,
    np.where(debit, g.net_volume * rates['interchange_debit_bps']/10000 + g.purchase_count*rates['interchange_debit_fixed_cents']/100, 0))
g['prepaid_debit_scenario'] = np.where(prepaid, g.net_volume*0.0005 + g.purchase_count*0.21, 0)
g['prepaid_credit_scenario'] = np.where(prepaid, g.net_volume*0.018, 0)
g['refund_reversal_sensitivity'] = np.where(credit, g.refunds*0.018, np.where(debit,g.refunds*0.0005,0))
numeric = ['purchases','refunds','purchase_count','refund_count','net_volume','credit_volume','debit_volume','prepaid_volume','interchange','prepaid_debit_scenario','prepaid_credit_scenario','refund_reversal_sensitivity']
c = g.groupby('client_id')[numeric].sum()
c['active_months'] = g[g.purchase_count>0].groupby('client_id').month.nunique()
c['last_purchase'] = g.groupby('client_id').last_purchase.max()
c = users.rename(columns={'id':'client_id'}).merge(c, on='client_id', how='left', validate='one_to_one')
c[numeric+['active_months']] = c[numeric+['active_months']].fillna(0)
c['days_since_purchase'] = (pd.Timestamp('2019-11-01')-c.last_purchase).dt.days
c['first_observed_purchase'] = c.client_id.map(pd.concat(firsts).groupby(level=0).min())
c['credit_share'] = c.credit_volume.div(c.purchases.replace(0,np.nan)).fillna(0)
c['segment'] = np.select([c.purchase_count.eq(0), c.active_months.lt(9), c.credit_share.ge(0.5)],
    ['No purchases in window','Occasional users (<9 months)','Regular credit-led'], default='Regular debit/prepaid-led')
# Fees are a separate scenario: card ownership alone does not prove fees were collected.
amex = cards[cards.card_type.eq('Credit') & cards.card_brand.eq('Amex') & cards.opened.lt('2019-11-01')].copy()
amex['exposure'] = ((pd.Timestamp('2019-11-01')-amex.opened.clip(lower=pd.Timestamp('2018-11-01'))).dt.days/365).clip(0,1)
c['potential_amex_fees'] = c.client_id.map(amex.groupby('client_id').exposure.sum()*95).fillna(0)
c.to_csv(OUT/'customer_metrics.csv',index=False)
g.to_csv(OUT/'card_month_metrics.csv',index=False)
summary = c.groupby('segment').agg(customers=('client_id','size'), purchases=('purchases','sum'),
    median_purchases=('purchases','median'), interchange=('interchange','sum'), median_interchange=('interchange','median'),
    avg_interchange=('interchange','mean'), median_income=('yearly_income','median'), median_credit_score=('credit_score','median'),
    median_age=('current_age','median'), median_active_months=('active_months','median'), potential_fees=('potential_amex_fees','sum'),
    prepaid_debit_scenario=('prepaid_debit_scenario','sum'),prepaid_credit_scenario=('prepaid_credit_scenario','sum'))
summary.to_csv(OUT/'segment_summary.csv')
print(summary.to_string(),flush=True)
print('AUDIT',dict(audit),flush=True)
print('TOTALS',c[numeric+['potential_amex_fees']].sum().to_dict(),flush=True)
print('DEMOGRAPHICS',c[['current_age','yearly_income','credit_score','total_debt']].describe().to_string(),flush=True)
print('Top MCCs',mcc_counts.most_common(15),flush=True)
print('Recent customer first observed after window start',int(c.first_observed_purchase.ge('2018-11-01').sum()))
print('Active customers',int(c.purchase_count.gt(0).sum()),'12 month users',int(c.active_months.eq(12).sum()))
print('TOP 20% interchange share',c.nlargest(400,'interchange').interchange.sum()/c.interchange.sum())
print('Card types',cards.card_type.value_counts().to_dict())
(OUT/'audit.json').write_text(json.dumps(dict(audit),indent=2))
