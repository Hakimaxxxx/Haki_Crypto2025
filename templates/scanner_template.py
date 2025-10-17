"""
Scanner template for adding a new chain whale scanner.
- Place this file in `<CHAIN>/metrics_<chain>_whale_alert_realtime.py`
- Follow the guarded startup pattern to avoid import-time side effects.
"""
from __future__ import annotations
import os
import json
import time
import threading
from typing import List, Dict

# CONFIG
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "<chain>_whale_alert_history.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "<chain>_whale_scanner.log")

# Environment keys
RPC_URL_KEY = "<CHAIN>_RPC_URL"
INDEXER_KEY = "<CHAIN>_INDEXER_KEY"

# Keep scanner thread handle here so import doesn't start it accidentally
_scanner_thread: threading.Thread | None = None
_stop_flag = threading.Event()


def _log(msg: str) -> None:
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def _load_history() -> List[Dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def _save_event(event: Dict) -> None:
    h = _load_history()
    h.append(event)
    with open(HISTORY_FILE, "w") as f:
        json.dump(h[-10000:], f)  # keep last N events


def _scan_loop(poll_interval: int = 10):
    _log("scanner started")
    while not _stop_flag.is_set():
        try:
            # TODO: implement chain-specific probing and event detection
            # Example event shape:
            # event = {"ts": int(time.time()), "symbol": "TOKEN", "value_usd": 12345.0, "type":"transfer", "direction":"out"}
            # _save_event(event)
            pass
        except Exception as e:
            _log(f"scan error: {e}")
        _stop_flag.wait(poll_interval)
    _log("scanner stopped")


def start_scanner(poll_interval: int = 10) -> None:
    """Start background scanner in guarded way. Call this from a safe entrypoint (not module import)."""
    global _scanner_thread
    if _scanner_thread and _scanner_thread.is_alive():
        return
    _stop_flag.clear()
    _scanner_thread = threading.Thread(target=_scan_loop, args=(poll_interval,), daemon=True)
    _scanner_thread.start()


def stop_scanner() -> None:
    _stop_flag.set()
    if _scanner_thread:
        _scanner_thread.join(timeout=5)


def diagnostic_status() -> Dict:
    return {
        "history_file": HISTORY_FILE,
        "log_file": LOG_FILE,
        "thread_alive": _scanner_thread.is_alive() if _scanner_thread else False,
        "env_rpc": bool(os.environ.get(RPC_URL_KEY)),
        "env_indexer": bool(os.environ.get(INDEXER_KEY)),
    }
