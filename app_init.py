"""
App initialization system with robust fallback mechanisms.

Handles:
- Database bootstrap and data loading
- API initialization with background sync
- Conflict resolution between DB and API data
- Graceful degradation when services fail
"""

import json
import os
import time
import threading
import traceback
from typing import Dict, Tuple, Optional, Any
from datetime import datetime

# Application state management
_APP_STATE = {
    "db_available": False,
    "api_available": False,
    "data_loaded": False,
    "background_sync_active": False,
    "last_db_sync": 0,
    "last_api_sync": 0,
    "errors": [],
    "init_complete": False
}

# Data caches
_DATA_CACHE = {
    "portfolio": {},
    "avg_prices": {},
    "history": [],
    "prices": {},
    "price_changes": {},
    "last_write_ts": 0  # track freshest portfolio commit to prevent rollback
}

# Thread locks for data safety
_data_lock = threading.Lock()
_init_lock = threading.Lock()

def get_app_state() -> Dict[str, Any]:
    """Get current application state for diagnostics."""
    state = dict(_APP_STATE)
    # Bổ sung last_write_ts để UI hiển thị nguồn dữ liệu & kiểm tra commit
    try:
        state["last_write_ts"] = _DATA_CACHE.get("last_write_ts", 0)
    except Exception:
        state["last_write_ts"] = 0
    # Cache stats (redis) best-effort
    try:
        from redis_cache import get_cache_stats, redis_available
        state["redis_available"] = redis_available()
        state["cache_stats"] = get_cache_stats()
    except Exception:
        state["redis_available"] = False
        state["cache_stats"] = {}
    return state

def get_cached_data() -> Dict[str, Any]:
    """Get cached data safely."""
    with _data_lock:
        return {
            "portfolio": dict(_DATA_CACHE["portfolio"]),
            "avg_prices": dict(_DATA_CACHE["avg_prices"]),
            "history": list(_DATA_CACHE["history"]),
            "prices": dict(_DATA_CACHE["prices"]),
            "price_changes": dict(_DATA_CACHE["price_changes"])
        }

def _load_local_files() -> bool:
    """Load data from local JSON files as fallback."""
    try:
        local_data_loaded = False
        # Portfolio data
        if os.path.exists("data.json"):
            with open("data.json", "r") as f:
                _DATA_CACHE["portfolio"] = json.load(f)
            local_data_loaded = True
        
        # Average prices
        if os.path.exists("avg_price.json"):
            with open("avg_price.json", "r") as f:
                _DATA_CACHE["avg_prices"] = json.load(f)
            local_data_loaded = True

        # Last write timestamp (optional file)
        if os.path.exists("portfolio_meta_ts.json"):
            try:
                with open("portfolio_meta_ts.json", "r") as f:
                    ts_data = json.load(f)
                    if isinstance(ts_data, dict):
                        ts_val = int(ts_data.get("last_write_ts", 0))
                        if ts_val > _DATA_CACHE.get("last_write_ts", 0):
                            _DATA_CACHE["last_write_ts"] = ts_val
            except Exception:
                pass
        
        # History
        if os.path.exists("portfolio_history.json"):
            with open("portfolio_history.json", "r") as f:
                _DATA_CACHE["history"] = json.load(f)
            local_data_loaded = True
        
        # Last prices
        if os.path.exists("last_prices.json"):
            with open("last_prices.json", "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Support legacy formats:
                    # 1) {"prices": {...}, "price_data": {...}}
                    # 2) {"BTC": {"price":123}, ...}
                    # 3) {"BTC": 123.45, ...}
                    if "prices" in data:
                        _DATA_CACHE["prices"] = data.get("prices", {})
                        _DATA_CACHE["price_changes"] = data.get("price_data", {})
                    else:
                        # Assume direct mapping of symbol->obj/float
                        _DATA_CACHE["prices"] = data
                        # Do not overwrite existing price_changes if already loaded earlier
                        if not _DATA_CACHE["price_changes"]:
                            _DATA_CACHE["price_changes"] = {}
                local_data_loaded = True
        
        if local_data_loaded:
            print("[DEBUG] Local files loaded successfully.")
        else:
            print("[DEBUG] No local files found.")
        return local_data_loaded
    except Exception as e:
        _APP_STATE["errors"].append(f"Local file load error: {e}")
        return False

def _bootstrap_from_db() -> bool:
    """Bootstrap data from database with error handling."""
    try:
        from cloud_db import db

        if not db.available():
            print("[DEBUG] DB not available, attempting reconnect...")
            if not db.force_reconnect():
                _APP_STATE["errors"].append("DB reconnect failed.")
                return False

        # Load portfolio metadata & last_write_ts
        holdings = db.get_kv("portfolio_meta", "holdings") or {}
        avg_prices = db.get_kv("portfolio_meta", "avg_price") or {}
        last_write_ts = db.get_kv("portfolio_meta", "last_write_ts") or 0

        if holdings:
            _DATA_CACHE["portfolio"] = holdings
            with open("data.json", "w") as f:
                json.dump(holdings, f)

        if avg_prices:
            _DATA_CACHE["avg_prices"] = avg_prices
            with open("avg_price.json", "w") as f:
                json.dump(avg_prices, f)

        if isinstance(last_write_ts, (int, float)) and last_write_ts > _DATA_CACHE.get("last_write_ts", 0):
            _DATA_CACHE["last_write_ts"] = int(last_write_ts)
            try:
                with open("portfolio_meta_ts.json", "w") as f:
                    json.dump({"last_write_ts": int(last_write_ts)}, f)
            except Exception:
                pass

        # Load portfolio history
        history = db.find_all("portfolio_history", sort_field="timestamp", ascending=True)
        if history:
            _DATA_CACHE["history"] = history
            with open("portfolio_history.json", "w") as f:
                json.dump(history, f)

        _APP_STATE["db_available"] = True
        _APP_STATE["last_db_sync"] = time.time()
        print("[DEBUG] DB bootstrap completed successfully.")
        return True
    except Exception as e:
        _APP_STATE["errors"].append(f"DB bootstrap error: {e}")
        return False

def _init_api_services() -> bool:
    """Initialize API services with fallback handling."""
    try:
        print("[DEBUG] Initializing API services...")

        # Initialize price cache
        from price_utils import init_price_cache
        print("[DEBUG] Imported init_price_cache successfully.")
        init_price_cache()
        print("[DEBUG] Price cache initialized.")

        # Try to fetch initial prices
        from price_utils import fetch_prices_and_changes
        from config import COIN_LIST
        print("[DEBUG] Imported fetch_prices_and_changes and COIN_LIST successfully.")

        coins = [coin_id for coin_id, _ in COIN_LIST]
        prices, changes, success, msg = fetch_prices_and_changes(coins, force=False)
        print("[DEBUG] Fetched initial prices.")

        # Treat existing cached prices (interval) as a successful initialization if data present
        if (not success) and prices and ("Dùng cache" in str(msg) or "cache" in str(msg)):
            print("[DEBUG] Using existing cached prices for API init (interval skip).")
            success = True

        if success and prices:
            _DATA_CACHE["prices"] = prices
            _DATA_CACHE["price_changes"] = changes
            _APP_STATE["api_available"] = True
            _APP_STATE["last_api_sync"] = time.time()
            print("[DEBUG] API services initialized successfully.")
            return True
        else:
            _APP_STATE["errors"].append(f"Initial API fetch failed: {msg}")
            print(f"[DEBUG] Initial API fetch failed: {msg}")
            return False

    except Exception as e:
        print(f"[DEBUG] Exception occurred during API initialization: {e}")
        _APP_STATE["errors"].append(f"API init error: {e}")
        return False

def _background_sync():
    """Background thread for continuous data synchronization."""
    _APP_STATE["background_sync_active"] = True
    
    while _APP_STATE["background_sync_active"]:
        try:
            time.sleep(60)  # Sync every minute
            
            # API sync
            if _APP_STATE["api_available"]:
                try:
                    from price_utils import fetch_prices_and_changes
                    from config import COIN_LIST
                    
                    coins = [coin_id for coin_id, _ in COIN_LIST]
                    prices, changes, success, msg = fetch_prices_and_changes(coins, force=False)
                    
                    if success:
                        with _data_lock:
                            _DATA_CACHE["prices"] = prices
                            _DATA_CACHE["price_changes"] = changes
                        _APP_STATE["last_api_sync"] = time.time()
                    else:
                        _APP_STATE["api_available"] = False
                        _APP_STATE["errors"].append(f"Background API sync failed: {msg}")
                
                except Exception as e:
                    _APP_STATE["api_available"] = False
                    _APP_STATE["errors"].append(f"Background API error: {e}")
            
            # DB sync
            if _APP_STATE["db_available"]:
                try:
                    from cloud_db import db
                    from db_utils import db_retry_queue
                    
                    # Check DB connection with debug info
                    db_conn_info = db.get_connection_info()
                    if db.available():
                        # Process any queued writes
                        db_retry_queue(db)
                        _APP_STATE["last_db_sync"] = time.time()
                        print(f"[DEBUG] DB sync successful at {time.time()}")
                    else:
                        _APP_STATE["db_available"] = False
                        error_msg = f"DB became unavailable during sync. Info: {db_conn_info}"
                        _APP_STATE["errors"].append(error_msg)
                        print(f"[DEBUG] {error_msg}")
                        
                        # Try to reconnect
                        print("[DEBUG] Attempting DB reconnect in background...")
                        if db.force_reconnect():
                            _APP_STATE["db_available"] = True
                            print("[DEBUG] Background DB reconnect successful!")
                
                except Exception as e:
                    _APP_STATE["db_available"] = False
                    error_msg = f"Background DB error: {e}"
                    _APP_STATE["errors"].append(error_msg)
                    print(f"[DEBUG] {error_msg}")
            else:
                # Try to reconnect if DB was previously unavailable
                try:
                    from cloud_db import db
                    if db.force_reconnect():
                        _APP_STATE["db_available"] = True
                        print("[DEBUG] DB reconnected from unavailable state!")
                except Exception as e:
                    print(f"[DEBUG] DB reconnect attempt failed: {e}")
            
            # Clean old errors (keep last 10)
            if len(_APP_STATE["errors"]) > 10:
                _APP_STATE["errors"] = _APP_STATE["errors"][-10:]
                
        except Exception as e:
            _APP_STATE["errors"].append(f"Background sync error: {e}")

def initialize_app(refresh: bool = False) -> Tuple[bool, str]:
    """Initialize the application (idempotent) with robust error handling.

    Parameters
    ----------
    refresh: bool
        If True, forces a hydration pass (re-load from local/DB) even when already initialized.
        Useful for new Streamlit sessions after browser hard refresh where session_state is empty.
    """
    with _init_lock:
        if _APP_STATE["init_complete"] and not refresh:
            # If caches somehow empty (edge case after code reload) attempt lightweight hydration
            if (not _DATA_CACHE["portfolio"]) and os.path.exists("data.json"):
                try:
                    _load_local_files()
                except Exception:
                    pass
            # If portfolio still empty, try DB bootstrap once more (non-intrusive)
            if not _DATA_CACHE["portfolio"]:
                try:
                    _bootstrap_from_db()
                except Exception:
                    pass
            return True, "App already initialized"
        if _APP_STATE["init_complete"] and refresh:
            # Force re-hydration path
            try:
                _load_local_files()
            except Exception:
                pass
            try:
                _bootstrap_from_db()
            except Exception:
                pass
            return True, "App already initialized (hydrated)"
        
        try:
            _APP_STATE["errors"].clear()
            
            # Step 1: Load local files as base
            local_loaded = _load_local_files()
            
            # Step 2: Try to bootstrap from DB
            db_loaded = _bootstrap_from_db()
            
            # Step 3: Prioritize DB data over local files
            if db_loaded:
                print("[DEBUG] Using DB data as primary source.")
            elif local_loaded:
                print("[DEBUG] Falling back to local files.")
            else:
                print("[DEBUG] No data sources available.")
                return False, "Initialization failed: No data sources available."
            
            # Step 4: Initialize API services
            api_loaded = _init_api_services()
            
            # Step 5: Start background sync if any service is available
            if db_loaded or api_loaded:
                def _delayed_start():
                    time.sleep(1)  # Wait 1 second before starting background sync
                    _background_sync()
                sync_thread = threading.Thread(target=_delayed_start, daemon=True)
                sync_thread.start()
            
            _APP_STATE["init_complete"] = True
            
            sources = []
            if local_loaded:
                sources.append("local files")
            if db_loaded:
                sources.append("database")
            if api_loaded:
                sources.append("API")
            
            return True, f"App initialized successfully from: {', '.join(sources)}"
        except Exception as e:
            _APP_STATE["errors"].append(f"Init error: {e}")
            return False, f"Initialization failed: {e}"

def get_portfolio_data() -> Tuple[Dict, Dict]:
    """Get portfolio and average price data with fallback."""
    with _data_lock:
        return dict(_DATA_CACHE["portfolio"]), dict(_DATA_CACHE["avg_prices"])

def get_price_data() -> Tuple[Dict, Dict]:
    """Get current prices and changes with fallback."""
    with _data_lock:
        return dict(_DATA_CACHE["prices"]), dict(_DATA_CACHE["price_changes"])

def get_history_data() -> list:
    """Get portfolio history with fallback."""
    with _data_lock:
        return list(_DATA_CACHE["history"])

def update_portfolio_data(portfolio: Dict, avg_prices: Dict):
    """Update portfolio data safely (replace semantics) and stamp last_write_ts."""
    now_ts = int(time.time())
    with _data_lock:
        # Replace rather than partial update to avoid stale keys
        _DATA_CACHE["portfolio"] = dict(portfolio)
        _DATA_CACHE["avg_prices"] = dict(avg_prices)
        _DATA_CACHE["last_write_ts"] = now_ts
    # Persist to local files (atomic-ish best effort)
    try:
        with open("data.json", "w") as f:
            json.dump(_DATA_CACHE["portfolio"], f)
        with open("avg_price.json", "w") as f:
            json.dump(_DATA_CACHE["avg_prices"], f)
        with open("portfolio_meta_ts.json", "w") as f:
            json.dump({"last_write_ts": now_ts}, f)
    except Exception as e:
        _APP_STATE["errors"].append(f"Local save error: {e}")
    # Invalidate / bump portfolio version in Redis (read-through dependent caches can use version)
    try:
        from redis_cache import bump_portfolio_version
        bump_portfolio_version()
    except Exception:
        pass
    # Update DB if available
    if _APP_STATE["db_available"]:
        try:
            from cloud_db import db
            from db_utils import db_set_kv_with_retry, db_retry_queue
            if db.available():  # vẫn thử ghi (hàm helper sẽ queue nếu fail)
                db_set_kv_with_retry(db, "portfolio_meta", "holdings", _DATA_CACHE["portfolio"])
                db_set_kv_with_retry(db, "portfolio_meta", "avg_price", _DATA_CACHE["avg_prices"])
                db_set_kv_with_retry(db, "portfolio_meta", "last_write_ts", now_ts)
                # Cố gắng xử lý queue ngay nếu có thể
                db_retry_queue(db)
        except Exception as e:
            _APP_STATE["errors"].append(f"DB portfolio update error: {e}")

def update_price_cache(prices: Dict[str, Any], changes: Dict[str, Any]):
    """Update price caches (used by force refresh button)."""
    with _data_lock:
        _DATA_CACHE["prices"] = dict(prices)
        _DATA_CACHE["price_changes"] = dict(changes)
    _APP_STATE["last_api_sync"] = time.time()
    _APP_STATE["api_available"] = True

def force_reinitialize() -> Tuple[bool, str]:
    """Force a full re-initialization (stop background sync, reset state, re-run init)."""
    try:
        stop_background_sync()
        with _init_lock:
            # Reset essential state flags (preserve existing cached data for quick UI continuity)
            _APP_STATE["init_complete"] = False
            _APP_STATE["api_available"] = False
            _APP_STATE["db_available"] = False
        ok, msg = initialize_app(refresh=True)
        return ok, f"Force re-init: {msg}"
    except Exception as e:
        err = f"Force re-init error: {e}"
        _APP_STATE["errors"].append(err)
        return False, err

def rehydrate_from_db() -> bool:
    """Explicitly re-bootstrap from DB without re-running full init (used after reconnect or manual push)."""
    ok = _bootstrap_from_db()
    if ok:
        _APP_STATE["last_db_sync"] = time.time()
    return ok

def stop_background_sync():
    """Stop background synchronization."""
    _APP_STATE["background_sync_active"] = False