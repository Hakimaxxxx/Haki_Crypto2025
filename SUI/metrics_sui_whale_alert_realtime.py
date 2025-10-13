"""
SUI Whale Alert Realtime

This module scans Sui blocks for large transfers (whales) using an indexer API
when available. It contains robust HTTP handling, base autodetection and
lightweight persistence similar to other coin modules in this repo.
"""
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
from .sui_cex_dex_wallets import classify_transaction
from .sui_utils import (
    SUI_CHAIN_ID,
    USER_SEEN_BLOCK_FILE,
    HISTORY_FILE,
    BLOCK_FILE,
    LOG_FILE,
    CSV_FILE,
)

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# API KEY: Default to the BlockVision trial/provided key if env not set
API_KEY = os.getenv("SUI_API_KEY", os.getenv("BLOCKVISION_API_KEY", "33vnlk9jCMgCqthYy7IrhDWvJDq"))

# Base URL (allow override via env). We'll auto-detect a working base from candidates if not set.
_env_base = os.getenv("SUI_API_BASE")
BASE_API_URL = _env_base or "https://suivision.xyz/api"

# Candidate bases to probe
_CANDIDATE_BASES = [
    "https://suivision.xyz/api",
    "https://suivision.xyz",
    "https://suivision.xyz/transactions",
    # Added suiscan mainnet API candidate (may serve REST/indexer-like endpoints)
    "https://rpc-mainnet.suiscan.xyz",
    # BlockBerry indexer (public API)
    "https://api.blockberry.one/sui/v1",
    "https://api.blockvision.org",
    "https://blockvision.org",
]

# RPC fallback: allow using a Sui JSON-RPC endpoint if indexer is unavailable.
# Prefer environment variable SUI_RPC_URL, otherwise probe a small candidate list.
SUI_RPC_URL = os.getenv("SUI_RPC_URL")
_RPC_CANDIDATES = [
    SUI_RPC_URL,
    # Common Sui fullnode endpoint (no guarantee; can be overridden via env)
    "https://fullnode.mainnet.sui.io:443",
    # Suiscan public RPC/metrics endpoints (added per user suggestion)
    "https://rpc-mainnet.suiscan.xyz:443",
    "https://rpc-mainnet.suiscan.xyz",
]

# BlockBerry API key (hardcoded as requested). Note: this overrides any env var.
BLOCKBERRY_API_KEY = "Y1CcambMPLreF9NiuJ8JeZlfmHqpZY"
BLOCKBERRY_BASE = "https://api.blockberry.one/sui/v1"

# How many checkpoints to scan per background run (to keep each run bounded to ~5 minutes)
MAX_CHECKPOINTS_PER_SCAN = int(os.getenv("SUI_BLOCKBERRY_MAX_CHECKPOINTS_PER_SCAN", "50"))


def _blockberry_request_with_backoff(method: str, url: str, headers: dict | None = None, json_body: dict | None = None, timeout: int = 12, max_retries: int = 4, throttle_sec: float = 0.25):
    """Make a BlockBerry request with simple exponential backoff for 429 and small throttle between calls.

    Returns Response on success or raises the last exception.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            time.sleep(throttle_sec)
            if method.upper() == "GET":
                r = requests.get(url, headers=headers, timeout=timeout)
            else:
                r = requests.post(url, headers=headers, json=json_body, timeout=timeout)
        except Exception as e:
            last_exc = e
            #_log(f"BlockBerry request error (attempt {attempt+1}/{max_retries}) for {url}: {e}")
            time.sleep(1 * (2 ** attempt))
            continue

        if r.status_code == 200:
            return r
        # If rate-limited, backoff and retry
        if r.status_code == 429:
            #_log(f"BlockBerry rate-limited (429) for {url} (attempt {attempt+1}/{max_retries}); backing off")
            last_exc = RuntimeError("HTTP 429")
            time.sleep(1 * (2 ** attempt))
            continue
        # On other non-200, return the response so caller can handle logging/format
        return r
    # exhausted retries
    raise last_exc or RuntimeError("BlockBerry request failed after retries")

# Note: Suiscan also exposes a metrics HTTP endpoint and a websocket endpoint
# - Metrics: https://rpc-mainnet.suiscan.xyz/metrics
# - WebSocket: wss://rpc-mainnet.suiscan.xyz/websocket
# The current scanner uses HTTP JSON-RPC calls. WebSocket (WSS) support for
# real-time event streaming is not implemented yet; we can add a WSS listener
# later if you want streaming rather than polling.


def _log(msg: str):
    try:
        line = f"[{datetime.utcnow()}] {msg}"
        with open(LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(line + "\n")
        if db.available():
            db.insert_one("sui_logs", {"ts": datetime.utcnow().isoformat(), "line": line})
    except Exception as e:
        print(f"[SUI_LOG_ERROR] {e}")


def _http_get_with_retries(url: str, timeout: int = 12, attempts: int = 3, backoff_sec: float = 1.0):
    """Perform GET with small retry/backoff and rich logging on failures."""
    last_exc = None
    for i in range(attempts):
        try:
            r = requests.get(url, timeout=timeout)
        except Exception as e:
            _log(f"HTTP request error (attempt {i+1}/{attempts}) for {url}: {e}")
            last_exc = e
            time.sleep(backoff_sec * (2 ** i))
            continue
        # log non-200
        if r.status_code != 200:
            snippet = (r.text or "")[:400]
            #_log(f"Non-200 HTTP response {r.status_code} for {url} (attempt {i+1}/{attempts}). Snippet: {snippet}")
            last_exc = RuntimeError(f"HTTP {r.status_code}")
            time.sleep(backoff_sec * (2 ** i))
            continue
        return r
    # all attempts failed
    raise last_exc or RuntimeError("HTTP request failed")


def _detect_working_api_base():
    """Probe candidate bases and choose the first that returns JSON for a common endpoint.
    This avoids treating HTML landing pages as API responses (which caused the JSON decode error).
    """
    global BASE_API_URL
    # If user set BASE_API_URL explicitly via env, respect it
    if _env_base:
        _log(f"Using user-provided SUI_API_BASE: {_env_base}")
        return

    # If BlockBerry API key is present, prefer it and skip probing other indexers
    if BLOCKBERRY_API_KEY:
        BASE_API_URL = BLOCKBERRY_BASE
        _log(f"Using BlockBerry as API base due to BLOCKBERRY_API_KEY: {BLOCKBERRY_BASE}")
        return

    for base in _CANDIDATE_BASES:
        try_urls = [f"{base}/block/latest?apikey={API_KEY}", f"{base}/transactions?apikey={API_KEY}"]
        for u in try_urls:
            try:
                r = requests.get(u, timeout=8)
            except Exception as e:
                _log(f"Probe request error for {u}: {e}")
                continue
            if r.status_code != 200:
                _log(f"Probe non-200 for {u}: {r.status_code}")
                continue
            # Accept if JSON-decodable
            try:
                _ = r.json()
                BASE_API_URL = base
                _log(f"Detected working SUI API base: {base} (via {u})")
                return
            except Exception:
                _log(f"Probe returned non-JSON for {u}; snippet: { (r.text or '')[:200] }")
                continue
    _log("No working SUI API base detected from candidates; will keep default and rely on retries")


# Run detection at import time (lightweight)
try:
    _detect_working_api_base()
except Exception as e:
    _log(f"API base detection error: {e}")


# --- Seen block helpers ---


def mark_sui_whale_alert_seen():
    last_block = load_last_block()
    with open(USER_SEEN_BLOCK_FILE, "w") as f:
        json.dump({"seen_block": last_block}, f)


def load_user_seen_block() -> int:
    if os.path.exists(USER_SEEN_BLOCK_FILE):
        with open(USER_SEEN_BLOCK_FILE, "r") as f:
            data = json.load(f)
            return int(data.get("seen_block", 0) or 0)
    return 0


def check_sui_whale_alert_has_new() -> bool:
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    return last_block is not None and int(last_block) > int(seen_block)


# --- SUI block/tx fetch ---


def fetch_latest_block_number() -> int:
    # If BlockBerry key present, prefer BlockBerry checkpoints endpoint for latest block
    if BLOCKBERRY_API_KEY:
        try:
            c = fetch_recent_checkpoints(limit=1)
            if c:
                return int(c[0])
        except Exception as e:
            _log(f"BlockBerry latest-block attempt failed: {e}")
    # First try indexer endpoint
    try:
        url = f"{BASE_API_URL}/block/latest?apikey={API_KEY}"
        r = _http_get_with_retries(url, timeout=10, attempts=3)
        try:
            data = r.json()
        except Exception as e:
            snippet = (r.text or "")[:800]
            _log(f"JSON decode error when fetching latest block: {e}. HTTP {r.status_code}. Snippet: {snippet}")
            raise
        block_number = data.get("block_number") or data.get("blockNumber") or data.get("block") or data.get("height")
        if block_number is not None:
            return int(block_number)
    except Exception as e:
        _log(f"Indexer latest-block attempt failed: {e}")

    # Fallback: try RPC endpoints
    try:
        rpc_url = _detect_working_rpc()
        if not rpc_url:
            raise RuntimeError("No working SUI RPC available")
        # Try JSON-RPC method to get total transaction blocks (works on many Sui nodes)
        payload = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTotalTransactionBlocks", "params": []}
        r = _rpc_post(rpc_url, payload, timeout=8)
        j = r.json()
        result = j.get("result")
        try:
            # Accept int or numeric strings (some fullnode implementations return strings)
            if isinstance(result, int):
                return int(result)
            if isinstance(result, str):
                # strip and try to parse numeric string
                s = result.strip()
                if s.isdigit():
                    return int(s)
                # allow decimal-like strings
                try:
                    return int(float(s))
                except Exception:
                    pass
            # try alternative field
            if isinstance(result, dict) and result.get("total"):
                return int(result.get("total"))
        except Exception:
            pass
        raise RuntimeError(f"Unexpected RPC latest-block payload: {j}")
    except Exception as e:
        _log(f"RPC latest-block attempt failed: {e}")
        raise


def fetch_block_transactions(block_number: int):
    # If BlockBerry API key present, bypass other indexers/RPC and use BlockBerry-only
    if BLOCKBERRY_API_KEY:
        # try filtered endpoints first
        found = fetch_blockberry_transactions_by_checkpoint(block_number, max_pages=50, page_size=50)
        if found:
            return found
        # otherwise fall back to fetching recent and filtering locally
        return [
            {"hash": t.get("hash"), "from": t.get("from"), "to": t.get("to"), "value": t.get("value"), "timeStamp": t.get("timeStamp")}
            for t in fetch_recent_blockberry_transactions(limit=200, page_size=50)
            if int(t.get("checkpoint") or 0) == int(block_number)
        ]
    # Try indexer first
    try:
        url = f"{BASE_API_URL}/block/{block_number}/transactions?apikey={API_KEY}"
        r = _http_get_with_retries(url, timeout=12, attempts=3)
        try:
            data = r.json()
        except Exception as e:
            snippet = (r.text or "")[:800]
            _log(f"JSON decode error for block {block_number}: {e}. HTTP {r.status_code}. Snippet: {snippet}")
            raise
        # Support both list-of-txs and object-wrapped responses
        if isinstance(data, dict):
            for k in ("transactions", "txs", "data", "result"):
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break
        if isinstance(data, list):
            return _format_indexer_txs(data)
    except Exception as e:
        _log(f"Indexer block-txs attempt failed for block {block_number}: {e}")

    # Try BlockBerry specific endpoint if API key present (fall back from generic indexer)
    try:
        if BLOCKBERRY_API_KEY:
            # try targeted filtered endpoints first
            found = fetch_blockberry_transactions_by_checkpoint(block_number, max_pages=8, page_size=50)
            if found:
                return found
            # fallback to generic paging if filtered endpoints didn't return
            headers = {"accept": "*/*", "x-api-key": BLOCKBERRY_API_KEY}
            formatted = []
            # page through a few pages searching for transactions with matching checkpoint
            for page in range(0, 50):
                b_url = f"https://api.blockberry.one/sui/v1/transactions?page={page}&size=50&orderBy=DESC&sortBy=AGE"
                try:
                    r = _blockberry_request_with_backoff("POST", b_url, headers=headers, json_body=None, timeout=12)
                except Exception as e:
                    _log(f"BlockBerry page request failed for {b_url}: {e}")
                    break
                if r.status_code != 200:
                    _log(f"BlockBerry page {page} non-200: {r.status_code}")
                    break
                j = r.json()
                content = j.get("content") or []
                for tx in content:
                    try:
                        # Build per-address SUI delta if available
                        owner_deltas = {}
                        total_sui = 0.0
                        for bc in tx.get("balanceChanges") or []:
                            ct = bc.get("coinType") or ""
                            amt = bc.get("amount")
                            owner = bc.get("owner") or bc.get("address") or bc.get("ownerAddress") or bc.get("addressOwner")
                            try:
                                n = int(amt)
                            except Exception:
                                try:
                                    n = int(float(amt))
                                except Exception:
                                    n = 0
                            if ct == "0x2::sui::SUI":
                                sui_val = n / 1_000_000.0
                                total_sui += sui_val
                                if owner:
                                    owner_deltas.setdefault(owner, 0.0)
                                    owner_deltas[owner] += sui_val
                        sender = tx.get("senderAddress") or tx.get("sender")
                        direction = None
                        value_abs = None
                        if sender and owner_deltas:
                            sender_delta = owner_deltas.get(sender)
                            if sender_delta is not None:
                                value_abs = abs(sender_delta)
                                direction = "out" if sender_delta < 0 else ("in" if sender_delta > 0 else "neutral")
                        if value_abs is None:
                            value_abs = abs(total_sui)
                            direction = "out" if total_sui < 0 else ("in" if total_sui > 0 else "neutral")
                        out.append({
                            "hash": tx.get("txHash"),
                            "from": tx.get("senderAddress") or tx.get("sender"),
                            "to": None,
                            "value": float(value_abs),
                            "timeStamp": tx.get("timestamp"),
                            "checkpoint": tx.get("checkpoint"),
                            "direction": direction,
                        })
                    except Exception:
                        continue
                # if we found matches, stop paging
                if formatted:
                    break
    except Exception as e:
        _log(f"BlockBerry indexer attempt failed for block {block_number}: {e}")

    # Fallback: use RPC (get tx digests then fetch each transaction)
    try:
        rpc_url = _detect_working_rpc()
        if not rpc_url:
            raise RuntimeError("No working SUI RPC available")
        # Get transaction block digests for the given sequence (many nodes expose sui_getTransactionBlocks)
        payload = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTransactionBlocks", "params": [block_number, block_number]}
        r = _rpc_post(rpc_url, payload, timeout=12)
        j = r.json()
        digests = j.get("result") or []
        if not isinstance(digests, list):
            # sometimes node returns a single digest as string
            digests = [digests]
        _log(f"RPC digests for block {block_number}: {len(digests)}")
        formatted = []
        for d in digests:
            try:
                # fetch full tx by digest
                p2 = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTransactionBlock", "params": [d]}
                r2 = _rpc_post(rpc_url, p2, timeout=10)
                j2 = r2.json()
                txobj = j2.get("result") or {}
                parsed = _parse_sui_rpc_tx(txobj)
                if parsed:
                    parsed_list = parsed if isinstance(parsed, list) else [parsed]
                    formatted.extend(parsed_list)
                    _log(f"Parsed {len(parsed_list)} transfer events from digest {d} (block {block_number})")
            except Exception as e:
                _log(f"Error fetching/parsing tx digest {d}: {e}")
        _log(f"RPC parsed total {len(formatted)} transfer events for block {block_number}")
        return formatted
    except Exception as e:
        _log(f"RPC block-txs attempt failed for block {block_number}: {e}")
        raise


def _format_indexer_txs(data_list: list) -> list:
    formatted = []
    for tx in data_list:
        try:
            formatted.append({
                "hash": tx.get("hash") or tx.get("digest") or tx.get("txHash"),
                "from": tx.get("from") or tx.get("sender"),
                "to": tx.get("to") or tx.get("recipient") or tx.get("toAddress"),
                "value": float(tx.get("value", 0) or 0),
                "timeStamp": tx.get("timestamp") or tx.get("timeStamp") or tx.get("ts"),
            })
        except Exception as e:
            logging.error(f"Format indexer tx error: {e}")
    return formatted


def _rpc_post(url: str, payload: dict, timeout: int = 10):
    headers = {"Content-Type": "application/json"}
    try:
        # If BlockBerry key is present, prefer BlockBerry-only flow and avoid RPC calls
        if BLOCKBERRY_API_KEY:
            _log("RPC calls disabled because BLOCKBERRY_API_KEY is set; skipping _rpc_post")
            raise RuntimeError("RPC disabled when BLOCKBERRY_API_KEY is present")
        return requests.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception as e:
        _log(f"RPC post error to {url}: {e}")
        raise


def fetch_blockberry_transactions_by_checkpoint(block_number: int, max_pages: int = 5, page_size: int = 50):
    """Try several BlockBerry endpoint shapes that support filtering by checkpoint.

    Returns a list of normalized tx dicts (hash, from, to, value, timeStamp, checkpoint, direction).
    """
    if not BLOCKBERRY_API_KEY:
        return []
    headers = {"accept": "*/*", "x-api-key": BLOCKBERRY_API_KEY}
    base = BLOCKBERRY_BASE
    found = []

    # Try the documented POST /transactions with filters
    txs_url = f"{base}/transactions?page=0&size={page_size}&orderBy=DESC&sortBy=AGE"
    for page in range(0, max_pages):
        body = {"filters": [{"field": "checkpoint", "op": "eq", "value": int(block_number)}], "page": page, "size": page_size}
        try:
            r = _blockberry_request_with_backoff("POST", txs_url.replace("page=0", f"page={page}"), headers={**headers, "Content-Type": "application/json"}, json_body=body, timeout=12)
        except Exception as e:
            _log(f"BlockBerry documented POST /transactions error (page {page}): {e}")
            r = None
        if r is None:
            continue
        if r.status_code != 200:
            _log(f"BlockBerry documented POST non-200 (page {page}): {r.status_code} - snippet: {(r.text or '')[:200]}")
            continue
        try:
            j = r.json()
        except Exception:
            _log(f"BlockBerry documented POST returned non-JSON (page {page}): {(r.text or '')[:200]}")
            continue
        content = j.get("content") or j.get("data") or j.get("result") or []
        if isinstance(content, dict) and content.get("data"):
            content = content.get("data")
        if not isinstance(content, list):
            _log(f"BlockBerry documented POST unexpected content shape (page {page}): {(r.text or '')[:200]}")
            continue

        for tx in content:
            try:
                if int(tx.get("checkpoint", 0) or 0) != int(block_number):
                    continue
                # Build per-address SUI delta if available
                owner_deltas = {}
                total_sui = 0.0
                for bc in tx.get("balanceChanges") or []:
                    ct = bc.get("coinType") or ""
                    amt = bc.get("amount")
                    owner = bc.get("owner") or bc.get("address") or bc.get("ownerAddress") or bc.get("addressOwner")
                    try:
                        n = int(amt)
                    except Exception:
                        try:
                            n = int(float(amt))
                        except Exception:
                            n = 0
                    if ct == "0x2::sui::SUI":
                        sui_val = n / 1_000_000.0
                        total_sui += sui_val
                        if owner:
                            owner_deltas.setdefault(owner, 0.0)
                            owner_deltas[owner] += sui_val

                sender = tx.get("senderAddress") or tx.get("sender")
                direction = None
                value_abs = None
                if sender and owner_deltas:
                    sender_delta = owner_deltas.get(sender)
                    if sender_delta is not None:
                        value_abs = abs(sender_delta)
                        direction = "out" if sender_delta < 0 else ("in" if sender_delta > 0 else "neutral")
                if value_abs is None:
                    value_abs = abs(total_sui)
                    direction = "out" if total_sui < 0 else ("in" if total_sui > 0 else "neutral")

                found.append({
                    "hash": tx.get("txHash"),
                    "from": tx.get("senderAddress") or tx.get("sender"),
                    "to": None,
                    "value": float(value_abs),
                    "timeStamp": tx.get("timestamp"),
                    "checkpoint": tx.get("checkpoint"),
                    "direction": direction,
                })
            except Exception:
                continue

        if found:
            return found

    # If documented POST didn't work, try a few candidate path templates
    candidate_paths = [
        f"{base}/transactions?checkpoint={block_number}&page={{page}}&size={page_size}&orderBy=DESC&sortBy=AGE",
        f"{base}/transactions?page={{page}}&size={page_size}&checkpoint={block_number}&orderBy=DESC&sortBy=AGE",
        f"{base}/transaction-blocks/{block_number}/transactions?page={{page}}&size={page_size}",
        f"{base}/transaction-blocks?checkpoint={block_number}&page={{page}}&size={page_size}",
        f"{base}/blocks/{block_number}/transactions?page={{page}}&size={page_size}",
    ]

    for path_tpl in candidate_paths:
        try:
            for page in range(0, max_pages):
                url = path_tpl.format(page=page)
                try:
                    if "/transactions" in url:
                        r = _blockberry_request_with_backoff("POST", url, headers=headers, json_body=None, timeout=12)
                    else:
                        r = _blockberry_request_with_backoff("GET", url, headers=headers, json_body=None, timeout=12)
                except Exception as e:
                    _log(f"BlockBerry probe error for {url}: {e}")
                    break
                if r.status_code != 200:
                    _log(f"BlockBerry probe non-200 for {url}: {r.status_code}")
                    break
                try:
                    j = r.json()
                except Exception:
                    _log(f"BlockBerry non-JSON for {url}: {(r.text or '')[:200]}")
                    break
                content = j.get("content") or j.get("data") or j.get("result") or []
                if isinstance(content, dict) and content.get("data"):
                    content = content.get("data")
                if not isinstance(content, list):
                    _log(f"BlockBerry unexpected content shape for {url}")
                    break

                for tx in content:
                    try:
                        if int(tx.get("checkpoint", 0) or 0) != int(block_number):
                            continue
                        # simpler fallback normalization
                        value_sui = 0.0
                        for bc in tx.get("balanceChanges") or []:
                            ct = bc.get("coinType") or ""
                            amt = bc.get("amount")
                            try:
                                n = int(amt)
                            except Exception:
                                try:
                                    n = int(float(amt))
                                except Exception:
                                    n = 0
                            if ct == "0x2::sui::SUI":
                                value_sui += n / 1_000_000.0
                        found.append({
                            "hash": tx.get("txHash"),
                            "from": tx.get("senderAddress") or tx.get("sender"),
                            "to": None,
                            "value": float(value_sui),
                            "timeStamp": tx.get("timestamp"),
                            "checkpoint": tx.get("checkpoint"),
                        })
                    except Exception:
                        continue
                if found:
                    return found
        except Exception as e:
            _log(f"Error probing BlockBerry path {path_tpl}: {e}")
            continue
    return []


def fetch_recent_checkpoints(limit: int = 100):
    """Fetch recent checkpoints list from BlockBerry.

    Returns a list of checkpoint sequence numbers (ints) ordered DESC (newest first).
    """
    if not BLOCKBERRY_API_KEY:
        return []
    headers = {"accept": "*/*", "x-api-key": BLOCKBERRY_API_KEY}
    # BlockBerry checkpoints endpoint
    url = f"{BLOCKBERRY_BASE}/checkpoints?page=0&size={limit}&orderBy=DESC&sortBy=AGE"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            j = r.json()
            content = j.get("content") or []
            cps = []
            for item in content:
                try:
                    cp = item.get("sequence") or item.get("checkpoint") or item.get("id")
                    if cp is not None:
                        cps.append(int(cp))
                except Exception:
                    continue
            return cps
        # If not 200, log full snippet and fall back to collecting checkpoints from recent transactions
        snippet = (r.text or '')[:400]
        _log(f"BlockBerry checkpoints non-200: {r.status_code}. Snippet: {snippet}")
    except Exception as e:
        _log(f"Error fetching BlockBerry checkpoints (GET): {e}")

    # Fallback: collect checkpoints by paging recent /transactions and deduplicating
    try:
        page_size = 50
        pages = max(1, (limit + page_size - 1) // page_size)
        seen = []
        seen_set = set()
        for page in range(0, pages):
            t_url = f"{BLOCKBERRY_BASE}/transactions?page={page}&size={page_size}&orderBy=DESC&sortBy=AGE"
            try:
                r2 = _blockberry_request_with_backoff("POST", t_url, headers=headers, json_body=None, timeout=12)
                if r2.status_code != 200:
                    _log(f"BlockBerry transactions page {page} non-200 during checkpoints fallback: {r2.status_code}")
                    break
                j2 = r2.json()
                content = j2.get("content") or []
                if not isinstance(content, list) or len(content) == 0:
                    break
                for tx in content:
                    try:
                        cp = tx.get("checkpoint")
                        if cp is None:
                            continue
                        cpn = int(cp)
                        if cpn not in seen_set:
                            seen.append(cpn)
                            seen_set.add(cpn)
                            if len(seen) >= limit:
                                break
                    except Exception:
                        continue
                if len(seen) >= limit:
                    break
            except Exception as e:
                _log(f"Error paging BlockBerry transactions during checkpoints fallback (page {page}): {e}")
                break
        return seen
    except Exception as e:
        _log(f"Fallback error collecting checkpoints from transactions: {e}")
        return []


def fetch_recent_blockberry_transactions(limit: int = 200, page_size: int = 50):
    """Fetch recent transactions from BlockBerry by paging and normalize SUI values.

    Returns list of tx dicts: {hash, from, to, value, timeStamp, checkpoint}
    """
    if not BLOCKBERRY_API_KEY:
        return []
    headers = {"accept": "*/*", "x-api-key": BLOCKBERRY_API_KEY}
    url_tpl = "https://api.blockberry.one/sui/v1/transactions?page={page}&size={size}&orderBy=DESC&sortBy=AGE"
    collected = []
    seen_hashes = set()
    pages = 0
    page = 0
    while len(collected) < limit and pages < 20:
            r = _blockberry_request_with_backoff("POST", url_tpl.format(page=page, size=page_size), headers=headers, json_body=None, timeout=12)
            if r.status_code != 200:
                _log(f"BlockBerry recent page {page} non-200: {r.status_code}")
                break
            try:
                j = r.json()
            except Exception as e:
                _log(f"BlockBerry recent page {page} JSON error: {e}")
                break
            content = j.get("content") or []
            if not isinstance(content, list) or len(content) == 0:
                break
            for tx in content:
                try:
                    txhash = tx.get("txHash")
                    if not txhash or txhash in seen_hashes:
                        continue
                    seen_hashes.add(txhash)
                    value_sui = 0.0
                    for bc in tx.get("balanceChanges") or []:
                        ct = bc.get("coinType") or ""
                        amt = bc.get("amount")
                        try:
                            n = int(amt)
                        except Exception:
                            try:
                                n = int(float(amt))
                            except Exception:
                                n = 0
                        if ct == "0x2::sui::SUI":
                            value_sui += n / 1_000_000.0
                    collected.append({
                        "hash": txhash,
                        "from": tx.get("senderAddress") or tx.get("sender"),
                        "to": None,
                        "value": float(value_sui),
                        "timeStamp": tx.get("timestamp"),
                        "checkpoint": tx.get("checkpoint"),
                    })
                    if len(collected) >= limit:
                        break
                except Exception:
                    continue
            page += 1
            pages += 1
    return collected


def _detect_working_rpc() -> str | None:
    global SUI_RPC_URL
    # When BlockBerry is the chosen indexer, skip RPC detection to avoid
    # contacting unrelated fullnodes. This keeps behavior deterministic.
    if BLOCKBERRY_API_KEY:
        _log("Skipping RPC detection because BLOCKBERRY_API_KEY is set")
        return None
    if SUI_RPC_URL:
        return SUI_RPC_URL
    for candidate in _RPC_CANDIDATES:
        if not candidate:
            continue
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTotalTransactionBlocks", "params": []}
            r = _rpc_post(candidate, payload, timeout=6)
            if r.status_code != 200:
                _log(f"RPC probe non-200 for {candidate}: {r.status_code}")
                continue
            try:
                j = r.json()
                if "result" in j:
                    SUI_RPC_URL = candidate
                    _log(f"Detected working SUI RPC: {candidate}")
                    return candidate
            except Exception:
                _log(f"RPC probe returned non-JSON for {candidate}; snippet: {(r.text or '')[:200]}")
                continue
        except Exception as e:
            _log(f"RPC probe error for {candidate}: {e}")
            continue
    return None


def _parse_sui_rpc_tx(txobj: dict):
    # Try to extract transfers from transaction block result.
    out = []
    try:
        # events often live in txobj.get('events') or txobj.get('effects', {}).get('events')
        events = txobj.get("events") or (txobj.get("effects") or {}).get("events") or []
        sender = None
        try:
            sender = txobj.get("transaction", {}).get("data", {}).get("sender")
        except Exception:
            sender = None
        for ev in events:
            try:
                # support different shapes
                if isinstance(ev, dict):
                    typ = ev.get("type") or ev.get("eventType") or ""
                    # common Sui native transfer event name contains 'TransferSui' or 'Transfer'
                    if "TransferSui" in str(typ) or "Transfer" in str(typ):
                        amt = None
                        to_addr = None
                        # amount might be in ev['parsed']['amount'] or ev['amount']
                        parsed = ev.get("parsed") or {}
                        amt = parsed.get("amount") or ev.get("amount") or parsed.get("amount_sui")
                        to_addr = parsed.get("recipient") or ev.get("recipient") or ev.get("to")
                        if amt is not None:
                            out.append({
                                "hash": txobj.get("digest") or txobj.get("transaction_digest") or txobj.get("txDigest"),
                                "from": (sender or ev.get("sender") or ev.get("from") or "") ,
                                "to": to_addr,
                                "value": float(amt),
                                "timeStamp": txobj.get("timestamp") or txobj.get("txTimestamp") or None,
                            })
            except Exception:
                continue
    except Exception:
        return None
    return out


def scan_recent_transactions_by_sequence(num_sequences: int = 500, min_value_sui: float = 1500000, chunk_size: int = 100):
    """Scan recent transaction sequences (not block heights) via RPC and collect transfer events >= min_value_sui.

    This pages transaction sequences using `sui_getTotalTransactionBlocks` and
    `sui_getTransactionBlocks(start, end)`, then fetches each digest via
    `sui_getTransactionBlock`. We group results by a block-like key (checkpoint when
    available, otherwise the sequence number).
    """
    # If BlockBerry mode is enabled, we avoid RPC-based scanning entirely.
    if BLOCKBERRY_API_KEY:
        _log("scan_recent_transactions_by_sequence skipped because BLOCKBERRY_API_KEY is set")
        return {}
    rpc = _detect_working_rpc()
    if not rpc:
        raise RuntimeError("No working RPC detected")
    # get total transaction sequences
    payload = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTotalTransactionBlocks", "params": []}
    r = _rpc_post(rpc, payload, timeout=8)
    j = r.json()
    total = j.get("result")
    try:
        total_n = int(total) if total is not None else 0
    except Exception:
        total_n = 0
    if total_n <= 0:
        _log(f"scan_recent_transactions: invalid total tx count from RPC: {j}")
        return []

    start_seq = max(0, total_n - num_sequences + 1)
    _log(f"scan_recent_transactions: total={total_n}, start_seq={start_seq}, end_seq={total_n}")

    found_events = []
    # page in chunks because nodes may limit return size
    seq = start_seq
    while seq <= total_n:
        end_seq = min(total_n, seq + chunk_size - 1)
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTransactionBlocks", "params": [seq, end_seq]}
            r = _rpc_post(rpc, payload, timeout=12)
            j = r.json()
            digests = j.get("result") or []
            if not isinstance(digests, list):
                digests = [digests]
            _log(f"scanned sequences {seq}-{end_seq}: digests returned={len(digests)}")
            # fetch each digest
            for idx, d in enumerate(digests, start=seq):
                try:
                    p2 = {"jsonrpc": "2.0", "id": 1, "method": "sui_getTransactionBlock", "params": [d]}
                    r2 = _rpc_post(rpc, p2, timeout=10)
                    j2 = r2.json()
                    txobj = j2.get("result") or {}
                    parsed = _parse_sui_rpc_tx(txobj) or []
                    if not isinstance(parsed, list):
                        parsed = [parsed]
                    # determine block-like key
                    block_key = txobj.get("checkpoint") or (txobj.get("effects") or {}).get("checkpoint") or f"seq_{idx}"
                    for ev in parsed:
                        try:
                            val = float(ev.get("value", 0) or 0)
                        except Exception:
                            continue
                        if abs(val) >= min_value_sui:
                            # attach block key and sequence
                            ev_record = {
                                "block_key": block_key,
                                "sequence": idx,
                                "hash": ev.get("hash"),
                                "from": (ev.get("from") or "").lower(),
                                "to": (ev.get("to") or "").lower(),
                                "value": val,
                                "time": ev.get("timeStamp") or None,
                            }
                            found_events.append(ev_record)
                except Exception as e:
                    _log(f"Error fetching/parsing digest {d} (seq {idx}): {e}")
                    continue
        except Exception as e:
            _log(f"Error fetching sequence chunk {seq}-{end_seq}: {e}")
        seq = end_seq + 1

    # group by block_key for output
    grouped = {}
    for ev in found_events:
        k = ev.get("block_key") or ev.get("sequence")
        grouped.setdefault(k, []).append(ev)

    # persist new entries into whale history (flattened with block_key as block)
    existing = load_whale_history() or []
    existing_hashes = {d.get("hash") for d in existing if d.get("hash")}
    new_entries = []
    for k, items in grouped.items():
        for it in items:
            if it.get("hash") not in existing_hashes:
                new_entries.append({
                    "block": k,
                    "hash": it.get("hash"),
                    "from": it.get("from"),
                    "to": it.get("to"),
                    "value": it.get("value"),
                    "time": it.get("time"),
                    "type": classify_transaction(it.get("from"), it.get("to")),
                })
    if new_entries:
        merged = existing + new_entries
        save_whale_history(merged)
        _log(f"scan_recent_transactions saved {len(new_entries)} new whale events")
    else:
        _log("scan_recent_transactions found no new whale events")

    return grouped


def scan_recent_events_via_suix(limit: int = 500, min_value_sui: float = 1500000, time_range_ms: tuple | None = None):
    """Query recent events using suix_queryEvents (indexer-like RPC on fullnode) and extract transfers.

    Params:
      - limit: total events to request (will page if needed)
      - min_value_sui: threshold for SUI amount to consider a whale
      - time_range_ms: optional (start_ms, end_ms) to restrict the query
    """
    # When using BlockBerry indexer, don't run suix RPC event scans.
    if BLOCKBERRY_API_KEY:
        _log("scan_recent_events_via_suix skipped because BLOCKBERRY_API_KEY is set")
        return {}
    rpc = _detect_working_rpc()
    if not rpc:
        raise RuntimeError("No working RPC detected")

    fetched = 0
    cursor = None
    page = 100 if limit > 100 else limit
    found = []

    # build initial query
    if time_range_ms and isinstance(time_range_ms, tuple) and len(time_range_ms) == 2:
        query = {"TimeRange": {"start_time": time_range_ms[0], "end_time": time_range_ms[1]}}
    else:
        query = {"All": []}

    while fetched < limit:
        params = [query, cursor, page]
        try:
            r = _rpc_post(rpc, {"jsonrpc": "2.0", "id": 1, "method": "suix_queryEvents", "params": params})
            # our _rpc_post returns Response; if an error, it will have been logged
            j = r.json()
        except Exception as e:
            _log(f"suix_queryEvents call error: {e}")
            break

        res = j.get("result") if isinstance(j, dict) else None
        data = None
        next_cursor = None
        if isinstance(res, dict):
            data = res.get("data") or []
            next_cursor = res.get("nextCursor")
        elif isinstance(res, list):
            data = res
        else:
            _log(f"suix_queryEvents unexpected result shape: {j}")
            break

        _log(f"suix_queryEvents returned {len(data)} events (cursor={cursor})")

        for ev in data:
            try:
                # event envelope shape from suix_queryEvents includes parsedJson
                tx_digest = None
                ev_id = ev.get("id") or {}
                if isinstance(ev_id, dict):
                    tx_digest = ev_id.get("txDigest") or ev_id.get("tx_digest")
                tx_digest = tx_digest or ev.get("txDigest") or ev.get("transactionDigest")

                typ = ev.get("type") or ev.get("transactionModule") or ev.get("eventType") or ""
                parsed = ev.get("parsedJson") or ev.get("parsed") or ev.get("parsed_json") or {}
                sender = ev.get("sender") or (parsed.get("sender") if isinstance(parsed, dict) else None)

                # Heuristics: if type contains 'Transfer' or parsed has amount/recipient
                amount = None
                recipient = None
                if isinstance(parsed, dict):
                    amount = parsed.get("amount") or parsed.get("value") or parsed.get("amount_sui")
                    recipient = parsed.get("recipient") or parsed.get("to") or parsed.get("recipient_address")
                # fallback to top-level fields
                amount = amount or ev.get("amount") or ev.get("value")

                try:
                    val = float(amount) if amount is not None else 0.0
                except Exception:
                    val = 0.0

                if ("Transfer" in str(typ) or val > 0) and abs(val) >= float(min_value_sui):
                    rec = (recipient or "").lower() if recipient else ""
                    fr = (sender or "").lower() if sender else ""
                    found.append({
                        "block_key": ev.get("checkpoint") or ev.get("checkpointSequence") or ev.get("sequence") or tx_digest,
                        "hash": tx_digest,
                        "from": fr,
                        "to": rec,
                        "value": val,
                        "time": ev.get("timestamp") or ev.get("time") or None,
                    })
            except Exception as e:
                _log(f"Error parsing suix event: {e}")
                continue

        fetched += len(data)
        if not next_cursor or len(data) == 0:
            break
        cursor = next_cursor

    # group and persist similar to other scanner
    grouped = {}
    existing = load_whale_history() or []
    existing_hashes = {d.get("hash") for d in existing if d.get("hash")}
    new_entries = []
    for ev in found:
        k = ev.get("block_key") or ev.get("hash")
        grouped.setdefault(k, []).append(ev)
        if ev.get("hash") not in existing_hashes:
            new_entries.append({
                "block": k,
                "hash": ev.get("hash"),
                "from": ev.get("from"),
                "to": ev.get("to"),
                "value": ev.get("value"),
                "time": ev.get("time"),
                "type": classify_transaction(ev.get("from"), ev.get("to")),
            })

    if new_entries:
        merged = existing + new_entries
        save_whale_history(merged)
        _log(f"scan_recent_events_via_suix saved {len(new_entries)} new events")
    else:
        _log("scan_recent_events_via_suix found no new events")

    return grouped


# --- Persistence helpers ---


def save_last_block(block_num: int):
    if db.available():
        try:
            db.set_kv("sui_meta", "last_block", {"last_block": int(block_num)})
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
            kv = db.get_kv("sui_meta", "last_block") or {}
            db_last = kv.get("last_block")
            if local_last and (db_last is None or int(local_last) > int(db_last)):
                db.set_kv("sui_meta", "last_block", {"last_block": int(local_last)})
            return (db.get_kv("sui_meta", "last_block") or {}).get("last_block")
        except Exception:
            pass
    return local_last


def save_whale_history(history: list[dict]):
    if db.available() and isinstance(history, list):
        try:
            db.upsert_many("sui_whale_history", history, unique_keys=["hash"])
        except Exception:
            pass
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)
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
            db_hist = db.find_all("sui_whale_history", sort_field="time", ascending=True)
            db_hashes = {d.get("hash") for d in db_hist if isinstance(d, dict) and d.get("hash")}
            new_entries = [e for e in local if e.get("hash") not in db_hashes]
            if new_entries:
                db.upsert_many("sui_whale_history", new_entries, unique_keys=["hash"])
            return db.find_all("sui_whale_history", sort_field="time", ascending=True)
        except Exception:
            pass
    return local


# --- Background scanner ---


def background_whale_alert_scanner(min_value_sui: float = 1500000, num_blocks: int = 300, interval_sec: int = 300):
    while True:
        try:
            _log("Starting SUI whale alert scan loop.")
            # Instead of sweeping an open-ended block range, request recent checkpoints
            # from BlockBerry and scan only up to MAX_CHECKPOINTS_PER_SCAN per run.
            checkpoints = fetch_recent_checkpoints(limit=MAX_CHECKPOINTS_PER_SCAN)
            if not checkpoints:
                # fallback to previous latest-block fallback if checkpoints not available
                latest = fetch_latest_block_number()
                checkpoints = [latest - i for i in range(0, min(num_blocks, MAX_CHECKPOINTS_PER_SCAN))]
            _log(f"Checkpoints to scan (count={len(checkpoints)}): {checkpoints[:10]}")

            history = load_whale_history()
            seen = {tx.get("hash") for tx in history}

            # determine a start_block for this scan run so we can persist progress
            # prefer the newest checkpoint if available, otherwise fetch latest block
            try:
                start_block = int(checkpoints[0]) if checkpoints else int(fetch_latest_block_number())
            except Exception:
                start_block = None
            _log(f"Starting scan with start_block={start_block}")

            # Initialize per-scan accumulators for reporting
            scan_total_tx_count = 0
            scan_total_sui = 0.0

            for blk in checkpoints:
                try:
                    txs = fetch_block_transactions(blk) or []

                    # Compute per-block scanned metrics (sum of absolute SUI values and tx count)
                    try:
                        blk_tx_count = len(txs)
                    except Exception:
                        blk_tx_count = 0
                    blk_sui_total = 0.0
                    for _t in txs:
                        try:
                            blk_sui_total += abs(float(_t.get("value", 0) or 0))
                        except Exception:
                            continue

                    _log(f"Scanned block {blk}: tx_count={blk_tx_count}, total_sui={blk_sui_total}")

                    # accumulate per-scan totals
                    try:
                        scan_total_tx_count += blk_tx_count
                        scan_total_sui += blk_sui_total
                    except NameError:
                        # initialize if not present in this run
                        scan_total_tx_count = blk_tx_count
                        scan_total_sui = blk_sui_total

                    for tx in txs:
                        value_sui = float(tx.get("value", 0) or 0)
                        if abs(value_sui) < min_value_sui:
                            continue
                        h = tx.get("hash") or ""
                        if h in seen:
                            continue
                        from_addr = (tx.get("from") or "").lower()
                        to_addr = (tx.get("to") or "").lower()
                        etype = classify_transaction(from_addr, to_addr)
                        obj = {
                            "block": blk,
                            "hash": h,
                            "from": from_addr,
                            "to": to_addr,
                            "value": value_sui,
                            "time": datetime.utcfromtimestamp(int(tx.get("timeStamp", "0") or 0) or int(time.time())).strftime("%Y-%m-%d %H:%M:%S"),
                            "type": etype,
                        }
                        history.append(obj)
                        seen.add(h)
                except Exception as e:
                    _log(f"Error processing checkpoint {blk}: {e}")

            # Determine a sensible start_block to persist as last scanned block.
            # Prefer the newest checkpoint we fetched (first item), otherwise fall back to the latest block number.
            start_block = None
            try:
                if checkpoints and len(checkpoints) > 0:
                    start_block = int(checkpoints[0])
            except Exception:
                start_block = None
            if start_block is None:
                try:
                    start_block = int(fetch_latest_block_number())
                except Exception:
                    start_block = 0

            # Log per-scan summary of what we scanned (total txs and total SUI observed)
            try:
                _log(f"Scan summary: scanned_blocks={len(checkpoints)}, total_tx_count={scan_total_tx_count}, total_sui={scan_total_sui}")
            except Exception:
                pass

            # Trim history to keep only entries meeting the threshold and avoid unbounded growth.
            history = [tx for tx in history if abs(float(tx.get("value", 0) or 0)) >= min_value_sui]
            # Keep most recent 1000 entries
            history = history[-1000:]

            # Persist last block and whale history
            try:
                # persist last scanned block (use start_block if we set it, otherwise infer)
                try:
                    if start_block is None:
                        # fallback to latest known
                        lb = fetch_latest_block_number()
                        save_last_block(lb)
                        _log(f"Saved last_block fallback={lb}")
                    else:
                        save_last_block(start_block)
                        _log(f"Saved last_block={start_block}")
                except Exception as e:
                    _log(f"Failed to save last_block: {e}")
            except Exception as e:
                _log(f"Failed to save last_block {start_block}: {e}")
            try:
                save_whale_history(history)
                _log(f"Scanner persisted {len(history)} whale history entries; last_block={start_block}")
            except Exception as e:
                _log(f"Failed to save whale history: {e}")
        except Exception as e:
            _log(f"Scanner error: {e}")
        time.sleep(interval_sec)


# --- UI ---


def show_sui_whale_alert_realtime(min_value_sui: float = 1500000, num_blocks: int = 100):
    st.markdown(
        """
<div style='font-size:22px;font-weight:bold;margin-bottom:8px;'>
    🐳 Whale Alert - SUI Large Transactions
</div>
        """,
        unsafe_allow_html=True,
    )
    whale_txs = load_whale_history()
    last_block = load_last_block()
    seen_block = load_user_seen_block()
    box = []
    if not whale_txs:
        box.append("<div style='color:#888;'>No recent large transactions.</div>")
    else:
        for tx in whale_txs[::-1]:
            is_new = last_block is not None and int(tx.get("block", 0) or 0) > int(seen_block)
            badge = (
                "<span style='color:#fff;background:#43a047;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>NEW</span>"
                if is_new
                else "<span style='color:#fff;background:#888;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px;vertical-align:middle;'>OLD</span>"
            )
            box.append(
                f"<div style='margin-bottom:8px;'>{badge}<span style='color:#1e88e5;font-weight:bold;'>🐳 {tx.get('value',0):.2f} SUI</span> | Hash: <code>{(tx.get('hash','') or '')[:12]}...</code> | From: <code>{tx.get('from','')}</code> → To: <code>{tx.get('to','')}</code> | <span style='color:#888;'>{tx.get('time','')}</span></div>"
            )
    st.markdown(
        "<div style='height: 260px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; padding: 8px; background: #f9f9f9; margin-top: 16px;'>"
        + "".join(box)
        + "</div>",
        unsafe_allow_html=True,
    )


# Launch background thread once
_sui_whale_bg_started = False


def ensure_background_scanner_started():
    global _sui_whale_bg_started
    if not _sui_whale_bg_started:
        try:
            _log("Starting SUI whale background scanner thread...")
            t = threading.Thread(target=background_whale_alert_scanner, args=(100, 100, 300), daemon=True)
            t.start()
            _sui_whale_bg_started = True
            _log("SUI whale background scanner thread started successfully")
        except Exception as e:
            _log(f"Failed to start SUI whale background scanner: {e}")


# Auto-start when module is imported
_log("SUI whale alert module imported")
ensure_background_scanner_started()