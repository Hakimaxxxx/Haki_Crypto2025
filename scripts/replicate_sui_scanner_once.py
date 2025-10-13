import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from SUI.metrics_sui_whale_alert_realtime import fetch_recent_checkpoints, fetch_block_transactions, load_whale_history, save_whale_history, fetch_recent_blockberry_transactions
from SUI.sui_utils import HISTORY_FILE
from datetime import datetime

MIN_VALUE = 100.0

history = load_whale_history() or []
seen = {tx.get('hash') for tx in history}
print('Existing history count:', len(history))

cps = fetch_recent_checkpoints(limit=10)
print('Checkpoints to scan:', cps)
new = []
# safer: page recent transactions and filter by checkpoint instead of calling fetch_block_transactions
txs = fetch_recent_blockberry_transactions(limit=500, page_size=50)
print('Recent txs paged:', len(txs))
for tx in txs:
        try:
            v = abs(float(tx.get('value', 0) or 0))
        except Exception:
            v = 0
        if v < MIN_VALUE:
            continue
        h = tx.get('hash')
        blk = int(tx.get('checkpoint') or 0)
        if h in seen:
            continue
        obj = {
            'block': blk,
            'hash': h,
            'from': (tx.get('from') or '').lower(),
            'to': (tx.get('to') or '').lower(),
            'value': v,
            'time': tx.get('timeStamp') or tx.get('timestamp') or None,
            'type': 'OTHER'
        }
        new.append(obj)
        seen.add(h)

print('New candidate entries found:', len(new))
if new:
    print('Sample new:', new[:5])
    merged = history + new
    save_whale_history(merged)
    print('Persisted. New history length:', len(merged))
else:
    print('No new entries to persist')
