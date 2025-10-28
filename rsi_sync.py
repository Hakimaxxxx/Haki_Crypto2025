"""
RSI Background Sync Module

Automatically syncs RSI data to MongoDB Atlas every 15 minutes.
Supports multiple timeframes: 15m, 1h, 4h, 1d, 7d
"""
from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import json

# Sync configuration
SYNC_INTERVAL = 900  # 15 minutes in seconds
SUPPORTED_TIMEFRAMES = ["15m", "1h", "4h", "1d", "7d"]
DEFAULT_UNIVERSE = "top50"  # Default to top 50 coins

# Thread-safe state
_sync_thread = None
_sync_running = False
_sync_lock = threading.Lock()
_last_sync_time = {}  # Track last sync per timeframe
_sync_errors = []  # Last 10 errors


def get_sync_status() -> Dict[str, Any]:
    """Get current sync status for monitoring."""
    with _sync_lock:
        return {
            "running": _sync_running,
            "last_sync": _last_sync_time.copy(),
            "errors": _sync_errors[-10:],  # Last 10 errors
            "interval_minutes": SYNC_INTERVAL / 60,
            "timeframes": SUPPORTED_TIMEFRAMES
        }


def _log_error(msg: str):
    """Thread-safe error logging."""
    with _sync_lock:
        _sync_errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": msg
        })
        # Keep only last 10
        if len(_sync_errors) > 10:
            _sync_errors.pop(0)
    print(f"[RSI Sync Error] {msg}")


def _sync_rsi_to_db(timeframe: str) -> bool:
    """
    Fetch RSI data for all coins and save to MongoDB.
    
    Collection structure:
    - Collection: rsi_data
    - Document: {
        "timeframe": "4h",
        "symbol": "BTC",
        "rsi_current": 65.3,
        "rsi_history": [
            {"timestamp": "2025-10-28T10:00:00Z", "rsi": 63.2},
            {"timestamp": "2025-10-28T14:00:00Z", "rsi": 65.3},
            ...
        ],
        "market_cap": 1234567890,
        "last_updated": "2025-10-28T14:15:00Z"
    }
    """
    try:
        from cloud_db import db
        import metrics_rsi as _rsi
        
        if not db.available():
            _log_error(f"DB not available for {timeframe} sync")
            return False
        
        # Get universe of coins to track
        list_meta = _rsi.get_universe_from_config(option=DEFAULT_UNIVERSE)
        if not list_meta:
            _log_error(f"Failed to get universe for {timeframe}")
            return False
        
        import pandas as pd
        df_meta = pd.DataFrame(list_meta)
        symbols = df_meta['symbol'].tolist()
        
        print(f"[RSI Sync] Syncing {len(symbols)} coins for timeframe {timeframe}...")
        
        # Fetch current RSI values
        rsi_current_map = _rsi.get_rsi_for_universe(
            symbols, 
            timeframe=timeframe, 
            ttl_seconds=0,  # Force fresh fetch
            force_refresh=True,
            with_history=False
        )
        
        # Fetch RSI history
        rsi_history_map = _rsi.get_rsi_for_universe(
            symbols, 
            timeframe=timeframe, 
            ttl_seconds=0,  # Force fresh fetch
            force_refresh=True,
            with_history=True
        )
        
        # Prepare documents for bulk upsert
        documents = []
        now = datetime.now(timezone.utc)
        
        for idx, row in df_meta.iterrows():
            symbol = row['symbol']
            rsi_current = rsi_current_map.get(symbol)
            rsi_history = rsi_history_map.get(symbol)
            
            # Skip if no RSI data
            if rsi_current is None:
                continue
            
            # Convert history timestamps to ISO strings for MongoDB
            history_serializable = []
            if rsi_history and isinstance(rsi_history, list):
                for h in rsi_history:
                    if isinstance(h, dict) and 'timestamp' in h and 'rsi' in h:
                        ts = h['timestamp']
                        # Convert pandas Timestamp to datetime if needed
                        if hasattr(ts, 'isoformat'):
                            ts_str = ts.isoformat()
                        else:
                            ts_str = str(ts)
                        history_serializable.append({
                            "timestamp": ts_str,
                            "rsi": float(h['rsi'])
                        })
            
            doc = {
                "timeframe": timeframe,
                "symbol": symbol,
                "rsi_current": float(rsi_current),
                "rsi_history": history_serializable,
                "market_cap": float(row.get('market_cap_usd', 0) or 0),
                "last_updated": now.isoformat()
            }
            documents.append(doc)
        
        if not documents:
            _log_error(f"No valid RSI data to sync for {timeframe}")
            return False
        
        # Bulk upsert to MongoDB
        collection = db._db['rsi_data']
        success_count = 0
        
        for doc in documents:
            try:
                # Upsert based on timeframe + symbol
                collection.update_one(
                    {"timeframe": timeframe, "symbol": doc["symbol"]},
                    {"$set": doc},
                    upsert=True
                )
                success_count += 1
            except Exception as e:
                _log_error(f"Failed to upsert {doc['symbol']} ({timeframe}): {e}")
        
        with _sync_lock:
            _last_sync_time[timeframe] = now.isoformat()
        
        print(f"[RSI Sync] ✅ {timeframe}: {success_count}/{len(documents)} coins synced")
        return True
        
    except Exception as e:
        _log_error(f"Sync failed for {timeframe}: {e}")
        import traceback
        traceback.print_exc()
        return False


def _sync_worker():
    """Background worker that syncs RSI data every 15 minutes."""
    global _sync_running
    
    print("[RSI Sync] Background worker started")
    
    while _sync_running:
        try:
            # Sync all timeframes
            for tf in SUPPORTED_TIMEFRAMES:
                if not _sync_running:
                    break
                _sync_rsi_to_db(tf)
                # Small delay between timeframes to avoid rate limits
                time.sleep(5)
            
            # Wait for next sync cycle (15 minutes)
            if _sync_running:
                print(f"[RSI Sync] Sleeping for {SYNC_INTERVAL/60:.0f} minutes until next sync...")
                time.sleep(SYNC_INTERVAL)
                
        except Exception as e:
            _log_error(f"Sync worker error: {e}")
            time.sleep(60)  # Wait 1 minute on error before retry


def start_sync():
    """Start the background RSI sync thread."""
    global _sync_thread, _sync_running
    
    with _sync_lock:
        if _sync_running:
            print("[RSI Sync] Already running")
            return
        
        _sync_running = True
    
    _sync_thread = threading.Thread(target=_sync_worker, daemon=True, name="RSISync")
    _sync_thread.start()
    print("[RSI Sync] ✅ Background sync started (15-minute interval)")


def stop_sync():
    """Stop the background RSI sync thread."""
    global _sync_running
    
    with _sync_lock:
        if not _sync_running:
            return
        _sync_running = False
    
    print("[RSI Sync] Stopping background sync...")
    if _sync_thread:
        _sync_thread.join(timeout=5)
    print("[RSI Sync] ✅ Stopped")


def fetch_rsi_from_db(timeframe: str, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch RSI data from MongoDB.
    
    Args:
        timeframe: RSI timeframe (15m, 1h, 4h, 1d, 7d)
        symbols: Optional list of symbols to fetch (None = fetch all)
    
    Returns:
        Dict mapping symbol -> {
            "rsi_current": float,
            "rsi_history": List[Dict],
            "market_cap": float,
            "last_updated": str
        }
    """
    try:
        from cloud_db import db
        
        if not db.available():
            return {}
        
        collection = db._db['rsi_data']
        
        # Build query
        query = {"timeframe": timeframe}
        if symbols:
            query["symbol"] = {"$in": symbols}
        
        # Fetch documents
        cursor = collection.find(query)
        
        result = {}
        for doc in cursor:
            symbol = doc.get("symbol")
            if symbol:
                result[symbol] = {
                    "rsi_current": doc.get("rsi_current"),
                    "rsi_history": doc.get("rsi_history", []),
                    "market_cap": doc.get("market_cap", 0),
                    "last_updated": doc.get("last_updated")
                }
        
        return result
        
    except Exception as e:
        _log_error(f"Failed to fetch from DB ({timeframe}): {e}")
        return {}


def force_sync_now():
    """Force an immediate sync of all timeframes (blocking call)."""
    print("[RSI Sync] Force sync requested...")
    success_count = 0
    
    for tf in SUPPORTED_TIMEFRAMES:
        if _sync_rsi_to_db(tf):
            success_count += 1
    
    print(f"[RSI Sync] Force sync complete: {success_count}/{len(SUPPORTED_TIMEFRAMES)} timeframes synced")
    return success_count > 0
