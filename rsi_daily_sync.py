"""
RSI Daily Sync Module - Long-term Historical Storage

Syncs RSI data ONCE per day to:
1. MongoDB rsi_history collection (long-term storage, 1 year+)
2. CSV backup files (local redundancy)

Unlike rsi_sync.py (15-minute current data), this stores historical snapshots.

Collection structure:
- Collection: rsi_history
- Document: {
    "symbol": "BTC",
    "timeframe": "1d",
    "timestamp": "2025-10-29T00:00:00Z",  # Daily snapshot timestamp
    "rsi": 65.3,
    "close_price": 68500.0,
    "volume_24h": 35000000000
  }

CSV structure:
- File: rsi_history_1d.csv
- Columns: timestamp,symbol,timeframe,rsi,close_price,volume_24h
"""
from __future__ import annotations

import time
import threading
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv

# Sync configuration
DAILY_SYNC_HOUR = 0  # Sync at midnight UTC
SUPPORTED_TIMEFRAMES = ["1d", "4h"]  # Focus on daily and 4h for historical analysis
DEFAULT_UNIVERSE = "top50"
CSV_DIR = Path(".")  # CSV files stored in project root

# Thread-safe state
_daily_sync_thread = None
_daily_sync_running = False
_daily_sync_lock = threading.Lock()
_last_daily_sync = None
_daily_sync_errors = []


def get_daily_sync_status() -> Dict[str, Any]:
    """Get current daily sync status."""
    with _daily_sync_lock:
        return {
            "running": _daily_sync_running,
            "last_sync": _last_daily_sync,
            "errors": _daily_sync_errors[-10:],
            "sync_hour_utc": DAILY_SYNC_HOUR,
            "timeframes": SUPPORTED_TIMEFRAMES,
            "csv_dir": str(CSV_DIR)
        }


def _log_error(msg: str):
    """Thread-safe error logging."""
    with _daily_sync_lock:
        _daily_sync_errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": msg
        })
        if len(_daily_sync_errors) > 10:
            _daily_sync_errors.pop(0)
    print(f"[RSI Daily Sync Error] {msg}")


def save_rsi_to_db_history(symbol: str, timeframe: str, timestamp: datetime, rsi: float, close_price: float = 0.0, volume_24h: float = 0.0) -> bool:
    """
    Save a single RSI snapshot to MongoDB rsi_history collection.
    
    Uses upsert to avoid duplicates (based on symbol + timeframe + timestamp).
    """
    try:
        from cloud_db import db
        
        if not db.available():
            print(f"[RSI Daily] DB not available")
            return False
        
        collection = db.get_collection("rsi_history")
        
        doc = {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "timestamp": timestamp.isoformat(),
            "rsi": float(rsi),
            "close_price": float(close_price),
            "volume_24h": float(volume_24h)
        }
        
        # Upsert to avoid duplicates
        collection.update_one(
            {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "timestamp": timestamp.isoformat()
            },
            {"$set": doc},
            upsert=True
        )
        
        return True
        
    except Exception as e:
        _log_error(f"Failed to save {symbol} to DB: {e}")
        return False


def append_rsi_to_csv(symbol: str, timeframe: str, timestamp: datetime, rsi: float, close_price: float = 0.0, volume_24h: float = 0.0) -> bool:
    """
    Append RSI snapshot to CSV file.
    
    CSV file: rsi_history_{timeframe}.csv
    Creates file with header if not exists.
    """
    try:
        csv_path = CSV_DIR / f"rsi_history_{timeframe}.csv"
        
        # Check if file exists
        file_exists = csv_path.exists()
        
        # Open in append mode
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header if new file
            if not file_exists:
                writer.writerow(['timestamp', 'symbol', 'timeframe', 'rsi', 'close_price', 'volume_24h'])
            
            # Write data row
            writer.writerow([
                timestamp.isoformat(),
                symbol.upper(),
                timeframe,
                f"{rsi:.2f}",
                f"{close_price:.2f}",
                f"{volume_24h:.2f}"
            ])
        
        return True
        
    except Exception as e:
        _log_error(f"Failed to append {symbol} to CSV: {e}")
        return False


def sync_rsi_daily_snapshot(timeframe: str = "1d") -> bool:
    """
    Take a daily snapshot of RSI for all tracked coins.
    
    This function:
    1. Fetches current RSI for all coins in universe
    2. Saves each to MongoDB rsi_history collection
    3. Appends each to CSV backup file
    
    Called once per day at midnight UTC.
    """
    try:
        print(f"[RSI Daily] Starting daily snapshot for {timeframe}...")
        
        # Get universe
        import metrics_rsi as _rsi
        list_meta = _rsi.get_universe_from_config(option=DEFAULT_UNIVERSE)
        
        if not list_meta:
            _log_error(f"Failed to get universe for daily snapshot")
            return False
        
        df_meta = pd.DataFrame(list_meta)
        symbols = df_meta['symbol'].tolist()
        
        print(f"[RSI Daily] Fetching RSI for {len(symbols)} coins...")
        
        # Fetch current RSI (force fresh calculation)
        rsi_map = _rsi.get_rsi_for_universe(
            symbols,
            timeframe=timeframe,
            ttl_seconds=0,
            force_refresh=True,
            with_history=False
        )
        
        # Get current prices for additional context
        from price_utils import fetch_prices_for_ids
        coin_ids = df_meta['id'].tolist()
        price_map = fetch_prices_for_ids(coin_ids)
        
        # Create timestamp for this snapshot (round to nearest day)
        snapshot_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        success_count = 0
        
        for idx, row in df_meta.iterrows():
            symbol = row['symbol']
            coin_id = row['id']
            
            rsi = rsi_map.get(symbol)
            if rsi is None:
                continue
            
            # Get price and volume
            price_data = price_map.get(coin_id, {})
            close_price = price_data.get('usd', 0.0)
            volume_24h = price_data.get('usd_24h_vol', 0.0)
            
            # Save to DB
            db_ok = save_rsi_to_db_history(symbol, timeframe, snapshot_time, rsi, close_price, volume_24h)
            
            # Append to CSV
            csv_ok = append_rsi_to_csv(symbol, timeframe, snapshot_time, rsi, close_price, volume_24h)
            
            if db_ok or csv_ok:
                success_count += 1
        
        print(f"[RSI Daily] ✅ Snapshot complete: {success_count}/{len(symbols)} coins saved")
        
        with _daily_sync_lock:
            global _last_daily_sync
            _last_daily_sync = datetime.now(timezone.utc).isoformat()
        
        return success_count > 0
        
    except Exception as e:
        _log_error(f"Daily snapshot failed for {timeframe}: {e}")
        import traceback
        traceback.print_exc()
        return False


def _daily_sync_worker():
    """
    Background worker that syncs RSI daily snapshots.
    
    Runs once per day at midnight UTC.
    """
    global _daily_sync_running
    
    print("[RSI Daily] Daily snapshot worker started")
    
    while _daily_sync_running:
        try:
            now = datetime.now(timezone.utc)
            
            # Calculate next sync time (midnight UTC)
            next_sync = now.replace(hour=DAILY_SYNC_HOUR, minute=0, second=0, microsecond=0)
            
            # If we've passed today's sync time, schedule for tomorrow
            if now >= next_sync:
                next_sync += timedelta(days=1)
            
            # Calculate seconds until next sync
            wait_seconds = (next_sync - now).total_seconds()
            
            print(f"[RSI Daily] Next snapshot at {next_sync.isoformat()} (in {wait_seconds/3600:.1f} hours)")
            
            # Wait until next sync time (check every minute to allow graceful shutdown)
            while _daily_sync_running and datetime.now(timezone.utc) < next_sync:
                time.sleep(60)  # Check every minute
            
            if not _daily_sync_running:
                break
            
            # Perform daily snapshot for all timeframes
            for tf in SUPPORTED_TIMEFRAMES:
                if not _daily_sync_running:
                    break
                sync_rsi_daily_snapshot(tf)
                time.sleep(5)  # Small delay between timeframes
            
        except Exception as e:
            _log_error(f"Daily worker error: {e}")
            time.sleep(3600)  # Wait 1 hour on error


def start_daily_sync():
    """Start the background daily RSI snapshot thread."""
    global _daily_sync_thread, _daily_sync_running
    
    with _daily_sync_lock:
        if _daily_sync_running:
            print("[RSI Daily] Daily sync already running")
            return
        
        _daily_sync_running = True
    
    _daily_sync_thread = threading.Thread(target=_daily_sync_worker, daemon=True, name="RSIDailySync")
    _daily_sync_thread.start()
    print("[RSI Daily] ✅ Daily snapshot sync started (runs at midnight UTC)")


def stop_daily_sync():
    """Stop the background daily RSI snapshot thread."""
    global _daily_sync_running
    
    with _daily_sync_lock:
        if not _daily_sync_running:
            return
        _daily_sync_running = False
    
    print("[RSI Daily] Stopping daily sync...")
    if _daily_sync_thread:
        _daily_sync_thread.join(timeout=5)
    print("[RSI Daily] ✅ Stopped")


def force_daily_sync_now():
    """Force an immediate daily snapshot (blocking call)."""
    print("[RSI Daily] Force daily snapshot requested...")
    
    success_count = 0
    for tf in SUPPORTED_TIMEFRAMES:
        if sync_rsi_daily_snapshot(tf):
            success_count += 1
    
    print(f"[RSI Daily] Force snapshot complete: {success_count}/{len(SUPPORTED_TIMEFRAMES)} timeframes synced")
    return success_count > 0


def cleanup_old_csv_data(days_to_keep: int = 400):
    """
    Clean up old CSV data to prevent file bloat.
    
    Keeps only last N days of data.
    """
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        for tf in SUPPORTED_TIMEFRAMES:
            csv_path = CSV_DIR / f"rsi_history_{tf}.csv"
            
            if not csv_path.exists():
                continue
            
            # Read CSV
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filter to recent data
            df_recent = df[df['timestamp'] >= cutoff_date]
            
            # Save back
            df_recent.to_csv(csv_path, index=False)
            
            removed_count = len(df) - len(df_recent)
            print(f"[RSI Daily] Cleaned {csv_path.name}: removed {removed_count} old records")
        
        return True
        
    except Exception as e:
        _log_error(f"CSV cleanup failed: {e}")
        return False
