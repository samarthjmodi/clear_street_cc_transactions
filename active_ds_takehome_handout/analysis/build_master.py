"""Build a transaction-grain SQLite master, preserving eligible nontransactors.

Run from the source-data directory: python analysis/build_master.py
Requires pandas and numpy. Raw inputs are not changed. No errors, refunds,
zero amounts, or unlabeled transactions are excluded.
"""
from pathlib import Path
from collections import Counter
import json
import re
import sqlite3
import tempfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'master'
START, END = '2018-11-01', '2019-11-01'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build():
    OUT.mkdir(exist_ok=True)
    destination = OUT / 'customer_transaction_master.sqlite'
    require(not destination.exists(), f'Output already exists: {destination}. Preserve or move it before rebuilding.')
    users = pd.read_csv(ROOT / 'users_data.csv')
    cards = pd.read_csv(ROOT / 'cards_data.csv')
    signups = pd.read_csv(ROOT / 'account_signups.csv')
    require(users.id.is_unique, 'Duplicate user IDs')
    require(cards.id.is_unique, 'Duplicate card IDs')
    require(not signups.duplicated(['client_id', 'card_id']).any(), 'Signup join is not many-to-one')
    require(signups.signup_id.is_unique, 'Duplicate signup IDs')
    require(cards.client_id.isin(users.id).all(), 'Unknown card owner')
    owner = cards.set_index('id').client_id
    require(signups.client_id.eq(signups.card_id.map(owner)).all(), 'Signup/card owner mismatch')
    # Dates contain only month and year: day 01 expresses that month, not an exact opening timestamp.
    cards['card_open_month'] = pd.to_datetime(cards.acct_open_date, format='%m/%Y').dt.strftime('%Y-%m-%d')
    early = cards[cards.card_open_month < START]
    eligible = users[users.id.isin(early.client_id)].copy()
    eligible['eligibility_first_card_open_month'] = eligible.id.map(cards.groupby('client_id').card_open_month.min())
    eligible['eligibility_cards_opened_before_window'] = eligible.id.map(early.groupby('client_id').size())
    eligible_ids = set(eligible.id)
    print(f'Eligible customers: {len(eligible)} / {len(users)}', flush=True)

    with tempfile.TemporaryDirectory(prefix='q1_master_') as scratch:
        stage = sqlite3.connect(str(Path(scratch) / 'staging.sqlite'))
        for name, data in [('users', eligible), ('cards', cards), ('signups', signups)]:
            data.to_sql(name, stage, index=False)
        stage.execute('CREATE UNIQUE INDEX user_key ON users(id)')
        stage.execute('CREATE UNIQUE INDEX card_key ON cards(id)')
        stage.execute('CREATE UNIQUE INDEX signup_key ON signups(client_id,card_id)')
        mcc = json.loads((ROOT / 'mcc_codes.json').read_text())
        pd.DataFrame([(int(k),v) for k,v in mcc.items()],columns=['mcc','description']).to_sql('mcc', stage,index=False)
        stage.execute('CREATE UNIQUE INDEX mcc_key ON mcc(mcc)')
        selected_ids = []
        expected_amount = 0
        window_all = 0
        for d in pd.read_csv(ROOT / 'transactions_data.csv', chunksize=100_000):
            in_window = d.date.ge(START) & d.date.lt(END)
            window_all += int(in_window.sum())
            d = d[in_window & d.client_id.isin(eligible_ids)].copy()
            if d.empty:
                continue
            require(d.client_id.eq(d.card_id.map(owner)).all(), 'Transaction/card owner mismatch')
            selected_ids.append(d.id.to_numpy())
            # Preserve raw dollar strings and add integer cents for exact reconciliation.
            d['amount_cents'] = pd.to_numeric(d.amount.str.replace('$','',regex=False)).mul(100).round().astype('int64')
            expected_amount += int(d.amount_cents.sum())
            d.to_sql('transactions',stage,if_exists='append',index=False,chunksize=5000)
        selected_ids = np.sort(np.concatenate(selected_ids))
        require(not np.any(selected_ids[1:] == selected_ids[:-1]), 'Duplicate selected transaction IDs')
        stage.execute('CREATE UNIQUE INDEX transaction_key ON transactions(id)')
        stage.execute('CREATE INDEX transaction_customer ON transactions(client_id)')
        print(f'Selected transactions: {len(selected_ids):,}', flush=True)

        stage.execute('CREATE TABLE fraud(transaction_id INTEGER PRIMARY KEY, label TEXT NOT NULL)')
        labels = Counter()
        pattern = re.compile(r'"(\d+)"\s*:\s*"([^"\\]*)"')

        def load_labels(text):
            pairs = pattern.findall(text)
            if not pairs:
                return
            ids = np.array([int(k) for k,v in pairs],dtype='int64')
            pos = np.searchsorted(selected_ids,ids)
            valid = pos < len(selected_ids)
            idx = np.flatnonzero(valid)
            valid[idx] = selected_ids[pos[idx]] == ids[idx]
            matches = [(int(ids[i]),pairs[i][1]) for i in np.flatnonzero(valid)]
            require(all(v in ('Yes','No') for k,v in matches),'Unexpected fraud label')
            stage.executemany('INSERT INTO fraud VALUES (?,?)',matches)
            labels.update(v for k,v in matches)

        with (ROOT / 'train_fraud_labels.json').open() as f:
            carry = ''
            while block := f.read(1024*1024):
                text = carry + block
                cut = text.rfind(',')
                load_labels(text[:cut+1])
                carry = text[cut+1:]
            load_labels(carry)
        stage.commit()

        selections = ['u.id AS client_id']
        selections += [f'u."{col}" AS "user_{col}"' for col in users.columns if col != 'id']
        selections += ['u.eligibility_first_card_open_month','u.eligibility_cards_opened_before_window']
        txcols = [r[1] for r in stage.execute('PRAGMA table_info(transactions)')]
        selections += [f't."{col}" AS "{("transaction_id" if col == "id" else "card_id" if col == "card_id" else "transaction_"+col)}"' for col in txcols if col != 'client_id']
        selections += [f'c."{col}" AS "{col if col.startswith("card_") else "card_"+col}"' for col in cards.columns if col not in ('id','client_id')]
        selections += ['m.description AS mcc_description','f.label AS fraud_label']
        selections += [f's."{col}" AS "{col if col.startswith("signup_") else "signup_"+col}"' for col in signups.columns if col not in ('client_id','card_id')]
        query = 'SELECT '+',\n'.join(selections)+'''\nFROM src.users u
LEFT JOIN src.transactions t ON t.client_id=u.id
LEFT JOIN src.cards c ON c.id=t.card_id AND c.client_id=u.id
LEFT JOIN src.mcc m ON m.mcc=t.mcc
LEFT JOIN src.fraud f ON f.transaction_id=t.id
LEFT JOIN src.signups s ON s.client_id=u.id AND s.card_id=t.card_id'''
        db = sqlite3.connect(destination)
        db.execute('ATTACH DATABASE ? AS src',(str(Path(scratch)/'staging.sqlite'),))
        db.execute('CREATE TABLE master AS '+query)
        db.execute('CREATE UNIQUE INDEX master_transaction_key ON master(transaction_id)')
        db.execute('CREATE INDEX master_customer_key ON master(client_id)')
        db.commit()
        stats = dict(zip(['rows','customers','transactions','null_transaction_rows','amount_cents'], db.execute('SELECT COUNT(*),COUNT(DISTINCT client_id),COUNT(transaction_id),SUM(transaction_id IS NULL),SUM(transaction_amount_cents) FROM master').fetchone()))
        require(stats['transactions']==len(selected_ids),'Transaction rows multiplied or lost')
        require(stats['customers']==len(eligible),'Eligible customers lost')
        require(stats['amount_cents']==expected_amount,'Transaction amount reconciliation failed')
        require(stats['rows']==stats['transactions']+stats['null_transaction_rows'],'Row grain mismatch')
        require(db.execute('SELECT COUNT(*) FROM (SELECT client_id FROM master GROUP BY client_id HAVING SUM(transaction_id IS NULL)>0 AND COUNT(*)<>1)').fetchone()[0]==0,'Nontransactor placeholders are not unique')
        require(db.execute('SELECT COUNT(*) FROM master WHERE transaction_id IS NOT NULL AND (transaction_date < ? OR transaction_date >= ?)',(START,END)).fetchone()[0]==0,'Out-of-window transaction')
        require(db.execute('SELECT COUNT(*) FROM master WHERE eligibility_first_card_open_month >= ?',(START,)).fetchone()[0]==0,'Ineligible customer')
        columns = [x[1] for x in db.execute('PRAGMA table_info(master)')]
        null_fields = [x for x in columns if x.startswith(('transaction_','card_','signup_')) or x in ('mcc_description','fraud_label')]
        require(db.execute('SELECT COUNT(*) FROM master WHERE transaction_id IS NULL AND ('+' OR '.join('"'+x+'" IS NOT NULL' for x in null_fields)+')').fetchone()[0]==0,'Placeholder has transaction-dependent data')
        stats.update(window_start_inclusive=START,window_end_exclusive=END,total_source_users=len(users),excluded_users=len(users)-len(eligible),all_window_transactions=window_all,excluded_window_transactions=window_all-len(selected_ids),fraud_labels=dict(labels),columns=len(columns),matched_signup_transactions=db.execute('SELECT COUNT(*) FROM master WHERE signup_id IS NOT NULL').fetchone()[0],validation='passed')
        stats['transactions_on_cards_opened_during_window'] = db.execute('SELECT COUNT(*) FROM master WHERE transaction_id IS NOT NULL AND card_open_month >= ?',(START,)).fetchone()[0]
        (OUT/'validation.json').write_text(json.dumps(stats,indent=2))
        (OUT/'join.sql').write_text(query+';\n')
        pd.read_sql_query('SELECT * FROM master LIMIT 0',db).to_csv(OUT/'column_names.csv',index=False)
        db.close()
        stage.close()
    print(json.dumps(stats,indent=2),flush=True)


if __name__ == '__main__':
    build()
