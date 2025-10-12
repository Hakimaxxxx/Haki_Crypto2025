import os
from importlib import reload
import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
reload(mod)
cp = 199941921
print('Calling fetch_blockberry_transactions_by_checkpoint for', cp)
res = mod.fetch_blockberry_transactions_by_checkpoint(cp, max_pages=2, page_size=5)
print('Got', len(res), 'txs')
if res:
    print(res[0])
