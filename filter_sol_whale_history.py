import json
from SOL.sol_cex_wallets import is_internal_exchange_transfer

with open('sol_whale_alert_history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

filtered = [tx for tx in data if not is_internal_exchange_transfer(tx['from'], tx['to'])]

with open('sol_whale_alert_history.json', 'w', encoding='utf-8') as f:
    json.dump(filtered, f, ensure_ascii=False)

print(f"Filtered: {len(data) - len(filtered)} internal exchange tx removed. Remaining: {len(filtered)}")
