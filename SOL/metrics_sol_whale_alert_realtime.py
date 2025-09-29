# SOL Whale Alert Realtime (template)
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os
from .sol_cex_wallets import ALL_EXCHANGE_WALLETS, is_internal_exchange_transfer, is_exchange_wallet, is_org_wallet

USER_SEEN_BLOCK_FILE = "sol_whale_user_seen_block.json"
HISTORY_FILE = "sol_whale_alert_history.json"
BLOCK_FILE = "sol_whale_last_block.json"

# --- User seen block logic ---
def mark_sol_whale_alert_seen():
    last_block = load_last_block()
    with open(USER_SEEN_BLOCK_FILE, "w") as f:
        json.dump({"seen_block": last_block}, f)

def load_user_seen_block():
    if os.path.exists(USER_SEEN_BLOCK_FILE):
        with open(USER_SEEN_BLOCK_FILE, "r") as f:
            data = json.load(f)
            return data.get("seen_block", 0)
    return 0

def check_sol_whale_alert_has_new():
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    return last_block is not None and last_block > seen_block

# --- SOL block/tx fetch logic (placeholder, needs real API) ---
def fetch_latest_block_number():
    # Use Solana RPC node to get latest block height
    url = "https://api.mainnet-beta.solana.com"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getSlot"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("result")
    except Exception as e:
        with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_latest_block_number] {datetime.utcnow()} | Error: {e} | status: {getattr(r, 'status_code', 'N/A')} | text: {getattr(r, 'text', '')}\n")
        return None

def fetch_block_transactions(block_number):
    # Use Solana RPC node to get block transactions
    url = "https://api.mainnet-beta.solana.com"
    # Add maxSupportedTransactionVersion for full compatibility
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBlock",
        "params": [
            block_number,
            {
                "transactionDetails": "full",
                "rewards": False,
                "maxSupportedTransactionVersion": 0
            }
        ]
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            data = r.json()
            txs = data.get("result", {}).get("transactions", [])
            return txs
        except Exception as e:
            status = getattr(r, 'status_code', 'N/A')
            text = getattr(r, 'text', '')
            with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
                logf.write(f"[fetch_block_transactions] {datetime.utcnow()} | Error: {e} | status: {status} | text: {text}\n")
            # Nếu lỗi 429 thì sleep 5s rồi retry
            if status == 429 or (isinstance(text, str) and '429' in text):
                time.sleep(5)
                continue
            else:
                break
    return []

def fetch_blocks_with_transactions(start_slot, end_slot):
    # Use getBlocks to get list of blocks with transactions
    url = "https://api.mainnet-beta.solana.com"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getBlocks", "params": [start_slot, end_slot]}
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        blocks = data.get("result", [])
        return blocks
    except Exception as e:
        with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
            logf.write(f"[fetch_blocks_with_transactions] {datetime.utcnow()} | Error: {e} | status: {getattr(r, 'status_code', 'N/A')} | text: {getattr(r, 'text', '')}\n")
        return []
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

def show_sol_whale_alert_realtime(min_value_sol=1000, num_blocks=750):
    st.markdown("""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - SOL Large Transactions
</div>
""", unsafe_allow_html=True)
    whale_txs = load_whale_history()
    last_block = load_last_block()
    # Tự động cập nhật seen_block = last_block mỗi lần load dashboard
    if last_block is not None:
        with open(USER_SEEN_BLOCK_FILE, "w") as f:
            json.dump({"seen_block": last_block}, f)
        seen_block = last_block
    else:
        seen_block = load_user_seen_block()
    box_content = ""
    if not whale_txs:
        box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
    else:
        for tx in whale_txs[::-1]:
            is_new = (last_block is not None and tx.get('block', 0) > seen_block)
            new_badge = "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>" if is_new else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
            # Hiển thị loại giao dịch
            tx_type = tx.get('type', 'other')
            if tx_type == 'deposit':
                type_badge = "<span style='color:#fff;background:#e53935;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>BÁN (Deposit CEX)</span>"
            elif tx_type == 'withdraw':
                type_badge = "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>MUA (Withdraw CEX)</span>"
            else:
                type_badge = "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>N/A</span>"
            box_content += f"<div style='margin-bottom:8px;'>{new_badge}{type_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx['value']:.2f} SOL</span> | Hash: <code>{tx['hash'][:12]}...</code> | Từ: <code>{tx['from']}</code> → Đến: <code>{tx['to']}</code> | <span style='color:#888;'>{tx['time']}</span></div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

def background_whale_alert_scanner(min_value_sol=1000, num_blocks=750, interval_sec=300):
    # Load danh sách protocol address từ Solana-programs.json
    protocol_addr_to_name = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "Solana-programs.json"), "r", encoding="utf-8") as f:
            protocol_json = json.load(f)
            protocol_addr_to_name = protocol_json.get("program", {})
    except Exception:
        protocol_addr_to_name = {}

    while True:
        try:
            with open("solscan_api_error.log", "w", encoding="utf-8") as logf:
                logf.write("")
            latest_block = fetch_latest_block_number()
            if not latest_block:
                time.sleep(interval_sec)
                continue
            last_scanned = load_last_block()
            start_block = latest_block
            end_block = latest_block - num_blocks + 1
            if last_scanned and last_scanned >= end_block:
                end_block = last_scanned + 1
            blocks_with_tx = fetch_blocks_with_transactions(end_block, start_block)
            whale_txs = load_whale_history()
            seen_hashes = set(tx['hash'] for tx in whale_txs)
            for block_num in blocks_with_tx[::-1]:
                try:
                    txs = fetch_block_transactions(block_num)
                    sol_found = 0
                    total_sol_transferred = 0
                    for tx in txs:
                        tx_hash = tx.get('transaction', {}).get('signatures', [''])[0]
                        block_time = tx.get('blockTime', None)
                        message = tx.get('transaction', {}).get('message', {})
                        account_keys = message.get('accountKeys', [])
                        instructions = message.get('instructions', [])
                        meta = tx.get('meta', {})
                        pre_balances = meta.get('preBalances', [])
                        post_balances = meta.get('postBalances', [])
                        for ix in instructions:
                            prog_idx = ix.get('programIdIndex', None)
                            # Kiểm tra programIdIndex hợp lệ và là System Program
                            if prog_idx is not None and prog_idx < len(account_keys) and account_keys[prog_idx] == '11111111111111111111111111111111':
                                accounts = ix.get('accounts', [])
                                if len(accounts) >= 2:
                                    from_idx, to_idx = accounts[0], accounts[1]
                                    if (isinstance(from_idx, int) and isinstance(to_idx, int)
                                        and from_idx < len(account_keys) and to_idx < len(account_keys)
                                        and from_idx < len(pre_balances) and to_idx < len(post_balances)):
                                        from_addr = account_keys[from_idx]
                                        to_addr = account_keys[to_idx]
                                        # Bỏ qua giao dịch nội bộ giữa các ví sàn/lưu ký
                                        if is_internal_exchange_transfer(from_addr, to_addr):
                                            continue
                                        try:
                                            amount = (pre_balances[from_idx] - post_balances[from_idx]) / 1e9
                                        except Exception as e:
                                            amount = 0
                                            with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
                                                logf.write(f"[block {block_num}] {datetime.utcnow()} | Error tính amount: {e} | from_idx: {from_idx}, to_idx: {to_idx}\n")
                                        if amount > 0:
                                            total_sol_transferred += amount
                                        if amount >= min_value_sol and tx_hash not in seen_hashes:
                                            sol_found += amount
                                            protocol_from = protocol_addr_to_name.get(from_addr)
                                            protocol_to = protocol_addr_to_name.get(to_addr)
                                            if to_addr in ALL_EXCHANGE_WALLETS:
                                                tx_type = 'deposit'
                                            elif from_addr in ALL_EXCHANGE_WALLETS:
                                                tx_type = 'withdraw'
                                            elif protocol_from:
                                                tx_type = 'protocol_from'
                                            elif protocol_to:
                                                tx_type = 'protocol_to'
                                            else:
                                                tx_type = 'other'
                                            # Gán nhãn cho from/to là sàn hoặc tổ chức nếu có
                                            from_label = None
                                            to_label = None
                                            if is_exchange_wallet(from_addr):
                                                from_label = "exchange"
                                            elif is_org_wallet(from_addr):
                                                from_label = "org"
                                            if is_exchange_wallet(to_addr):
                                                to_label = "exchange"
                                            elif is_org_wallet(to_addr):
                                                to_label = "org"
                                            tx_obj = {
                                                "block": block_num,
                                                "hash": tx_hash,
                                                "from": from_addr,
                                                "to": to_addr,
                                                "from_label": from_label,
                                                "to_label": to_label,
                                                "value": amount,
                                                "type": tx_type,
                                                "protocol_from": protocol_from,
                                                "protocol_to": protocol_to,
                                                "time": datetime.utcfromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                            }
                                            whale_txs.append(tx_obj)
                                            seen_hashes.add(tx_hash)
                                            # Ghi ngay vào history mỗi khi phát hiện giao dịch lớn
                                            # Giữ lại tối đa 2000 giao dịch lớn nhất gần đây
                                            whale_txs_recent = [tx for tx in whale_txs if tx['value'] >= min_value_sol]
                                            whale_txs_recent = whale_txs_recent[-2000:]
                                            save_whale_history(whale_txs_recent)
                        for ix in instructions:
                            prog_idx = ix.get('programIdIndex', None)
                            # Kiểm tra programIdIndex hợp lệ và là System Program
                            if prog_idx is not None and prog_idx < len(account_keys) and account_keys[prog_idx] == '11111111111111111111111111111111':
                                accounts = ix.get('accounts', [])
                                if len(accounts) >= 2:
                                    from_idx, to_idx = accounts[0], accounts[1]
                                    if (isinstance(from_idx, int) and isinstance(to_idx, int)
                                        and from_idx < len(account_keys) and to_idx < len(account_keys)
                                        and from_idx < len(pre_balances) and to_idx < len(post_balances)):
                                        from_addr = account_keys[from_idx]
                                        to_addr = account_keys[to_idx]
                                        try:
                                            amount = (pre_balances[from_idx] - post_balances[from_idx]) / 1e9
                                        except Exception as e:
                                            amount = 0
                                            with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
                                                logf.write(f"[block {block_num}] {datetime.utcnow()} | Error tính amount: {e} | from_idx: {from_idx}, to_idx: {to_idx}\n")
                                        if amount > 0:
                                            total_sol_transferred += amount
                                        if amount >= min_value_sol and tx_hash not in seen_hashes:
                                            sol_found += amount
                                            protocol_from = protocol_addr_to_name.get(from_addr)
                                            protocol_to = protocol_addr_to_name.get(to_addr)
                                            if to_addr in ALL_EXCHANGE_WALLETS:
                                                tx_type = 'deposit'
                                            elif from_addr in ALL_EXCHANGE_WALLETS:
                                                tx_type = 'withdraw'
                                            elif protocol_from:
                                                tx_type = 'protocol_from'
                                            elif protocol_to:
                                                tx_type = 'protocol_to'
                                            else:
                                                tx_type = 'other'
                                            # Gán nhãn cho from/to là sàn hoặc tổ chức nếu có
                                            from_label = None
                                            to_label = None
                                            if is_exchange_wallet(from_addr):
                                                from_label = "exchange"
                                            elif is_org_wallet(from_addr):
                                                from_label = "org"
                                            if is_exchange_wallet(to_addr):
                                                to_label = "exchange"
                                            elif is_org_wallet(to_addr):
                                                to_label = "org"
                                            tx_obj = {
                                                "block": block_num,
                                                "hash": tx_hash,
                                                "from": from_addr,
                                                "to": to_addr,
                                                "from_label": from_label,
                                                "to_label": to_label,
                                                "value": amount,
                                                "type": tx_type,
                                                "protocol_from": protocol_from,
                                                "protocol_to": protocol_to,
                                                "time": datetime.utcfromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                            }
                                            whale_txs.append(tx_obj)
                                            seen_hashes.add(tx_hash)
                                            # Ghi ngay vào history mỗi khi phát hiện giao dịch lớn
                                            # Giữ lại tối đa 100 giao dịch lớn nhất gần đây
                                            whale_txs_recent = [tx for tx in whale_txs if tx['value'] >= min_value_sol]
                                            whale_txs_recent = whale_txs_recent[-100:]
                                            save_whale_history(whale_txs_recent)
                    with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
                        logf.write(f"[block {block_num}] {datetime.utcnow()} | num_txs: {len(txs)} | Tổng SOL lớn phát hiện: {sol_found:.2f} | Tổng SOL phát hiện: {total_sol_transferred:.2f}\n")
                    save_last_block(block_num)
                    time.sleep(0.3)
                except Exception as e:
                    with open("solscan_api_error.log", "a", encoding="utf-8") as logf:
                        logf.write(f"[block {block_num}] {datetime.utcnow()} | Exception: {e}\n")
            whale_txs = [tx for tx in whale_txs if tx['value'] >= min_value_sol]
            whale_txs = whale_txs[-2000:]
            save_whale_history(whale_txs)
        except Exception:
            pass
        time.sleep(interval_sec)

# --- Tự động khởi động background scanner khi import module (chỉ chạy 1 lần) ---
if '_sol_whale_scanner_started' not in globals():
    t = threading.Thread(target=background_whale_alert_scanner, daemon=True)
    t.start()
    _sol_whale_scanner_started = True
