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
    "price_changes": {}
}

# Thread locks for data safety
_data_lock = threading.Lock()
_init_lock = threading.Lock()

def get_app_state() -> Dict[str, Any]:
    """Get current application state for diagnostics."""
    return dict(_APP_STATE)

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
        # Portfolio data
        if os.path.exists("data.json"):
            with open("data.json", "r") as f:
                _DATA_CACHE["portfolio"] = json.load(f)
        
        # Average prices
        if os.path.exists("avg_price.json"):
            with open("avg_price.json", "r") as f:
                _DATA_CACHE["avg_prices"] = json.load(f)
        
        # History
        if os.path.exists("portfolio_history.json"):
            with open("portfolio_history.json", "r") as f:
                _DATA_CACHE["history"] = json.load(f)
        
        # Last prices
        if os.path.exists("last_prices.json"):
            with open("last_prices.json", "r") as f:
                data = json.load(f)
                _DATA_CACHE["prices"] = data.get("prices", {})
                _DATA_CACHE["price_changes"] = data.get("price_data", {})
        
        return True
    except Exception as e:
        _APP_STATE["errors"].append(f"Local file load error: {e}")
        return False

def _bootstrap_from_db() -> bool:
    """Bootstrap data from database with error handling."""
    try:
        from cloud_db import db
        
        # Debug connection info
        conn_info = db.get_connection_info()
        print(f"[DEBUG] DB connection info: {conn_info}")
        
        if not db.available():
            # Try force reconnect
            print("[DEBUG] DB not available, attempting force reconnect...")
            reconnect_success = db.force_reconnect()
            if reconnect_success:
                print("[DEBUG] Force reconnect successful!")
            else:
                error_msg = f"DB not available after reconnect. Info: {db.get_connection_info()}"
                _APP_STATE["errors"].append(error_msg)
                print(f"[DEBUG] {error_msg}")
                return False
        
        # Load portfolio metadata
        try:
            print("[DEBUG] Attempting to load portfolio metadata from DB...")
            holdings = db.get_kv("portfolio_meta", "holdings") or {}
            avg_prices = db.get_kv("portfolio_meta", "avg_price") or {}
            
            print(f"[DEBUG] Loaded from DB - Holdings: {len(holdings)} items")
            print(f"[DEBUG] Loaded from DB - Avg Prices: {len(avg_prices)} items")
            
            if holdings:
                _DATA_CACHE["portfolio"] = holdings
                print(f"[DEBUG] Updated portfolio cache with {len(holdings)} holdings")
                # Backup to local file
                with open("data.json", "w") as f:
                    json.dump(holdings, f)
                print("[DEBUG] Saved holdings to data.json")
            
            if avg_prices:
                _DATA_CACHE["avg_prices"] = avg_prices
                print(f"[DEBUG] Updated avg_prices cache with {len(avg_prices)} prices")
                # Backup to local file
                with open("avg_price.json", "w") as f:
                    json.dump(avg_prices, f)
                print("[DEBUG] Saved avg_prices to avg_price.json")
        
        except Exception as e:
            _APP_STATE["errors"].append(f"DB portfolio meta load error: {e}")
        
        # Load portfolio history
        try:
            history = db.find_all("portfolio_history", sort_field="timestamp", ascending=True)
            if history:
                _DATA_CACHE["history"] = history
                # Backup to local file
                with open("portfolio_history.json", "w") as f:
                    json.dump(history, f)
        
        except Exception as e:
            _APP_STATE["errors"].append(f"DB history load error: {e}")
        
        _APP_STATE["db_available"] = True
        _APP_STATE["last_db_sync"] = time.time()
        return True
        
    except Exception as e:
        _APP_STATE["errors"].append(f"DB bootstrap error: {e}")
        return False

def _init_api_services() -> bool:
    """Initialize API services with fallback handling."""
    try:
        # Initialize price cache
        from price_utils import init_price_cache
        init_price_cache()
        
        # Try to fetch initial prices
        from price_utils import fetch_prices_and_changes
        from config import COIN_LIST
        
        coins = [coin_id for coin_id, _ in COIN_LIST]
        prices, changes, success, msg = fetch_prices_and_changes(coins, force=True)
        
        if success:
            _DATA_CACHE["prices"] = prices
            _DATA_CACHE["price_changes"] = changes
            _APP_STATE["api_available"] = True
            _APP_STATE["last_api_sync"] = time.time()
            return True
        else:
            _APP_STATE["errors"].append(f"Initial API fetch failed: {msg}")
            return False
            
    except Exception as e:
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

def initialize_app() -> Tuple[bool, str]:
    """
    Initialize the application with robust error handling.
    
    Returns:
        (success, message)
    """
    with _init_lock:
        if _APP_STATE["init_complete"]:
            return True, "App already initialized"
        
        try:
            _APP_STATE["errors"].clear()
            
            # Step 1: Load local files as base
            local_loaded = _load_local_files()
            if local_loaded:
                _APP_STATE["data_loaded"] = True
            
            # Step 2: Try to bootstrap from DB
            db_loaded = _bootstrap_from_db()
            
            # Step 3: Initialize API services
            api_loaded = _init_api_services()
            
            # Step 4: Start background sync if any service is available
            if db_loaded or api_loaded:
                sync_thread = threading.Thread(target=_background_sync, daemon=True)
                sync_thread.start()
            
            _APP_STATE["init_complete"] = True
            
            # Generate status message
            sources = []
            if local_loaded:
                sources.append("local files")
            if db_loaded:
                sources.append("database")
            if api_loaded:
                sources.append("API")
            
            if sources:
                return True, f"App initialized successfully from: {', '.join(sources)}"
            else:
                return False, "App initialization failed - no data sources available"
                
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
    """Update portfolio data safely."""
    with _data_lock:
        _DATA_CACHE["portfolio"].update(portfolio)
        _DATA_CACHE["avg_prices"].update(avg_prices)
    
    # Persist to local files
    try:
        with open("data.json", "w") as f:
            json.dump(_DATA_CACHE["portfolio"], f)
        with open("avg_price.json", "w") as f:
            json.dump(_DATA_CACHE["avg_prices"], f)
    except Exception as e:
        _APP_STATE["errors"].append(f"Local save error: {e}")
    
    # Update DB if available
    if _APP_STATE["db_available"]:
        try:
            from cloud_db import db
            if db.available():
                db.set_kv("portfolio_meta", "holdings", _DATA_CACHE["portfolio"])
                db.set_kv("portfolio_meta", "avg_price", _DATA_CACHE["avg_prices"])
        except Exception as e:
            _APP_STATE["errors"].append(f"DB portfolio update error: {e}")

def stop_background_sync():
    """Stop background synchronization."""
    _APP_STATE["background_sync_active"] = False