"""Descriptive inventory only; no cleaning, segmentation, or revenue assumptions.
Run from the data directory with Python, pandas and numpy.
"""
import json
import re
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd

OUT = Path('analysis/table_scan')
result = {}

def numeric(s):
    return pd.to_numeric(s.astype(str).str.replace('$', '', regex=False), errors='coerce')

def describe(s):
    return {k: float(v) for k, v in s.describe().items()}

def base(d):
    return {'rows':len(d), 'columns':list(d.columns), 'missing':{k:int(v) for k,v in d.isna().sum().items() if v}, 'exact_duplicate_rows':int(d.duplicated().sum())}

u = pd.read_csv('users_data.csv')
c = pd.read_csv('cards_data.csv')
s = pd.read_csv('account_signups.csv')
sp = pd.read_csv('channel_spend.csv')
for name, d, key in [('users',u,['id']),('cards',c,['id']),('signups',s,['signup_id']),('spend',sp,['spend_date','channel','campaign'])]:
    result[name] = base(d)
    result[name]['duplicate_key_excess'] = int(d.duplicated(key).sum())

result['users'].update(numeric={k:describe(numeric(u[k])) for k in ['current_age','yearly_income','total_debt','credit_score','num_credit_cards']}, gender=u.gender.value_counts().to_dict())
result['cards'].update(customers=int(c.client_id.nunique()), card_types=c.card_type.value_counts().to_dict(), brands=c.card_brand.value_counts().to_dict(), cards_per_customer=describe(c.groupby('client_id').size()), credit_limit=describe(numeric(c.credit_limit)), account_open_range=[str(pd.to_datetime(c.acct_open_date,format='%m/%Y').min().date()),str(pd.to_datetime(c.acct_open_date,format='%m/%Y').max().date())], unknown_customer=int((~c.client_id.isin(u.id)).sum()))
result['signups'].update(customers=int(s.client_id.nunique()), cards=int(s.card_id.nunique()), dates=[s.signup_ts.min(),s.signup_ts.max()], sources=s.self_reported_source.value_counts().to_dict(), unknown_customer=int((~s.client_id.isin(u.id)).sum()),unknown_card=int((~s.card_id.isin(c.id)).sum()),card_owner_mismatch=int((s.client_id!=s.card_id.map(c.set_index('id').client_id)).sum()))
result['spend'].update(dates=[sp.spend_date.min(),sp.spend_date.max()],channels=int(sp.channel.nunique()),campaigns=int(sp.campaign.nunique()),raw_spend=float(sp.spend.sum()),raw_platform_conversions=float(sp.platform_reported_conversions.sum()),duplicate_excess_by_channel=sp[sp.duplicated(['spend_date','channel','campaign'])].channel.value_counts().to_dict(),raw_by_channel=sp.groupby('channel').agg(rows=('channel','size'),spend=('spend','sum'),platform_conversions=('platform_reported_conversions','sum')).to_dict('index'))
result['revenue_assumptions']=pd.read_csv('revenue_assumptions.csv').to_dict('records')
mcc=json.loads(Path('mcc_codes.json').read_text())
result['mcc']={'entries':len(mcc),'blank_descriptions':sum(not v for v in mcc.values())}
print('Small tables done',flush=True)

count=Counter(); missing=Counter(); channels=Counter(); devices=Counter(); touch_ids=[]; anon=set(); linked_anon=set(); linked_clients=set(); anon_client_pairs=set(); touch_bounds=['9999','0000']
for d in pd.read_csv('marketing_touchpoints.csv',chunksize=200000):
    count['rows']+=len(d);missing.update({k:int(v) for k,v in d.isna().sum().items()})
    channels.update(d.channel);devices.update(d.device)
    touch_ids.append(d.touch_id.str.removeprefix('t_').astype('int64').to_numpy())
    anon.update(d.anonymous_id.dropna())
    linked=d[d.client_id.notna()];linked_anon.update(linked.anonymous_id.dropna());linked_clients.update(linked.client_id)
    anon_client_pairs.update(zip(linked.anonymous_id,linked.client_id.astype(int)))
    count['unknown_linked_customer']+=int((~linked.client_id.isin(u.id)).sum())
    touch_bounds=[min(touch_bounds[0],d.touch_ts.min()),max(touch_bounds[1],d.touch_ts.max())]
touch_ids=np.concatenate(touch_ids)
ac=Counter(a for a,b in anon_client_pairs)
result['touchpoints']={'rows':count['rows'],'columns':list(d.columns),'missing':{k:v for k,v in missing.items() if v},'dates':touch_bounds,'channels':dict(channels),'devices':dict(devices),'unique_anonymous_ids':len(anon),'anonymous_ids_with_customer_link':len(linked_anon),'linked_customers':len(linked_clients),'anonymous_ids_with_multiple_customers':sum(v>1 for v in ac.values()),'unknown_linked_customer':count['unknown_linked_customer'],'duplicate_touch_ids':len(touch_ids)-len(np.unique(touch_ids))}
del touch_ids,anon,linked_anon,anon_client_pairs
print('Touchpoints done',flush=True)

count=Counter(); missing=Counter(); clients=set(); card_ids=set(); tx_ids=[]; mcc_counts=Counter(); errors=Counter(); use_chip=Counter(); years=Counter(); amount_sum=0.; positive_sum=0.;negative_sum=0.;amin=float('inf');amax=-float('inf');bounds=['9999','0000']
owners=c.set_index('id').client_id
opened=pd.to_datetime(c.acct_open_date,format='%m/%Y');open_map=pd.Series(opened.values,index=c.id)
for d in pd.read_csv('transactions_data.csv',chunksize=250000):
    count['rows']+=len(d);missing.update({k:int(v) for k,v in d.isna().sum().items()})
    clients.update(d.client_id);card_ids.update(d.card_id);tx_ids.append(d.id.to_numpy())
    mcc_counts.update(d.mcc);errors.update(d.errors.dropna());use_chip.update(d.use_chip);years.update(d.date.str[:4])
    a=numeric(d.amount);amount_sum+=a.sum();positive_sum+=a[a>0].sum();negative_sum+=a[a<0].sum();amin=min(amin,a.min());amax=max(amax,a.max())
    count['positive_amount_rows']+=int((a>0).sum());count['negative_amount_rows']+=int((a<0).sum());count['zero_amount_rows']+=int((a==0).sum());count['unparseable_amounts']+=int(a.isna().sum())
    count['unknown_customer']+=int((~d.client_id.isin(u.id)).sum());count['unknown_card']+=int((~d.card_id.isin(c.id)).sum());count['card_owner_mismatch']+=int((d.client_id!=d.card_id.map(owners)).sum())
    count['before_card_open_month']+=int((pd.to_datetime(d.date)<d.card_id.map(open_map)).sum())
    bounds=[min(bounds[0],d.date.min()),max(bounds[1],d.date.max())]
    if count['rows']%4000000==0: print('Transactions scanned',count['rows'],flush=True)
tx_ids=np.sort(np.concatenate(tx_ids));count['duplicate_transaction_ids']=int((tx_ids[1:]==tx_ids[:-1]).sum())
result['transactions']={**dict(count),'columns':list(d.columns),'missing':{k:v for k,v in missing.items() if v},'dates':bounds,'customers':len(clients),'cards':len(card_ids),'raw_amount_sum':float(amount_sum),'positive_amount_sum':float(positive_sum),'negative_amount_sum':float(negative_sum),'amount_range':[float(amin),float(amax)],'transaction_modes':dict(use_chip),'top_errors':errors.most_common(8),'rows_by_year':dict(years),'mcc_codes':len(mcc_counts),'unmapped_mcc':{str(k):v for k,v in mcc_counts.items() if str(k) not in mcc},'top_mcc':[{'code':int(k),'description':mcc.get(str(k)),'rows':v} for k,v in mcc_counts.most_common(10)]}
print('Transactions done',flush=True)

# Parse the regular scalar ID:label mapping in bounded text blocks, retaining a
# compact int64 ID array for uniqueness and exact transaction-ID coverage checks.
labels=Counter();label_ids=[];pattern=re.compile(r'"(\d+)"\s*:\s*"([^"\\]*)"')
with open('train_fraud_labels.json') as f:
    carry=''
    while True:
        block=f.read(1024*1024)
        if not block:break
        text=carry+block;cut=text.rfind(',');part=text[:cut+1];carry=text[cut+1:]
        pairs=pattern.findall(part);labels.update(v for k,v in pairs);label_ids.append(np.array([int(k) for k,v in pairs],dtype='int64'))
    pairs=pattern.findall(carry);labels.update(v for k,v in pairs);label_ids.append(np.array([int(k) for k,v in pairs],dtype='int64'))
label_ids=np.sort(np.concatenate(label_ids));pos=np.searchsorted(tx_ids,label_ids);valid=pos<len(tx_ids);matched=np.zeros(len(pos),dtype=bool);matched[valid]=tx_ids[pos[valid]]==label_ids[valid]
result['fraud_labels']={'entries':len(label_ids),'labels':dict(labels),'duplicate_id_excess':int((label_ids[1:]==label_ids[:-1]).sum()),'ids_matching_transactions':int(matched.sum()),'ids_not_in_transactions':int((~matched).sum()),'transaction_rows_without_label':len(tx_ids)-int(matched.sum())}
(OUT/'profile.json').write_text(json.dumps(result,indent=2,default=str))
print(json.dumps(result,indent=2,default=str),flush=True)
