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
from cloud_db import db

from .bnb_cex_dex_wallets import classify_transaction

USER_SEEN_BLOCK_FILE = "bnb_whale_user_seen_block.json"
HISTORY_FILE = "bnb_whale_alert_history.json"
BLOCK_FILE = "bnb_whale_last_block.json"

# Configure logging
logging.basicConfig(filename="bnb_whale_scanner.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Define the log file for BNB whale scanner
LOG_FILE = "bnb_whale_scanner.log"

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

def load_whale_history():
    # Prefer cloud DB if available
    local_history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            local_history = json.load(f)

    if db.available():
        # Lấy dữ liệu từ database
        db_history = db.find_all("bnb_whale_history", sort_field="time", ascending=True)
        db_hashes = {d.get("hash") for d in db_history if isinstance(d, dict) and "hash" in d}

        # Gộp dữ liệu từ file local vào database
        new_entries = [entry for entry in local_history if entry.get("hash") not in db_hashes]
        if new_entries:
            db.upsert_many("bnb_whale_history", new_entries, unique_keys=["hash"])
            print(f"Gộp {len(new_entries)} giao dịch từ file local vào database.")

        # Trả về dữ liệu đã gộp
        return db.find_all("bnb_whale_history", sort_field="time", ascending=True)

    # Nếu database không khả dụng, trả về dữ liệu từ file local
    return local_history

def load_last_block():
    # Giá trị từ file local
    local_last_block = None
    if os.path.exists(BLOCK_FILE):
        with open(BLOCK_FILE, "r") as f:
            data = json.load(f)
            local_last_block = data.get("last_block", None)

    if db.available():
        # Giá trị từ database
        kv = db.get_kv("bnb_meta", "last_block")
        db_last_block = kv.get("last_block") if kv and isinstance(kv, dict) else None

        # Gộp giá trị từ file local vào database nếu cần
        if local_last_block and (db_last_block is None or local_last_block > db_last_block):
            db.set_kv("bnb_meta", "last_block", {"last_block": local_last_block})
            print(f"Gộp giá trị last_block {local_last_block} từ file local vào database.")

        # Trả về giá trị từ database
        return db.get_kv("bnb_meta", "last_block").get("last_block")

    # Nếu database không khả dụng, trả về giá trị từ file local
    return local_last_block

def _log(msg: str):
    try:
        line = f"[{datetime.utcnow()}] {msg}"
        with open(LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(line + "\n")

        if db.available():
            # Gộp log từ file local vào database
            with open(LOG_FILE, "r", encoding="utf-8") as logf:
                local_logs = [{"ts": datetime.utcnow().isoformat(), "line": line.strip()} for line in logf]
            db.insert_many("bnb_logs", local_logs)
            print(f"Gộp {len(local_logs)} log từ file local vào database.")
    except Exception:
        pass

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

# Function to save the last processed block number
def save_last_block(block_num):
    if db.available():
        try:
            db.set_kv("bnb_meta", "last_block", {"last_block": int(block_num)})
            print(f"Saved last block: {block_num}")
        except Exception as e:
            print(f"Error saving last block: {e}")
    # Always save to local file as a backup
    with open(BLOCK_FILE, "w") as f:
        json.dump({"last_block": block_num}, f)

# Function to save whale transaction history
def save_whale_history(history):
    # Save to cloud first if available
    if db.available() and isinstance(history, list):
        # Upsert by unique key 'hash'
        db.upsert_many("bnb_whale_history", history, unique_keys=["hash"])
    # Always keep a local backup
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

# Updated background_whale_alert_scanner to continue scanning even if an error occurs
def background_whale_alert_scanner(min_value_bnb=250, num_blocks=100, interval_sec=300):
    while True:
        try:
            logging.info("Starting block scan...")
            latest_block = fetch_latest_block_number()
            if not latest_block:
                #logging.warning("Failed to fetch the latest block number.")
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
                    #logging.info(f"Block {block_num} contains a total of {total_bnb:.2f} BNB")
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
