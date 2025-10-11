# AVAX Whale Alert Realtime (modeled after BNB/EVM scanners)
from __future__ import annotations

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
from .avax_cex_dex_wallets import classify_transaction
from .avax_utils import (
	AVAX_CHAIN_ID,
	USER_SEEN_BLOCK_FILE,
	HISTORY_FILE,
	BLOCK_FILE,
	LOG_FILE,
	CSV_FILE,
)

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# API KEY: Etherscan multi-chain (works with chainid param); replace with env if provided
API_KEY = os.getenv("ETHERSCAN_API_KEY", "2I9RJZUQK7CGS6C3G5SPXIUCTCK3VXBRAG")


def _log(msg: str):
    try:
        line = f"[{datetime.utcnow()}] {msg}"
        #print(f"[AVAX_LOG] {line}")  # Console log for debugging
        with open(LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(line + "\n")
        if db.available():
            # store a light log entry
            db.insert_one("avax_logs", {"ts": datetime.utcnow().isoformat(), "line": line})
    except Exception as e:
        print(f"[AVAX_LOG_ERROR] {e}")
		
# --- Seen block helpers ---

def mark_avax_whale_alert_seen():
	last_block = load_last_block()
	with open(USER_SEEN_BLOCK_FILE, "w") as f:
		json.dump({"seen_block": last_block}, f)


def load_user_seen_block() -> int:
	if os.path.exists(USER_SEEN_BLOCK_FILE):
		with open(USER_SEEN_BLOCK_FILE, "r") as f:
			data = json.load(f)
			return int(data.get("seen_block", 0) or 0)
	return 0


def check_avax_whale_alert_has_new() -> bool:
	last_block = load_last_block()
	seen_block = load_user_seen_block()
	return last_block is not None and int(last_block) > int(seen_block)


# --- AVAX (C-Chain) block/tx fetch via Etherscan v2 multi-chain ---

def fetch_latest_block_number() -> int:
	url = f"https://api.etherscan.io/v2/api?chainid={AVAX_CHAIN_ID}&module=proxy&action=eth_blockNumber&apikey={API_KEY}"
	r = requests.get(url, timeout=10)
	data = r.json()
	block_hex = data.get("result")
	if not block_hex:
		raise ValueError("Failed to fetch latest block number")
	return int(block_hex, 16)


def fetch_block_transactions(block_number: int):
	url = (
		f"https://api.etherscan.io/v2/api?chainid={AVAX_CHAIN_ID}&module=proxy&action=eth_getBlockByNumber"
		f"&tag={hex(block_number)}&boolean=true&apikey={API_KEY}"
	)
	r = requests.get(url, timeout=12)
	try:
		data = r.json()
	except json.JSONDecodeError:
		logging.error(f"JSON decode error for block {block_number}: {r.text[:200]}")
		raise
	if not isinstance(data, dict) or "result" not in data or not isinstance(data["result"], dict):
		raise ValueError(f"Unexpected response for block {block_number}: {data}")
	txs = data["result"].get("transactions", [])
	formatted = []
	for tx in txs:
		try:
			formatted.append({
				"hash": tx.get("hash"),
				"from": tx.get("from"),
				"to": tx.get("to"),
				"value": int(tx.get("value", "0"), 16) / 1e18,  # AVAX has 18 decimals
				"timeStamp": tx.get("timeStamp"),
			})
		except Exception as e:
			logging.error(f"Format tx error (block {block_number}): {e}")
	return formatted


# --- Persistence helpers ---

def save_last_block(block_num: int):
	if db.available():
		try:
			db.set_kv("avax_meta", "last_block", {"last_block": int(block_num)})
		except Exception as e:
			logging.error(f"DB save_last_block error: {e}")
	with open(BLOCK_FILE, "w") as f:
		json.dump({"last_block": int(block_num)}, f)


def load_last_block():
	local_last = None
	if os.path.exists(BLOCK_FILE):
		try:
			with open(BLOCK_FILE, "r") as f:
				local_last = (json.load(f) or {}).get("last_block")
		except Exception:
			local_last = None
	if db.available():
		try:
			kv = db.get_kv("avax_meta", "last_block") or {}
			db_last = kv.get("last_block")
			if local_last and (db_last is None or int(local_last) > int(db_last)):
				db.set_kv("avax_meta", "last_block", {"last_block": int(local_last)})
			return (db.get_kv("avax_meta", "last_block") or {}).get("last_block")
		except Exception:
			pass
	return local_last


def save_whale_history(history: list[dict]):
	# Cloud first
	if db.available() and isinstance(history, list):
		try:
			db.upsert_many("avax_whale_history", history, unique_keys=["hash"])
		except Exception:
			pass
	# Local JSON
	with open(HISTORY_FILE, "w", encoding="utf-8") as f:
		json.dump(history, f)
	# Optional CSV for downstream tools
	try:
		df = pd.DataFrame(history)
		cols = ["block", "hash", "from", "to", "value", "time", "type"]
		for c in cols:
			if c not in df.columns:
				df[c] = None
		df.to_csv(CSV_FILE, index=False)
	except Exception:
		pass


def load_whale_history() -> list[dict]:
	local = []
	if os.path.exists(HISTORY_FILE):
		try:
			with open(HISTORY_FILE, "r", encoding="utf-8") as f:
				local = json.load(f)
		except Exception:
			local = []
	if db.available():
		try:
			db_hist = db.find_all("avax_whale_history", sort_field="time", ascending=True)
			db_hashes = {d.get("hash") for d in db_hist if isinstance(d, dict) and d.get("hash")}
			new_entries = [e for e in local if e.get("hash") not in db_hashes]
			if new_entries:
				db.upsert_many("avax_whale_history", new_entries, unique_keys=["hash"])
			return db.find_all("avax_whale_history", sort_field="time", ascending=True)
		except Exception:
			pass
	return local


# --- Background scanner ---

def background_whale_alert_scanner(min_value_avax: float = 30000, num_blocks: int = 300, interval_sec: int = 300):
	while True:
		try:
			_log("Starting AVAX whale alert scan loop.")
			latest = fetch_latest_block_number()
			_log(f"Latest block number fetched: {latest}")
			last_scanned = load_last_block()
			_log(f"Last scanned block: {last_scanned}")
			start_block = latest
			end_block = max(0, latest - num_blocks + 1)
			if last_scanned and last_scanned >= end_block:
				end_block = int(last_scanned) + 1
			_log(f"Scanning blocks from {start_block} to {end_block}")

			history = load_whale_history()
			#_log(f"Loaded whale history with {len(history)} transactions")
			seen = {tx.get("hash") for tx in history}

			for blk in range(start_block, end_block - 1, -1):
				try:
					#_log(f"Scanning block {blk}")
					txs = fetch_block_transactions(blk)
					#_log(f"Fetched {len(txs)} transactions from block {blk}")
					for tx in txs:
						value_avax = float(tx.get("value", 0) or 0)
						if value_avax < min_value_avax:
							#_log(f"Transaction {tx.get('hash')} skipped due to low value: {value_avax} AVAX")
							continue
						h = tx.get("hash") or ""
						if h in seen:
							#_log(f"Transaction {h} already seen, skipping")
							continue
						from_addr = (tx.get("from") or "").lower()
						to_addr = (tx.get("to") or "").lower()
						etype = classify_transaction(from_addr, to_addr)
						#_log(f"Classified transaction {h} as {etype}")
						obj = {
							"block": blk,
							"hash": h,
							"from": from_addr,
							"to": to_addr,
							"value": value_avax,
							"time": datetime.utcfromtimestamp(int(tx.get("timeStamp", "0") or 0) or int(time.time())).strftime("%Y-%m-%d %H:%M:%S"),
							"type": etype,
						}
						history.append(obj)
						seen.add(h)
				except Exception as e:
					_log(f"Error processing block {blk}: {e}")

			save_last_block(start_block)
			#_log(f"Saved last scanned block: {start_block}")
			# Keep recent 1000
			history = [tx for tx in history if float(tx.get("value", 0) or 0) >= min_value_avax][-1000:]
			save_whale_history(history)
			#_log("Whale history updated.")
		except Exception as e:
			_log(f"Scanner error: {e}")
		time.sleep(interval_sec)


# --- UI ---

def show_avax_whale_alert_realtime(min_value_avax: float = 30000, num_blocks: int = 100):
	st.markdown(
		"""
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
	🐳 Whale Alert - AVAX Large Transactions
</div>
		""",
		unsafe_allow_html=True,
	)
	whale_txs = load_whale_history()
	last_block = load_last_block()
	seen_block = load_user_seen_block()
	box = []
	if not whale_txs:
		box.append("<div style='color:#888;'>Không có transaction lớn nào gần đây.</div>")
	else:
		for tx in whale_txs[::-1]:
			is_new = last_block is not None and int(tx.get("block", 0) or 0) > int(seen_block)
			badge = (
				"<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>"
				if is_new
				else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
			)
			box.append(
				f"<div style='margin-bottom:8px;'>{badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx.get('value',0):.2f} AVAX</span> | Hash: <code>{(tx.get('hash','') or '')[:12]}...</code> | Từ: <code>{tx.get('from','')}</code> → Đến: <code>{tx.get('to','')}</code> | <span style='color:#888;'>{tx.get('time','')}</span></div>"
			)
	st.markdown(
		"<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>"
		+ "".join(box)
		+ "</div>",
		unsafe_allow_html=True,
	)


# Launch background thread once
_avax_whale_bg_started = False

def ensure_background_scanner_started():
	global _avax_whale_bg_started
	if not _avax_whale_bg_started:
		try:
			_log("Starting AVAX whale background scanner thread...")
			t = threading.Thread(target=background_whale_alert_scanner, args=(3000, 100, 300), daemon=True)
			t.start()
			_avax_whale_bg_started = True
			_log("AVAX whale background scanner thread started successfully")
			print("[DEBUG] AVAX whale background scanner thread started")
		except Exception as e:
			_log(f"Failed to start AVAX whale background scanner: {e}")
			print(f"[ERROR] Failed to start AVAX whale background scanner: {e}")

# Auto-start when module is imported
print("[DEBUG] AVAX metrics module loading...")
_log("AVAX whale alert module imported")
ensure_background_scanner_started()
