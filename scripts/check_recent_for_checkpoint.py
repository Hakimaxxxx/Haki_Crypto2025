import os
import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)
import requests
key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'accept':'*/*', 'x-api-key': key}
# get a recent checkpoint
r = requests.post(f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
cp = None
try:
    cp = r.json().get('content')[0].get('checkpoint')
except Exception:
    pass
print('target cp', cp)
# fetch recent blockberry txs via module
txs = mod.fetch_recent_blockberry_transactions(limit=500, page_size=50)
print('recent fetched', len(txs))
matches = [t for t in txs if int(t.get('checkpoint') or 0) == int(cp)]
print('matches for cp', cp, '->', len(matches))
if matches:
    print(matches[0])
else:
    # show some sample checkpoints seen
    s = sorted({int(t.get('checkpoint') or 0) for t in txs}, reverse=True)
    print('sample checkpoints seen:', s[:10])
