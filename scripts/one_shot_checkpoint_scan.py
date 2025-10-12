import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)

print('Calling fetch_recent_checkpoints(limit=20)')
checkpoints = mod.fetch_recent_checkpoints(limit=20)
print('checkpoints ->', checkpoints)

history = mod.load_whale_history() or []
seen_hashes = {h.get('hash') for h in history if h.get('hash')}
new_entries = []

for cp in checkpoints:
    print('Fetching txs for checkpoint', cp)
    txs = mod.fetch_blockberry_transactions_by_checkpoint(cp, max_pages=4, page_size=50)
    print('  txs returned', len(txs))
    for tx in txs:
        try:
            val = float(tx.get('value') or 0)
        except Exception:
            val = 0
        if abs(val) >= 100:
            h = tx.get('hash')
            if h not in seen_hashes:
                entry = {
                    'block': cp,
                    'hash': h,
                    'from': (tx.get('from') or '').lower(),
                    'to': (tx.get('to') or '').lower(),
                    'value': val,
                    'time': tx.get('timeStamp') or tx.get('timestamp') or None,
                    'type': mod.classify_transaction((tx.get('from') or '').lower(), (tx.get('to') or '').lower()),
                }
                new_entries.append(entry)
                seen_hashes.add(h)

print('New whale entries found:', len(new_entries))
if new_entries:
    merged = history + new_entries
    mod.save_whale_history(merged)
    print('Saved new entries')
else:
    print('No new whale entries')
