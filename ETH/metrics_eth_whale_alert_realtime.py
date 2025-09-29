# File lưu block cuối cùng user đã xem khi vào tab ETH
USER_SEEN_BLOCK_FILE = "eth_whale_user_seen_block.json"
USER_SEEN_HASH_FILE = "eth_whale_user_seen_hash.json"

# Lưu block cuối cùng user đã xem (gọi khi chuyển sang tab ETH)
def mark_eth_whale_alert_seen():
    whale_txs = load_whale_history()
    last_block = load_last_block()
    # Lưu block như cũ để không ảnh hưởng logic cũ
    with open(USER_SEEN_BLOCK_FILE, "w") as f:
        json.dump({"seen_block": last_block}, f)
    # Lưu hash giao dịch whale mới nhất (nếu có)
    if whale_txs:
        last_hash = whale_txs[-1]["hash"]
        with open(USER_SEEN_HASH_FILE, "w") as f:
            json.dump({"seen_hash": last_hash}, f)

# Lấy block cuối cùng user đã xem
def load_user_seen_block():
    if os.path.exists(USER_SEEN_BLOCK_FILE):
        with open(USER_SEEN_BLOCK_FILE, "r") as f:
            data = json.load(f)
            return data.get("seen_block", 0)
    return 0

def load_user_seen_hash():
    if os.path.exists(USER_SEEN_HASH_FILE):
        with open(USER_SEEN_HASH_FILE, "r") as f:
            data = json.load(f)
            return data.get("seen_hash", None)
    return None

# Hàm check có alert mới chưa xem (dùng cho dashboard để làm tab sáng)
def check_eth_whale_alert_has_new():
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    return last_block is not None and last_block > seen_block
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os

def get_eth_api_key():
    API_KEY_FILE = "eth_api_key.json"
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r") as f:
            data = json.load(f)
            return data.get("api_key", "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG")
    return "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG"

def fetch_latest_block_number(api_key):
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 1,
        "module": "proxy",
        "action": "eth_blockNumber",
        "apikey": api_key
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_latest_block_number][V2] status={r.status_code}, url={r.url}, data={data}\n")
        block_hex = data.get("result")
        if not block_hex:
            return None
        return int(block_hex, 16)
    except Exception as e:
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_latest_block_number][V2][ERROR] {e}\n")
        return None

def fetch_block_transactions(block_number, api_key):
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 1,
        "module": "proxy",
        "action": "eth_getBlockByNumber",
        "tag": hex(block_number),
        "boolean": "true",
        "apikey": api_key
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_block_transactions][V2] block={block_number}, status={r.status_code}, url={r.url}, data_keys={list(data.keys())}\n")
        txs = data.get("result", {}).get("transactions", [])
        return txs
    except Exception as e:
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_block_transactions][V2][ERROR] block={block_number}, {e}\n")
        return []


HISTORY_FILE = "eth_whale_alert_history.json"
BLOCK_FILE = "eth_whale_last_block.json"

def load_last_block():
    if os.path.exists(BLOCK_FILE):
        with open(BLOCK_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_block", None)
    return None

def save_last_block(block_num):
    with open(BLOCK_FILE, "w") as f:
        json.dump({"last_block": block_num}, f)

def load_whale_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_whale_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

def show_eth_whale_alert_realtime(min_value_eth=100, num_blocks=5):
    st.markdown("""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - ETH Large Transactions
</div>
""", unsafe_allow_html=True)
    whale_txs = load_whale_history()
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    seen_hash = load_user_seen_hash()
    box_content = ""
    if not whale_txs:
        box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
    else:
        # Danh sách mapping ví sàn để hiển thị tên sàn
        exchange_wallets = {
            '0x28c6c06298d514db089934071355e5743bf21d60': 'Binance',
            '0x564286362092d8e7936f0549571a803b203aaced': 'Binance',
            '0x742d35cc6634c0532925a3b844bc454e4438f44e': 'Bitfinex',
            '0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0': 'Binance',
            '0x53d284357ec70ce289d6d64134dfac8e511c8a3d': 'Kraken',
            '0x66f820a414680b5bcda5eeca5dea238543f42054': 'OKX',
            '0x21a31ee1afc51d94c2efccaa2092ad1028285549': 'Huobi',
            '0xf977814e90da44bfa03b6295a0616a897441acec': 'Binance',
        }
        found_seen = False
        for tx in whale_txs[::-1]:
            # Đánh dấu NEW cho đến khi gặp hash đã xem cuối cùng
            if not found_seen and seen_hash is not None and tx.get('hash') == seen_hash:
                found_seen = True
            is_new = not found_seen and seen_hash is not None
            new_badge = "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>" if is_new else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
            tx_type = tx.get('type', 'N/A')
            if tx_type == 'BÁN':
                type_badge = "<span style='color:#fff;background:#e53935;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>BÁN</span>"
            elif tx_type == 'MUA':
                type_badge = "<span style='color:#fff;background:#1e88e5;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>MUA</span>"
            else:
                type_badge = "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>N/A</span>"
            from_addr = tx.get('from', '')
            to_addr = tx.get('to', '')
            from_label = exchange_wallets.get(from_addr.lower(), from_addr)
            to_label = exchange_wallets.get(to_addr.lower(), to_addr)
            box_content += f"<div style='margin-bottom:8px;'>{new_badge}{type_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx['value']:.2f} ETH</span> | Hash: <code>{tx['hash'][:12]}...</code> | Từ: <code>{from_label}</code> → Đến: <code>{to_label}</code> | <span style='color:#888;'>{tx['time']}</span></div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

def background_whale_alert_scanner(min_value_eth=100, num_blocks=5, interval_sec=300):
    while True:
        try:
            api_key = get_eth_api_key()
            with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
                logf.write(f"[scanner] Start loop at {datetime.now()}\n")
            latest_block = fetch_latest_block_number(api_key)
            if not latest_block:
                with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
                    logf.write(f"[scanner] No latest_block, sleep {interval_sec}s\n")
                time.sleep(interval_sec)
                continue
            last_scanned = load_last_block()
            start_block = latest_block
            end_block = latest_block - num_blocks + 1
            if last_scanned and last_scanned >= end_block:
                end_block = last_scanned + 1
            whale_txs = load_whale_history()
            seen_hashes = set(tx['hash'] for tx in whale_txs)
            exchange_wallets = {
                '0x28c6c06298d514db089934071355e5743bf21d60': 'Binance',
                '0x564286362092d8e7936f0549571a803b203aaced': 'Binance',
                '0x742d35cc6634c0532925a3b844bc454e4438f44e': 'Bitfinex',
                '0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0': 'Binance',
                '0x53d284357ec70ce289d6d64134dfac8e511c8a3d': 'Kraken',
                '0x66f820a414680b5bcda5eeca5dea238543f42054': 'OKX',
                '0x21a31ee1afc51d94c2efccaa2092ad1028285549': 'Huobi',
                '0xf977814e90da44bfa03b6295a0616a897441acec': 'Binance',
            }
            for block_num in range(start_block, end_block - 1, -1):
                txs = fetch_block_transactions(block_num, api_key)
                with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
                    logf.write(f"[scanner] block={block_num}, txs_count={len(txs)}\n")
                for tx in txs:
                    value_eth = int(tx.get("value", "0"), 16) / 1e18
                    tx_hash = tx.get("hash", "")
                    to_addr = (tx.get("to") or "").lower()
                    from_addr = (tx.get("from") or "").lower()
                    if value_eth >= min_value_eth and tx_hash not in seen_hashes:
                        from_label = exchange_wallets.get(from_addr, from_addr[:10]+"...")
                        to_label = exchange_wallets.get(to_addr, to_addr[:10]+"...")
                        tx_type = "BÁN" if to_addr in exchange_wallets else "MUA"
                        tx_obj = {
                            "block": block_num,
                            "hash": tx_hash,
                            "from": from_label,
                            "to": to_label,
                            "value": value_eth,
                            "time": datetime.utcfromtimestamp(int(tx.get("timeStamp", "0")) if tx.get("timeStamp") else int(time.time())).strftime("%Y-%m-%d %H:%M:%S"),
                            "type": tx_type
                        }
                        whale_txs.append(tx_obj)
                        seen_hashes.add(tx_hash)
            save_last_block(start_block)
            whale_txs = [tx for tx in whale_txs if tx['value'] >= min_value_eth]
            whale_txs = whale_txs[-2000:]
            save_whale_history(whale_txs)
            with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
                logf.write(f"[scanner] Done block {start_block} at {datetime.now()}, whale_txs={len(whale_txs)}\n")
        except Exception as e:
            with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
                logf.write(f"[scanner][ERROR] {e}\n")
        time.sleep(interval_sec)


# Chỉ khởi động thread background khi import module, không render UI
if "_whale_bg_thread" not in globals():
    t = threading.Thread(target=background_whale_alert_scanner, args=(100, 5, 300), daemon=True)
    t.start()
    _whale_bg_thread = True
