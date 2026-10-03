"""Framework step 2: descriptive customer profiles; no value model or segments.
Run with Python and pandas. Reads the master database without modifying it.
"""
import json
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'customer_profile'
OUT.mkdir(exist_ok=True)
db = sqlite3.connect(f'file:{ROOT / "master/customer_transaction_master.sqlite"}?mode=ro',uri=True)
POS = 'transaction_id IS NOT NULL AND transaction_amount_cents > 0 AND transaction_errors IS NULL'
query = f'''
SELECT client_id,
 MAX(user_current_age) AS reported_age,
 MAX(user_gender) AS gender,
 MAX(CAST(REPLACE(user_yearly_income,'$','') AS REAL)) AS annual_income,
 MAX(CAST(REPLACE(user_total_debt,'$','') AS REAL)) AS total_debt,
 MAX(user_credit_score) AS credit_score,
 MAX(user_num_credit_cards) AS reported_card_count,
 MAX(eligibility_cards_opened_before_window) AS cards_opened_before_window,
 COUNT(transaction_id) AS raw_transaction_count,
 SUM(CASE WHEN transaction_errors IS NOT NULL THEN 1 ELSE 0 END) AS error_count,
 SUM(CASE WHEN transaction_amount_cents < 0 THEN 1 ELSE 0 END) AS negative_amount_count,
 SUM(CASE WHEN {POS} THEN 1 ELSE 0 END) AS positive_error_free_count,
 SUM(CASE WHEN {POS} THEN transaction_amount_cents ELSE 0 END) AS positive_error_free_cents,
 SUM(CASE WHEN transaction_amount_cents < 0 AND transaction_errors IS NULL THEN -transaction_amount_cents ELSE 0 END) AS negative_error_free_magnitude_cents,
 COUNT(DISTINCT CASE WHEN {POS} THEN SUBSTR(transaction_date,1,7) END) AS positive_error_free_months,
 COUNT(DISTINCT CASE WHEN {POS} THEN SUBSTR(transaction_date,1,10) END) AS positive_error_free_days,
 COUNT(DISTINCT CASE WHEN {POS} THEN card_id END) AS cards_used,
 COUNT(DISTINCT CASE WHEN {POS} THEN transaction_mcc END) AS merchant_categories_used,
 MIN(CASE WHEN {POS} THEN transaction_date END) AS first_positive_in_window,
 MAX(CASE WHEN {POS} THEN transaction_date END) AS last_positive_in_window,
 SUM(CASE WHEN {POS} AND card_type='Credit' THEN transaction_amount_cents ELSE 0 END) AS credit_cents,
 SUM(CASE WHEN {POS} AND card_type='Debit' THEN transaction_amount_cents ELSE 0 END) AS debit_cents,
 SUM(CASE WHEN {POS} AND card_type='Debit (Prepaid)' THEN transaction_amount_cents ELSE 0 END) AS prepaid_cents,
 SUM(CASE WHEN {POS} AND transaction_mcc=4829 THEN transaction_amount_cents ELSE 0 END) AS money_transfer_cents,
 SUM(CASE WHEN {POS} AND transaction_use_chip='Online Transaction' THEN transaction_amount_cents ELSE 0 END) AS online_cents
FROM master GROUP BY client_id
'''
c = pd.read_sql_query(query,db)
assert c.client_id.is_unique and len(c)==1603
assert c.raw_transaction_count.sum()==1392940
assert (c.credit_cents+c.debit_cents+c.prepaid_cents).equals(c.positive_error_free_cents)
c['observed_activity'] = c.raw_transaction_count.gt(0).map({True:'Recorded transactions',False:'No recorded transactions'})
c['positive_error_free_amount'] = c.positive_error_free_cents/100
c['days_since_last_positive'] = (pd.Timestamp('2019-11-01')-pd.to_datetime(c.last_positive_in_window)).dt.total_seconds()/86400
c['average_positive_amount'] = c.positive_error_free_amount.div(c.positive_error_free_count.replace(0,float('nan')))
c.to_csv(OUT/'customer_summary.csv',index=False)

active = c[c.positive_error_free_count>0]
demographics = c.groupby('observed_activity').agg(customers=('client_id','size'),median_age=('reported_age','median'),median_income=('annual_income','median'),median_debt=('total_debt','median'),median_credit_score=('credit_score','median'),median_reported_cards=('reported_card_count','median'))
demographics.to_csv(OUT/'demographics_by_observation.csv')
metrics=['positive_error_free_count','positive_error_free_amount','positive_error_free_days','positive_error_free_months','cards_used','merchant_categories_used','average_positive_amount']
distribution=active[metrics].describe(percentiles=[.25,.5,.75,.9,.95]).T
distribution.to_csv(OUT/'activity_distributions.csv')
cards = pd.read_sql_query(f'''SELECT card_type,COUNT(*) AS transactions,COUNT(DISTINCT client_id) AS customers,COUNT(DISTINCT card_id) AS cards_used,SUM(transaction_amount_cents)/100.0 AS positive_amount FROM master WHERE {POS} GROUP BY card_type''',db)
categories = pd.read_sql_query(f'''SELECT transaction_mcc,mcc_description,COUNT(*) AS transactions,COUNT(DISTINCT client_id) AS customers,SUM(transaction_amount_cents)/100.0 AS positive_amount FROM master WHERE {POS} GROUP BY transaction_mcc,mcc_description ORDER BY positive_amount DESC''',db)
cards.to_csv(OUT/'card_usage.csv',index=False)
categories.to_csv(OUT/'merchant_categories.csv',index=False)
monthly = pd.read_sql_query(f'''SELECT SUBSTR(transaction_date,1,7) AS month,COUNT(*) AS transactions,COUNT(DISTINCT client_id) AS customers,SUM(transaction_amount_cents)/100.0 AS positive_amount FROM master WHERE {POS} GROUP BY month''',db)
monthly.to_csv(OUT/'monthly_activity.csv',index=False)
assert cards.transactions.sum()==active.positive_error_free_count.sum()==categories.transactions.sum()==monthly.transactions.sum()
assert round(cards.positive_amount.sum()*100)==int(active.positive_error_free_cents.sum())
stats={
 'population':len(c),'raw_transactors':int(c.raw_transaction_count.gt(0).sum()),'positive_error_free_transactors':len(active),
 'no_transactions':int(c.raw_transaction_count.eq(0).sum()),'raw_error_count':int(c.error_count.sum()),
 'raw_negative_count':int(c.negative_amount_count.sum()),'positive_error_free_count':int(c.positive_error_free_count.sum()),
 'positive_error_free_amount':float(c.positive_error_free_amount.sum()),
 'negative_error_free_magnitude':float(c.negative_error_free_magnitude_cents.sum()/100),
 'overall_demographic_medians':c[['reported_age','annual_income','total_debt','credit_score','reported_card_count']].median().to_dict(),
 'gender':c.gender.value_counts().to_dict(),
 'active_month_counts':active.positive_error_free_months.value_counts().sort_index().to_dict(),
 'active_card_type_combinations':active.apply(lambda r: '+'.join(t for t in ['credit','debit','prepaid'] if r[t+'_cents']>0),axis=1).value_counts().to_dict(),
 'top_10pct_positive_amount_share':float(active.nlargest(int(len(active)*.1+.999),'positive_error_free_cents').positive_error_free_cents.sum()/active.positive_error_free_cents.sum()),
 'money_transfer_share':float(active.money_transfer_cents.sum()/active.positive_error_free_cents.sum()),
 'online_amount_share':float(active.online_cents.sum()/active.positive_error_free_cents.sum()),
 'validation':'passed',
}
(OUT/'statistics.json').write_text(json.dumps(stats,indent=2))
(OUT/'customer_summary.sql').write_text(query)
print(json.dumps(stats,indent=2))
print('\nDEMOGRAPHICS\n'+demographics.to_string())
print('\nDISTRIBUTIONS\n'+distribution.to_string())
print('\nCARD USAGE\n'+cards.to_string(index=False))
print('\nTOP CATEGORIES BY POSITIVE AMOUNT\n'+categories.head(10).to_string(index=False))
print('\nMONTHLY\n'+monthly.to_string(index=False))
