# ERC20 Whale Alert Realtime (generic for LINK, ETH, ...)
import threading
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import os
from cloud_db import db

# ERC20 token configs
LINK_CONTRACT = "0x514910771af9ca656af840dff83e8264ecf986ca"  # Chainlink ERC20
WETH_CONTRACT = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # Wrapped ETH ERC20
# Add more ERC20 contract addresses here

ERC20_TOKENS = [
    {
        "name": "ETH",
        "contract": WETH_CONTRACT,
        "history_file": "eth_whale_alert_history.json",
        "block_file": "eth_whale_last_block.json",
        # Threshold configuration (back-compat: "min_value" == token units)
        "min_value_token": 500,
        # Alternatively, you can specify a USD-based threshold and set threshold_mode to "usd"
        # "min_value_usd": 500000,  # example
        "threshold_mode": "token",  # or "usd"
        "coingecko_id": "ethereum",
        "max_results": 2000
    },
    {
        "name": "LINK",
        "contract": LINK_CONTRACT,
        "history_file": "link_whale_alert_history.json",
        "block_file": "link_whale_last_block.json",
        "min_value_token": 20000,
        # "min_value_usd": 500000,  # example
        "threshold_mode": "token",
        "coingecko_id": "chainlink",
        "max_results": 2000
    },
    # Add more tokens here
]

import os
from wallet_loader import load_wallet_groups

# Fallback nhỏ – phần mở rộng nằm trong erc20_cex_wallets.json
_STATIC_EX_WALLETS = {
    "Binance": [
        '0x28c6c06298d514db089934071355e5743bf21d60',
        '0xf977814e90da44bfa03b6295a0616a897441acec',
    ],
    "Kraken": ['0x53d284357ec70ce289d6d64134dfac8e511c8a3d'],
    "OKX": ['0x66f820a414680b5bcda5eeca5dea238543f42054'],
    "Huobi": ['0x21a31ee1afc51d94c2efccaa2092ad1028285549'],
    "Coinbase": ['0xFCD159D0FeF5B1003E10D91A5b79d52BbB8cD05d'],
}
_JSON_PATH_EX = os.path.join(os.path.dirname(__file__), 'erc20_cex_wallets.json')
_GROUPS = load_wallet_groups(_JSON_PATH_EX, _STATIC_EX_WALLETS)
EXCHANGE_WALLETS = {addr.lower(): label for label, addrs in _GROUPS.items() for addr in addrs}

# --- Generic ERC20 token transfer fetch logic ---
def fetch_large_erc20_transfers(api_key, contract_address, min_value=20000, max_results=20, start_block=0, end_block=99999999, chain_id=1):
    """
    Fetch large ERC20 transfers using Etherscan API V2, supporting multiple chains (e.g., Ethereum, BSC).
    """
    base_url = "https://api.etherscan.io/v2/api" if chain_id == 1 else "https://api.bscscan.com/api"
    url = f"{base_url}?chainid={chain_id}&module=account&action=tokentx&contractaddress={contract_address}&startblock={start_block}&endblock={end_block}&sort=desc&apikey={api_key}"
    r = requests.get(url, timeout=10)
    data = r.json()
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return pd.DataFrame()
    df = pd.DataFrame(result)
    # Convert raw on-chain value using each token's decimals (default 18 if missing)
    # Etherscan returns tokenDecimal as a string per row.
    try:
        decimals = pd.to_numeric(df.get("tokenDecimal"), errors="coerce").fillna(18).astype(int)
    except Exception:
        decimals = pd.Series([18] * len(df))
    # Ensure numeric value; Etherscan may return 'value' as string
    df_value_num = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    # Vectorized conversion: value_token = value_raw / 10 ** decimals
    import numpy as _np
    df["value"] = df_value_num / _np.power(10.0, decimals.to_numpy())
    # Apply min filter in token units (caller supplies appropriate threshold per token)
    df = df[df["value"] >= float(min_value)]
    # tz-aware UTC time for consistency with charts
    df["time"] = pd.to_datetime(df["timeStamp"].astype(int), unit="s", utc=True)
    df = df.sort_values("time", ascending=False).head(max_results)
    # Add BUY/SELL/N/A detection and mapping
    df["from_label"] = df["from"].str.lower().map(EXCHANGE_WALLETS).fillna(df["from"].str[:10] + "...")
    df["to_label"] = df["to"].str.lower().map(EXCHANGE_WALLETS).fillna(df["to"].str[:10] + "...")
    def detect_type(row):
        from_addr = str(row["from"]).lower()
        to_addr = str(row["to"]).lower()
        if to_addr in EXCHANGE_WALLETS:
            return "SELL"
        elif from_addr in EXCHANGE_WALLETS:
            return "BUY"
        else:
            return "N/A"
    df["type"] = df.apply(detect_type, axis=1)
    return df

# --- Threshold helpers (support token-unit or USD-based thresholds) ---
def _get_coingecko_price_usd(coin_id: str) -> float:
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r = requests.get(url, timeout=8)
        data = r.json()
        return float(data.get(coin_id, {}).get("usd", 0.0))
    except Exception:
        return 0.0

def resolve_token_min_threshold_units(token_cfg: dict) -> float:
    # Backward compatibility: allow "min_value" to act as token-unit threshold
    if "min_value_token" in token_cfg:
        return float(token_cfg.get("min_value_token", 0.0))
    if token_cfg.get("threshold_mode", "token").lower() == "usd":
        usd = float(token_cfg.get("min_value_usd", 0.0))
        if usd <= 0:
            return float(token_cfg.get("min_value", 0.0) or 0.0)
        price = _get_coingecko_price_usd(token_cfg.get("coingecko_id", "")) if token_cfg.get("coingecko_id") else 0.0
        if price > 0:
            return usd / price
        return 0.0
    # default token mode
    return float(token_cfg.get("min_value", 0.0) or 0.0)

# --- Save whale history and block ---
def save_token_whale_history(token, history):
    try:
        # Log nội dung biến history trước khi ghi file
        # with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
        #     logf.write(f"[{datetime.utcnow()}] [SAVE_HISTORY] {token['name']} | Số lượng tx: {len(history)} | Types: {[tx.get('type') for tx in history]}\n")
        #     for tx in history:
        #         logf.write(f"[{datetime.utcnow()}] [SAVE_HISTORY] TX: {tx.get('hash','')} | Type: {tx.get('type','N/A')} | Value: {tx.get('value',0)}\n")
        # Load old history if exists
        if os.path.exists(token["history_file"]):
            with open(token["history_file"], "r") as f:
                old_history = json.load(f)
        else:
            old_history = []
        # Combine old and new history, remove duplicates by hash
        combined_history = {tx["hash"]: tx for tx in old_history}
        for tx in history:
            combined_history[tx["hash"]] = tx
        # Save combined history
        with open(token["history_file"], "w") as f:
            json.dump(list(combined_history.values()), f, ensure_ascii=False, indent=2)
    except Exception as e:
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[{datetime.utcnow()}] Error saving whale history for {token['name']}: {str(e)}\n")

def save_token_last_block(token, block_num):
    with open(token["block_file"], "w") as f:
        json.dump({"last_block": block_num}, f)

# --- Background scanner for multiple ERC20 whale alerts ---
def background_erc20_whale_alert_scanner(api_key='2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG', interval_sec=300):
    with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
        logf.write(f"[{datetime.utcnow()}] [SCANNER] Thread started.\n")
    try:
        with open("eth_whale_scanner.log", "a", encoding="utf-8") as logf:
            logf.write(f"[{datetime.utcnow()}] [SCANNER] Start scan loop.\n")
        for token in ERC20_TOKENS:
            try:
                min_th = resolve_token_min_threshold_units(token)
                last_block = load_last_block(token)  # Call load_last_block
                latest_block_url = f"https://api.etherscan.io/v2/api?chainid=1&module=proxy&action=eth_blockNumber&apikey={api_key}"
                r = requests.get(latest_block_url, timeout=10)
                latest_block_data = r.json()
                latest_block = int(latest_block_data.get("result", "0x0"), 16)

                if latest_block > last_block:
                    start_block = last_block + 1
                    end_block = latest_block
                    df = fetch_large_erc20_transfers(
                        api_key,
                        contract_address=token["contract"],
                        min_value=min_th,
                        max_results=token["max_results"],
                        start_block=start_block,
                        end_block=end_block
                    )
                    history = load_whale_history(token)  # Call load_whale_history
                    if not df.empty:
                        for _, row in df.iterrows():
                            history.append({
                                "hash": row.get("hash", ""),
                                "from": row.get("from", ""),
                                "to": row.get("to", ""),
                                "from_label": row.get("from_label", ""),
                                "to_label": row.get("to_label", ""),
                                "type": row.get("type", "N/A"),
                                "value": row.get("value", 0),
                                "time": str(row.get("time", "")),
                                "blockNumber": row.get("blockNumber", None)
                            })
                    save_token_whale_history(token, history)
                    _log(token, f"Token: {token['name']} | Whale txs found: {len(df)} | Blocks scanned: {start_block} to {end_block}")  # Call _log
                    save_token_last_block(token, end_block)
                else:
                    _log(token, f"No new block for token {token['name']}. Latest block: {latest_block}, Last scanned: {last_block}")
            except Exception as e:
                _log(token, f"Error scanning token {token['name']}: {str(e)}")
    except Exception as e:
        _log({"name": "GENERAL"}, f"FATAL error in background_erc20_whale_alert_scanner: {str(e)}")

# Start background scanner thread on import (only once)
if '_erc20_whale_scanner_started' not in globals():
    t = threading.Thread(target=background_erc20_whale_alert_scanner, kwargs={"api_key": "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG", "interval_sec": 300}, daemon=True)
    t.start()
    _erc20_whale_scanner_started = True

# --- Show whale alert box for a token ---

def show_erc20_whale_alert_realtime(token, api_key='2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG'):
    st.markdown(f"""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - {token['name']} Large Transfers
</div>
""", unsafe_allow_html=True)
    box_content = ""
    try:
        df = fetch_large_erc20_transfers(
            api_key,
            contract_address=token["contract"],
            min_value=resolve_token_min_threshold_units(token),
            max_results=token["max_results"]
        )
        if df.empty:
            # Nếu API trả về rỗng, đọc lịch sử từ file
            history = []
            if os.path.exists(token["history_file"]):
                try:
                    with open(token["history_file"], "r") as f:
                        history = json.load(f)
                except Exception as e:
                    history = []
                    # Ghi log lỗi khi đọc file history
                    log_path = token["history_file"] + ".error.log"
                    with open(log_path, "a", encoding="utf-8") as logf:
                        logf.write(f"[{datetime.utcnow()}] Lỗi đọc file history: {e}\n")
            if not history:
                box_content += "<div style='color:#888;'>Không có transaction lớn nào được phát hiện gần đây.</div>"
            else:
                for tx in history[::-1]:
                    type_badge = ""
                    if tx.get("type") == "SELL":
                        type_badge = "<span style='color:#fff;background:#e53935;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>SELL</span>"
                    elif tx.get("type") == "BUY":
                        type_badge = "<span style='color:#fff;background:#1e88e5;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>BUY</span>"
                    else:
                        type_badge = "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>N/A</span>"
                    box_content += f"<div style='margin-bottom:8px;'>{type_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx.get('value', 0):.2f} {token['name']}</span> | Hash: <code>{tx.get('hash', '')[:12]}...</code> | Từ: <code>{tx.get('from_label', tx.get('from', '')[:10] + '...')}</code> → Đến: <code>{tx.get('to_label', tx.get('to', '')[:10] + '...')}</code> | <span style='color:#888;'>{tx.get('time', '')}</span></div>"
        else:
            for _, row in df.iterrows():
                type_badge = ""
                if row.get("type") == "SELL":
                    type_badge = "<span style='color:#fff;background:#e53935;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>SELL</span>"
                elif row.get("type") == "BUY":
                    type_badge = "<span style='color:#fff;background:#1e88e5;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>BUY</span>"
                else:
                    type_badge = "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>N/A</span>"
                box_content += f"<div style='margin-bottom:8px;'>{type_badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {row['value']:.2f} {token['name']}</span> | Hash: <code>{row['hash'][:12]}...</code> | Từ: <code>{row['from_label']}</code> → Đến: <code>{row['to_label']}</code> | <span style='color:#888;'>{row['time']}</span></div>"
    except Exception as e:
        box_content += f"<div style='color:#c00;'>Không thể lấy dữ liệu whale alert từ Etherscan: {str(e)}</div>"
    st.markdown(f"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>{box_content}</div>", unsafe_allow_html=True)

def load_whale_history(token):
    # Prefer cloud DB if available
    local_history = []
    if os.path.exists(token["history_file"]):
        with open(token["history_file"], "r") as f:
            local_history = json.load(f)

    if db.available():
        # Lấy dữ liệu từ database
        db_history = db.find_all(f"{token['name'].lower()}_whale_history", sort_field="time", ascending=True)
        db_hashes = {d.get("hash") for d in db_history if isinstance(d, dict) and "hash" in d}

        # Gộp dữ liệu từ file local vào database
        new_entries = [entry for entry in local_history if entry.get("hash") not in db_hashes]
        if new_entries:
            db.upsert_many(f"{token['name'].lower()}_whale_history", new_entries, unique_keys=["hash"])
            print(f"Gộp {len(new_entries)} giao dịch từ file local vào database.")

        # Trả về dữ liệu đã gộp
        return db.find_all(f"{token['name'].lower()}_whale_history", sort_field="time", ascending=True)

    # Nếu database không khả dụng, trả về dữ liệu từ file local
    return local_history

def load_last_block(token):
    # Giá trị từ file local
    local_last_block = None
    if os.path.exists(token["block_file"]):
        with open(token["block_file"], "r") as f:
            data = json.load(f)
            local_last_block = data.get("last_block", None)

    if db.available():
        # Giá trị từ database
        kv = db.get_kv(f"{token['name'].lower()}_meta", "last_block")
        db_last_block = kv.get("last_block") if kv and isinstance(kv, dict) else None

        # Gộp giá trị từ file local vào database nếu cần
        if local_last_block and (db_last_block is None or local_last_block > db_last_block):
            db.set_kv(f"{token['name'].lower()}_meta", "last_block", {"last_block": local_last_block})
            print(f"Gộp giá trị last_block {local_last_block} từ file local vào database.")

        # Trả về giá trị từ database
        return db.get_kv(f"{token['name'].lower()}_meta", "last_block").get("last_block")

    # Nếu database không khả dụng, trả về giá trị từ file local
    return local_last_block

def _log(token, msg: str):
    try:
        line = f"[{datetime.utcnow()}] {msg}"
        log_file = f"{token['name'].lower()}_whale_scanner.log"
        with open(log_file, "a", encoding="utf-8") as logf:
            logf.write(line + "\n")

        if db.available():
            # Gộp log từ file local vào database
            with open(log_file, "r", encoding="utf-8") as logf:
                local_logs = [{"ts": datetime.utcnow().isoformat(), "line": line.strip()} for line in logf]
            db.insert_many(f"{token['name'].lower()}_logs", local_logs)
            print(f"Gộp {len(local_logs)} log từ file local vào database.")
    except Exception:
        pass
