import json
import os
import time
import tempfile
import threading
from typing import List, Dict
from config import HISTORY_FILE

# Simple in-memory cache
_HISTORY_CACHE: List[Dict] = []
_HISTORY_LAST_LOAD = 0
_CACHE_TTL = 30  # seconds
_HISTORY_LOCK = threading.Lock()  # prevent concurrent read/write corruption


def _atomic_write_json(obj, path: str):
    """Write JSON atomically to avoid partial writes.

    Writes to a temp file in the same directory and replaces the target file.
    """
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=dir_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tmp_f:
            json.dump(obj, tmp_f, ensure_ascii=False)
        # os.replace is atomic on both Windows and POSIX
        os.replace(tmp_path, path)
    except Exception:
        # Best effort cleanup of temp file
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def load_history(force: bool = False) -> List[Dict]:
    global _HISTORY_CACHE, _HISTORY_LAST_LOAD
    now = time.time()
    if not force and _HISTORY_CACHE and (now - _HISTORY_LAST_LOAD) < _CACHE_TTL:
        return _HISTORY_CACHE
    if not os.path.exists(HISTORY_FILE):
        _HISTORY_CACHE = []
        _HISTORY_LAST_LOAD = now
        return _HISTORY_CACHE
    try:
        with _HISTORY_LOCK:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                _HISTORY_CACHE = json.load(f)
                _HISTORY_LAST_LOAD = now
    except Exception as e:
        # Backup corrupted file and reset cache to avoid repeated failures
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            corrupt_path = f"{HISTORY_FILE}.corrupt_{ts}"
            if os.path.exists(HISTORY_FILE):
                os.replace(HISTORY_FILE, corrupt_path)
        except Exception:
            pass
        _HISTORY_CACHE = []
        _HISTORY_LAST_LOAD = now
    return _HISTORY_CACHE


def append_snapshot(docs: List[Dict]):
    """Append new snapshot docs safely with a process-wide lock and atomic write."""
    if not docs:
        return
    with _HISTORY_LOCK:
        # Load latest from disk (not from cache) to avoid missing updates from other writers
        hist: List[Dict] = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    hist = json.load(f)
            except Exception:
                # If the file is corrupt, back it up and start fresh
                try:
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    corrupt_path = f"{HISTORY_FILE}.corrupt_{ts}"
                    os.replace(HISTORY_FILE, corrupt_path)
                except Exception:
                    pass
                hist = []

        # Avoid duplication by (timestamp, coin/null)
        existing_keys = {(d.get('timestamp'), d.get('coin')) for d in hist}
        new_clean = [d for d in docs if (d.get('timestamp'), d.get('coin')) not in existing_keys]
        if not new_clean:
            return
        hist.extend(new_clean)
        try:
            _atomic_write_json(hist, HISTORY_FILE)
            # update cache
            global _HISTORY_CACHE, _HISTORY_LAST_LOAD
            _HISTORY_CACHE = hist
            _HISTORY_LAST_LOAD = time.time()
        except Exception:
            # As a last resort, do not crash
            pass


def write_full_history(hist: List[Dict]):
    """Replace the entire history file atomically under a lock.

    Intended for bootstrap operations that fetch the whole history from DB.
    """
    if not isinstance(hist, list):
        return
    with _HISTORY_LOCK:
        try:
            _atomic_write_json(hist, HISTORY_FILE)
            global _HISTORY_CACHE, _HISTORY_LAST_LOAD
            _HISTORY_CACHE = list(hist)
            _HISTORY_LAST_LOAD = time.time()
        except Exception:
            pass


def filter_portfolio_totals(hist: List[Dict]):
    return [h for h in hist if 'coin' not in h]


def filter_coin_history(hist: List[Dict], coin_id: str):
    return [h for h in hist if h.get('coin') == coin_id]
