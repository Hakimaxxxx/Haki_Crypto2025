import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)

LIMIT = 200
print(f'Fetching recent {LIMIT} transactions (paging)')
txs = mod.fetch_recent_blockberry_transactions(limit=LIMIT, page_size=50)
print('Fetched tx count:', len(txs))

candidates = []
for tx in txs:
    try:
        val = float(tx.get('value', 0) or 0)
    except Exception:
        val = 0
    if abs(val) >= 100:
        candidates.append(tx)

print('Candidates found:', len(candidates))
if candidates:
    for c in candidates[:5]:
        print(c)
else:
    print('No recent tx with abs(value) >= 100 SUI found')
