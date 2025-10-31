
# Gộp: fetch block, phân tích toàn bộ giao dịch chuyển SOL, xuất log
import requests
import json
import sys
import os

def get_block_number():
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except Exception:
            pass
    try:
        return int(input("Nhập block_number cần kiểm tra: "))
    except Exception:
        return 369810960  # fallback mặc định

block_number = get_block_number()
url = "https://api.mainnet-beta.solana.com"
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getBlock",
    "params": [block_number, {"transactionDetails": "full", "rewards": False, "maxSupportedTransactionVersion": 0}]
}

data = None
try:
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    fname = f"block_{block_number}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Đã tạo file {fname}")
except Exception as e:
    print(f"Error: {e}")
    exit(1)

txns = data.get('result', {}).get('transactions', [])

system_program = '11111111111111111111111111111111'
sol_transfer_txs = []

for idx, tx in enumerate(txns):
    if not isinstance(tx, dict) or 'transaction' not in tx:
        continue
    message = tx['transaction'].get('message', {})
    account_keys = message.get('accountKeys', [])
    instructions = message.get('instructions', [])
    meta = tx.get('meta', {})
    pre_balances = meta.get('preBalances', [])
    post_balances = meta.get('postBalances', [])
    for ix in instructions:
        prog_idx = ix.get('programIdIndex')
        acc_indices = ix.get('accounts', [])
        if prog_idx is not None and prog_idx < len(account_keys):
            if account_keys[prog_idx] == system_program:
                if len(acc_indices) >= 2 and max(acc_indices) < len(account_keys):
                    from_idx = acc_indices[0]
                    to_idx = acc_indices[1]
                    from_addr = account_keys[from_idx]
                    to_addr = account_keys[to_idx]
                    amount_sol = None
                    if pre_balances and post_balances and from_idx < len(pre_balances) and from_idx < len(post_balances):
                        amount = pre_balances[from_idx] - post_balances[from_idx]
                        amount_sol = amount / 1_000_000_000
                    sol_transfer_txs.append({
                        'tx_index': idx,
                        'signature': tx['transaction'].get('signatures', [''])[0] if 'transaction' in tx and 'signatures' in tx['transaction'] else '',
                        'accounts': [from_addr, to_addr],
                        'data': ix.get('data', ''),
                        'programIdIndex': prog_idx,
                        'amount_sol': amount_sol
                    })

log_name = f'sol_transfer_in_block_{block_number}.log'
with open(log_name, 'w', encoding='utf-8') as logf:
    logf.write(f"Tìm thấy {len(sol_transfer_txs)} transaction chuyển SOL trong block.\n")
    for t in sol_transfer_txs[:10]:
        logf.write(f"- Tx index: {t['tx_index']}, Signature: {t['signature']}\n")
        logf.write(f"  From: {t['accounts'][0] if t['accounts'] else '?'} -> To: {t['accounts'][1] if len(t['accounts'])>1 else '?'}\n")
        logf.write(f"  Số lượng: {t['amount_sol']} SOL\n")
        logf.write(f"  Data (base64): {t['data']}\n")
        logf.write(f"  programIdIndex: {t['programIdIndex']}\n\n")
    if sol_transfer_txs:
        logf.write("Đặc điểm nhận diện lệnh chuyển SOL:\n")
        logf.write("- programIdIndex trỏ tới account '11111111111111111111111111111111' (System Program)\n")
        logf.write("- Thường có 2 account đầu là from/to\n")
        logf.write("- Data là base64 encode của instruction 'transfer'\n")
    else:
        logf.write("Không tìm thấy transaction chuyển SOL nào trong block này.\n")
