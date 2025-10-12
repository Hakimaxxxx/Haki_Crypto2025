import sys
sys.path.append(r'd:\Crypto')
from SUI import metrics_sui_whale_alert_realtime as mod
import importlib
importlib.reload(mod)

print('Fetching recent checkpoints (limit=10)')
checkpoints = mod.fetch_recent_checkpoints(limit=10)
print('Checkpoints:', checkpoints)

found = False
for cp in checkpoints:
    print(f'Checking checkpoint {cp} (max_pages=3, page_size=20)')
    txs = mod.fetch_blockberry_transactions_by_checkpoint(cp, max_pages=3, page_size=20)
    print('  txs count:', len(txs))
    if txs:
        print('Sample tx (first):')
        print(txs[0])
        found = True
        break

if not found:
    print('No tx found via per-checkpoint filtering; trying recent transactions paging (limit=50)')
    txs2 = mod.fetch_recent_blockberry_transactions(limit=50, page_size=25)
    print('Recent txs fetched:', len(txs2))
    if txs2:
        print('Sample recent tx (first):')
        print(txs2[0])
        found = True

if not found:
    print('No transactions fetched from BlockBerry (could be rate-limited or empty pages).')
else:
    print('At least one transaction fetched successfully.')
