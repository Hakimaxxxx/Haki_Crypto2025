import requests
import json

block_number = 369810960
url = "https://api.mainnet-beta.solana.com"
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getBlock",
    "params": [block_number, {"transactionDetails": "full", "rewards": False, "maxSupportedTransactionVersion": 0}]
}

try:
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    # Ghi raw JSON response ra file
    with open("block_369810960.json", "w", encoding="utf-8") as f:
        json.dump(r.json(), f, ensure_ascii=False, indent=2)
    print("Đã tạo file block_369810960.json")
except Exception as e:
    print(f"Error: {e}")
