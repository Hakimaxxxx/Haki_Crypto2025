import os
import requests
import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)

key = os.getenv('BLOCKBERRY_API_KEY') or os.getenv('SUI_API_KEY') or os.getenv('BLOCKVISION_API_KEY')
base = 'https://api.blockberry.one/sui/v1'
headers = {'accept':'*/*', 'x-api-key': key}
# fetch a recent tx to get a checkpoint
r = requests.post(f"{base}/transactions?page=0&size=1&orderBy=DESC&sortBy=AGE", headers=headers, timeout=10)
print('recent status', r.status_code)
cp = None
try:
    j = r.json()
    content = j.get('content') or []
    if content:
        cp = content[0].get('checkpoint')
    print('recent checkpoint', cp)
except Exception as e:
    print('json err', e)

if cp is None:
    print('no checkpoint')
    sys.exit(1)

print('Calling module fetch for checkpoint', cp)
res = mod.fetch_blockberry_transactions_by_checkpoint(cp, max_pages=10, page_size=20)
print('module returned', len(res), 'txs')
if res:
    print(res[0])

# Also try fetch_block_transactions wrapper
print('Calling fetch_block_transactions wrapper')
res2 = mod.fetch_block_transactions(cp)
print('fetch_block_transactions returned', len(res2))
if res2:
    print(res2[0])
