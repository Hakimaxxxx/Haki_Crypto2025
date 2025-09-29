# BTC Whale Alert Realtime (template)
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os

USER_SEEN_BLOCK_FILE = "btc_whale_user_seen_block.json"
HISTORY_FILE = "btc_whale_alert_history.json"
BLOCK_FILE = "btc_whale_last_block.json"

# --- User seen block logic ---
def mark_btc_whale_alert_seen():
    last_block = load_last_block()
    with open(USER_SEEN_BLOCK_FILE, "w") as f:
        json.dump({"seen_block": last_block}, f)

def load_user_seen_block():
    if os.path.exists(USER_SEEN_BLOCK_FILE):
        with open(USER_SEEN_BLOCK_FILE, "r") as f:
            data = json.load(f)
            return data.get("seen_block", 0)
    return 0

def check_btc_whale_alert_has_new():
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    return last_block is not None and last_block > seen_block

# --- BTC block/tx fetch logic (placeholder, needs real API) ---
def fetch_latest_block_number():
    url = "https://blockchain.info/latestblock"
    r = requests.get(url, timeout=10)
    data = r.json()
    return data.get("height")

def fetch_block_transactions(block_number):
    url = f"https://blockchain.info/block-height/{block_number}?format=json"
    r = requests.get(url, timeout=10)
    data = r.json()
    blocks = data.get("blocks", [])
    if not blocks:
        return []
    return blocks[0].get("tx", [])

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

def show_btc_whale_alert_realtime(min_value_btc=100, num_blocks=5):
    st.markdown("""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - BTC Large Transactions
</div>
""", unsafe_allow_html=True)
    whale_txs = load_whale_history()
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    box_content = ""
    if not whale_txs:
        box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
    else:
        for tx in whale_txs[::-1]:
            is_new = (last_block is not None and tx.get('block', 0) > seen_block)
            new_badge = "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>" if is_new else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
            box_content += f"<div style='margin-bottom:8px;'>{new_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx['value']:.2f} BTC</span> | Hash: <code>{tx['hash'][:12]}...</code> | Từ: <code>{tx['from']}</code> → Đến: <code>{tx['to']}</code> | <span style='color:#888;'>{tx['time']}</span></div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

def background_whale_alert_scanner(min_value_btc=5, num_blocks=5, interval_sec=300):
    while True:
        try:
            latest_block = fetch_latest_block_number()
            if not latest_block:
                time.sleep(interval_sec)
                continue
            last_scanned = load_last_block()
            start_block = latest_block
            end_block = latest_block - num_blocks + 1
            if last_scanned and last_scanned >= end_block:
                end_block = last_scanned + 1
            whale_txs = load_whale_history()
            seen_hashes = set(tx['hash'] for tx in whale_txs)
            for block_num in range(start_block, end_block - 1, -1):
                txs = fetch_block_transactions(block_num)
                for tx in txs:
                    value_btc = sum([out.get('value', 0) for out in tx.get('out', [])]) / 1e8
                    tx_hash = tx.get('hash', '')
                    from_addr = tx.get('inputs', [{}])[0].get('prev_out', {}).get('addr', 'unknown')
                    to_addr = tx.get('out', [{}])[0].get('addr', 'unknown')
                    if value_btc >= min_value_btc and tx_hash not in seen_hashes:
                        tx_obj = {
                            "block": block_num,
                            "hash": tx_hash,
                            "from": from_addr,
                            "to": to_addr,
                            "value": value_btc,
                            "time": datetime.utcfromtimestamp(tx.get('time', int(time.time()))).strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        whale_txs.append(tx_obj)
                        seen_hashes.add(tx_hash)
            save_last_block(start_block)
            whale_txs = [tx for tx in whale_txs if tx['value'] >= min_value_btc]
            whale_txs = whale_txs[-100:]
            save_whale_history(whale_txs)
        except Exception:
            pass
        time.sleep(interval_sec)

if "_btc_whale_bg_thread" not in globals():
    t = threading.Thread(target=background_whale_alert_scanner, args=(100, 5, 300), daemon=True)
    t.start()
    _btc_whale_bg_thread = True
