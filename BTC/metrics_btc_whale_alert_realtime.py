# BTC Whale Alert Realtime (template)
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os
import html
from cloud_db import db

LOG_FILE = "btc_whale_scanner.log"

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
    # Giá trị từ file local
    local_last_block = None
    if os.path.exists(BLOCK_FILE):
        with open(BLOCK_FILE, "r") as f:
            data = json.load(f)
            local_last_block = data.get("last_block", None)

    if db.available():
        # Giá trị từ database
        kv = db.get_kv("btc_meta", "last_block")
        db_last_block = kv.get("last_block") if kv and isinstance(kv, dict) else None

        # Gộp giá trị từ file local vào database nếu cần
        if local_last_block and (db_last_block is None or local_last_block > db_last_block):
            db.set_kv("btc_meta", "last_block", {"last_block": local_last_block})
            print(f"Gộp giá trị last_block {local_last_block} từ file local vào database.")

        # Trả về giá trị từ database
        return db.get_kv("btc_meta", "last_block").get("last_block")

    # Nếu database không khả dụng, trả về giá trị từ file local
    return local_last_block

def save_last_block(block_num):
    if db.available():
        try:
            db.set_kv("btc_meta", "last_block", {"last_block": int(block_num)})
            print(f"Saved last block: {block_num}")
        except Exception as e:
            print(f"Error saving last block: {e}")

def load_whale_history():
    # Prefer cloud DB if available
    local_history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            local_history = json.load(f)

    if db.available():
        # Lấy dữ liệu từ database
        db_history = db.find_all("btc_whale_history", sort_field="time", ascending=True)
        db_hashes = {d.get("hash") for d in db_history if isinstance(d, dict) and "hash" in d}

        # Gộp dữ liệu từ file local vào database
        new_entries = [entry for entry in local_history if entry.get("hash") not in db_hashes]
        if new_entries:
            db.upsert_many("btc_whale_history", new_entries, unique_keys=["hash"])
            print(f"Gộp {len(new_entries)} giao dịch từ file local vào database.")

        # Trả về dữ liệu đã gộp
        return db.find_all("btc_whale_history", sort_field="time", ascending=True)

    # Nếu database không khả dụng, trả về dữ liệu từ file local
    return local_history

def save_whale_history(history):
    # Save to cloud first if available
    if db.available() and isinstance(history, list):
        # Upsert by unique key 'hash'
        db.upsert_many("btc_whale_history", history, unique_keys=["hash"])
    # Always keep local backup
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

# --- Helpers & logging ---
def _log(msg: str):
    try:
        line = f"[{datetime.utcnow()}] {msg}"
        with open(LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(line + "\n")

        if db.available():
            # Gộp log từ file local vào database
            with open(LOG_FILE, "r", encoding="utf-8") as logf:
                local_logs = [{"ts": datetime.utcnow().isoformat(), "line": line.strip()} for line in logf]
            db.insert_many("btc_logs", local_logs)
            print(f"Gộp {len(local_logs)} log từ file local vào database.")
    except Exception:
        pass

def _extract_addrs(tx):
    """Safely extract first input and output addresses from a blockchain.info tx object."""
    from_addr = "unknown"
    to_addr = "unknown"
    try:
        if isinstance(tx.get('inputs'), list) and tx['inputs']:
            prev_out = tx['inputs'][0].get('prev_out') or {}
            from_addr = prev_out.get('addr', 'unknown') or 'unknown'
        if isinstance(tx.get('out'), list) and tx['out']:
            to_addr = tx['out'][0].get('addr', 'unknown') or 'unknown'
    except Exception:
        pass
    return from_addr, to_addr

def fetch_recent_whales_once(min_value_btc, num_blocks=5):
    """Synchronous fetch of recent blocks to populate large BTC transfers when history is empty."""
    try:
        latest_block = fetch_latest_block_number()
        if not latest_block:
            _log("[ONDEMAND] latest_block not available")
            return []
        start = int(latest_block)
        end = start - max(1, int(num_blocks)) + 1
        seen = {tx.get('hash') for tx in load_whale_history()}
        results = []
        try:
            from BTC.btc_cex_dex_wallets import is_cex_wallet
        except Exception:
            is_cex_wallet = lambda a: False
        for b in range(start, end - 1, -1):
            try:
                txs = fetch_block_transactions(b)
            except Exception as e:
                _log(f"[ONDEMAND] error fetch block {b}: {e}")
                continue
            for tx in txs:
                if 'hash' not in tx or 'out' not in tx:
                    continue
                value_btc = sum(out.get('value', 0) for out in tx.get('out', [])) / 1e8
                if value_btc < float(min_value_btc):
                    continue
                h = tx.get('hash')
                if h in seen:
                    continue
                from_addr, to_addr = _extract_addrs(tx)
                tx_type = 'SELL' if is_cex_wallet(to_addr) else ('BUY' if is_cex_wallet(from_addr) else 'N/A')
                results.append({
                    "block": b,
                    "hash": h,
                    "from": from_addr,
                    "to": to_addr,
                    "value": value_btc,
                    "time": datetime.utcfromtimestamp(tx.get('time', int(time.time()))).strftime("%Y-%m-%d %H:%M:%S"),
                    "type": tx_type
                })
                seen.add(h)
        if results:
            hist = load_whale_history()
            by_hash = {t.get('hash'): t for t in hist}
            for r in results:
                by_hash[r['hash']] = r
            merged = list(by_hash.values())
            save_whale_history(merged)
            _log(f"[ONDEMAND] saved {len(results)} new whales, total {len(merged)}")
        return results
    except Exception as e:
        _log(f"[ONDEMAND] fatal: {e}")
        return []

def show_btc_whale_alert_realtime(min_value_btc=100, num_blocks=5):
    st.markdown("""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - BTC Large Transactions
</div>
""", unsafe_allow_html=True)
    whale_txs = load_whale_history()
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    # Wallet labeling
    try:
        from BTC.btc_cex_dex_wallets import ADDRESS_LABELS
    except Exception:
        ADDRESS_LABELS = {}
    box_content = ""
    # helpers to render safe HTML fragments
    def _esc(x):
        try:
            return html.escape(str(x)) if x is not None else ""
        except Exception:
            return ""
    def _mono(x):
        return f"<span style='font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; background:#f1f3f5; padding:1px 4px; border-radius:3px;'>{_esc(x)}</span>"
    if not whale_txs:
        # Trigger a quick fetch to avoid empty UI if background thread hasn't populated yet
        _log("[UI] history empty -> trigger on-demand fetch")
        whale_txs = fetch_recent_whales_once(min_value_btc=min_value_btc, num_blocks=num_blocks)
        if not whale_txs:
            box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
    else:
        for tx in whale_txs[::-1]:
            # Skip transactions without 'value' or 'hash'
            if 'value' not in tx or 'hash' not in tx:
                print("Skipping transaction without required keys")
                continue
            is_new = (last_block is not None and tx.get('block', 0) > seen_block)
            new_badge = "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>" if is_new else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
            from_addr = tx.get('from', '')
            to_addr = tx.get('to', '')
            from_label = ADDRESS_LABELS.get((from_addr or '').lower(), from_addr)
            to_label = ADDRESS_LABELS.get((to_addr or '').lower(), to_addr)
            tx_type = tx.get('type', 'N/A')
            if tx_type == 'SELL':
                type_badge = "<span style='color:#fff;background:#e53935;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>SELL</span>"
            elif tx_type == 'BUY':
                type_badge = "<span style='color:#fff;background:#1e88e5;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>BUY</span>"
            else:
                type_badge = "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>N/A</span>"
            # Build safe, escaped HTML without raw <code> tags to avoid InvalidCharacterError
            h_preview = (tx.get('hash') or '')[:12] + '...'
            time_str = tx.get('time', '')
            box_content += (
                "<div style='margin-bottom:8px;'>"
                f"{new_badge}{type_badge}"
                f"<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx['value']:.2f} BTC</span> | "
                f"Hash: {_mono(h_preview)} | "
                f"From: {_mono(from_label)} → To: {_mono(to_label)} | "
                f"<span style='color:#888;'>{_esc(time_str)}</span>"
                "</div>"
            )
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

def background_whale_alert_scanner(min_value_btc=300, num_blocks=5, interval_sec=300):
    while True:
        try:
            latest_block = fetch_latest_block_number()
            if not latest_block:
                _log("[BG] latest_block not available")
                time.sleep(interval_sec)
                continue
            last_scanned = load_last_block()
            start_block = latest_block
            end_block = latest_block - max(1, int(num_blocks)) + 1
            if last_scanned and last_scanned >= end_block:
                end_block = last_scanned + 1
            whale_txs = load_whale_history()
            seen_hashes = set(tx['hash'] for tx in whale_txs)
            try:
                from BTC.btc_cex_dex_wallets import is_cex_wallet
            except Exception:
                is_cex_wallet = lambda a: False
            appended = False
            _log(f"[BG] scanning blocks {start_block} -> {end_block}")
            for block_num in range(start_block, end_block - 1, -1):
                txs = fetch_block_transactions(block_num)
                for tx in txs:
                    # blockchain.info tx doesn't include top-level 'value'; sum outputs instead
                    if 'hash' not in tx or 'out' not in tx:
                        # Nếu muốn log cảnh báo, dùng logging.warning thay vì print
                        continue
                    value_btc = sum(out.get('value', 0) for out in tx.get('out', [])) / 1e8
                    tx_hash = tx.get('hash', '')
                    from_addr, to_addr = _extract_addrs(tx)
                    if is_cex_wallet(to_addr):
                        tx_type = 'SELL'
                    elif is_cex_wallet(from_addr):
                        tx_type = 'BUY'
                    else:
                        tx_type = 'N/A'
                    if value_btc >= min_value_btc and tx_hash not in seen_hashes:
                        tx_obj = {
                            "block": block_num,
                            "hash": tx_hash,
                            "from": from_addr,
                            "to": to_addr,
                            "value": value_btc,
                            "time": datetime.utcfromtimestamp(tx.get('time', int(time.time()))).strftime("%Y-%m-%d %H:%M:%S"),
                            "type": tx_type
                        }
                        whale_txs.append(tx_obj)
                        seen_hashes.add(tx_hash)
                        appended = True
            save_last_block(start_block)
            # Chỉ ghi file nếu có giao dịch lớn mới
            if appended:
                save_whale_history(whale_txs)
        except Exception as e:
            _log(f"[BG] error: {e}")
        time.sleep(interval_sec)

# --- Standardized Transaction Type Logic ---
def determine_transaction_type(value):
    """
    Determine the transaction type based on value.
    """
    if value > 0:
        return "BUY"
    elif value < 0:
        return "SELL"
    return "N/A"

# --- Overlay Marker Logic ---
def add_overlay_marker(transaction):
    """
    Add overlay marker for the transaction.
    """
    transaction_type = determine_transaction_type(transaction.get("value", 0))
    marker = {
        "type": transaction_type,
        "color": "green" if transaction_type == "BUY" else "red" if transaction_type == "SELL" else "gray",
        "size": abs(transaction.get("value", 0))
    }
    return marker

# Example usage in existing logic
# transactions = fetch_block_transactions(last_block)
# for tx in transactions:
#     marker = add_overlay_marker(tx)
#     # Add marker to visualization or log
#     print(f"Transaction {tx['hash']} marked as {marker['type']} with color {marker['color']}")

if "_btc_whale_bg_thread" not in globals():
    t = threading.Thread(target=background_whale_alert_scanner, args=(300, 5, 300), daemon=True)
    t.start()
    _btc_whale_bg_thread = True
