# BNB Whale Alert Realtime (template)
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os
import logging

from .bnb_cex_dex_wallets import classify_transaction

USER_SEEN_BLOCK_FILE = "bnb_whale_user_seen_block.json"
HISTORY_FILE = "bnb_whale_alert_history.json"
BLOCK_FILE = "bnb_whale_last_block.json"

# Configure logging
logging.basicConfig(filename="bnb_whale_scanner.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- User seen block logic ---
def mark_bnb_whale_alert_seen():
    last_block = load_last_block()
    with open(USER_SEEN_BLOCK_FILE, "w") as f:
        json.dump({"seen_block": last_block}, f)

def load_user_seen_block():
    if os.path.exists(USER_SEEN_BLOCK_FILE):
        with open(USER_SEEN_BLOCK_FILE, "r") as f:
            data = json.load(f)
            return data.get("seen_block", 0)
    return 0

def check_bnb_whale_alert_has_new():
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    return last_block is not None and last_block > seen_block

# --- BNB block/tx fetch logic (placeholder, needs real API) ---
API_KEY = "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG"

# Updated fetch_latest_block_number to use Etherscan API V2 with chainid for BNB
def fetch_latest_block_number():
    url = f"https://api.etherscan.io/v2/api?chainid=56&module=proxy&action=eth_blockNumber&apikey={API_KEY}"
    r = requests.get(url, timeout=10)
    data = r.json()
    block_number = data.get("result")
    if not block_number:
        raise ValueError("Failed to fetch the latest block number.")
    return int(block_number, 16)

# Updated fetch_block_transactions to handle API errors and format transactions correctly
def fetch_block_transactions(block_number):
    url = f"https://api.etherscan.io/v2/api?chainid=56&module=proxy&action=eth_getBlockByNumber&tag={hex(block_number)}&boolean=true&apikey={API_KEY}"
    r = requests.get(url, timeout=10)
    try:
        data = r.json()
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON response for block {block_number}: {r.text}")
        raise ValueError("Failed to decode JSON response from API.")

    if not isinstance(data, dict):
        logging.error(f"Unexpected response format for block {block_number}: {data}")
        raise ValueError("Unexpected response format from API.")

    if "result" not in data or not isinstance(data["result"], dict):
        logging.error(f"API returned error for block {block_number}: {data}")
        raise ValueError(f"API error: {data.get('error', 'Unknown error')}")

    txs = data["result"].get("transactions", [])
    if not isinstance(txs, list):
        logging.error(f"Unexpected transactions format for block {block_number}: {txs}")
        raise ValueError(f"Unexpected transactions format for block {block_number}.")

    # Ensure transactions are formatted correctly
    formatted_txs = []
    for tx in txs:
        try:
            formatted_txs.append({
                "hash": tx.get("hash"),
                "from": tx.get("from"),
                "to": tx.get("to"),
                "value": int(tx.get("value", "0"), 16) / 1e18,  # Convert value to BNB
                "timeStamp": tx.get("timeStamp"),
            })
        except Exception as e:
            logging.error(f"Error formatting transaction {tx}: {e}")

    return formatted_txs

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

def show_bnb_whale_alert_realtime(min_value_bnb=250, num_blocks=100):
    st.markdown("""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - BNB Large Transactions
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
            box_content += f"<div style='margin-bottom:8px;'>{new_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx['value']:.2f} BNB</span> | Hash: <code>{tx['hash'][:12]}...</code> | Từ: <code>{tx['from']}</code> → Đến: <code>{tx['to']}</code> | <span style='color:#888;'>{tx['time']}</span></div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

# Updated background_whale_alert_scanner to continue scanning even if an error occurs
def background_whale_alert_scanner(min_value_bnb=250, num_blocks=100, interval_sec=300):
    while True:
        try:
            logging.info("Starting block scan...")
            latest_block = fetch_latest_block_number()
            if not latest_block:
                logging.warning("Failed to fetch the latest block number.")
                time.sleep(interval_sec)
                continue
            logging.info(f"Latest block number: {latest_block}")
            last_scanned = load_last_block()
            start_block = latest_block
            end_block = latest_block - num_blocks + 1
            if last_scanned and last_scanned >= end_block:
                end_block = last_scanned + 1
            logging.info(f"Scanning blocks from {start_block} to {end_block}")
            whale_txs = load_whale_history()
            seen_hashes = set(tx['hash'] for tx in whale_txs)
            for block_num in range(start_block, end_block - 1, -1):
                try:
                    txs = fetch_block_transactions(block_num)
                    total_bnb = sum(tx.get("value", 0) for tx in txs)
                    logging.info(f"Block {block_num} contains a total of {total_bnb:.2f} BNB")
                    for tx in txs:
                        value_bnb = tx.get("value", 0)
                        tx_hash = tx.get("hash", "")
                        to_addr = (tx.get("to") or "").lower()
                        from_addr = (tx.get("from") or "").lower()
                        if value_bnb >= min_value_bnb and tx_hash not in seen_hashes:
                            tx_type = classify_transaction(from_addr, to_addr)
                            tx_obj = {
                                "block": block_num,
                                "hash": tx_hash,
                                "from": from_addr,
                                "to": to_addr,
                                "value": value_bnb,
                                "time": datetime.utcfromtimestamp(int(tx.get("timeStamp", "0")) if tx.get("timeStamp") else int(time.time())).strftime("%Y-%m-%d %H:%M:%S"),
                                "type": tx_type,
                            }
                            whale_txs.append(tx_obj)
                            seen_hashes.add(tx_hash)
                            logging.info(f"Logged whale transaction: {tx_obj}")
                except Exception as e:
                    logging.error(f"Error processing block {block_num}: {e}")
            save_last_block(start_block)
            whale_txs = [tx for tx in whale_txs if tx['value'] >= min_value_bnb]
            whale_txs = whale_txs[-1000:]
            save_whale_history(whale_txs)
            logging.info("Block scan completed and history updated.")
        except Exception as e:
            logging.error(f"Error during block scan: {e}")
        time.sleep(interval_sec)

if "_bnb_whale_bg_thread" not in globals():
    t = threading.Thread(target=background_whale_alert_scanner, args=(250, 100, 300), daemon=True)
    t.start()
    _bnb_whale_bg_thread = True
