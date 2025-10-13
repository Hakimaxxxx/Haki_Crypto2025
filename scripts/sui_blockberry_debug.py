import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from SUI.metrics_sui_whale_alert_realtime import fetch_recent_checkpoints, fetch_recent_blockberry_transactions

print('Fetching checkpoints...')
try:
    cps = fetch_recent_checkpoints(limit=10)
    print('Checkpoints:', cps)
except Exception as e:
    print('fetch_recent_checkpoints error:', e)

print('\nFetching recent transactions (limit=20)...')
try:
    txs = fetch_recent_blockberry_transactions(limit=20, page_size=20)
    print('Fetched txs count:', len(txs))
    if txs:
        print('Sample tx:', txs[0])
except Exception as e:
    print('fetch_recent_blockberry_transactions error:', e)
