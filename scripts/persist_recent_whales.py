import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)

LIMIT = 200
MIN = 100
print(f'Fetching recent {LIMIT} transactions and persisting those with |value| >= {MIN} SUI')

recent = mod.fetch_recent_blockberry_transactions(limit=LIMIT, page_size=50)
print('Fetched:', len(recent))

existing = mod.load_whale_history() or []
existing_hashes = {e.get('hash') for e in existing if e.get('hash')}
new_entries = []
for tx in recent:
    try:
        val = float(tx.get('value', 0) or 0)
    except Exception:
        val = 0
    if abs(val) >= MIN:
        h = tx.get('hash')
        if not h or h in existing_hashes:
            continue
        entry = {
            'block': tx.get('checkpoint') or None,
            'hash': h,
            'from': (tx.get('from') or '').lower(),
            'to': (tx.get('to') or '').lower() if tx.get('to') else None,
            'value': val,
            'time': tx.get('timeStamp') or tx.get('timestamp') or None,
            'type': mod.classify_transaction((tx.get('from') or '').lower(), (tx.get('to') or '').lower()),
        }
        new_entries.append(entry)
        existing_hashes.add(h)

print('New entries to add:', len(new_entries))
if new_entries:
    merged = existing + new_entries
    mod.save_whale_history(merged)
    print('Saved, total history now:', len(merged))
else:
    print('No new entries to add')
