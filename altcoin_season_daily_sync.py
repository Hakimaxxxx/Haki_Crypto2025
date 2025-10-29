"""
Altcoin Season Index - Daily Snapshot Sync

Syncs Altcoin Season Index ONCE per day to:
1. MongoDB altcoin_season_history collection (long-term storage)
2. CSV backup file (local redundancy)

Unlike the 1-hour cache in metrics_altcoin_season.py, this stores daily snapshots
for historical analysis and timeline charts (1 year+ of data).

Collection structure:
- Collection: altcoin_season_history
- Document: {
    "timestamp": "2025-10-29T00:00:00Z",
    "index_value": 65.3,
    "outperforming_count": 65,
    "total_count": 100,
    "btc_performance_90d": 12.5,
    "top_performers": [...],
    "worst_performers": [...]
  }

CSV structure:
- File: altcoin_season_history.csv
- Columns: timestamp,index_value,outperforming_count,total_count,btc_performance_90d
"""
from __future__ import annotations

import time
import threading
import pandas as pd
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv

# Sync configuration
DAILY_SYNC_HOUR = 1  # Sync at 1 AM UTC (avoid midnight conflicts)
CSV_FILE = Path("altcoin_season_history.csv")

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
            "csv_file": str(CSV_FILE)
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
    print(f"[Altcoin Season Daily] Error: {msg}")


def save_to_db_history(timestamp: datetime, index_value: float, details: Dict) -> bool:
    """
    Save a single Altcoin Season Index snapshot to MongoDB.
    
    Uses upsert to avoid duplicates (based on timestamp date).
    """
    try:
        from cloud_db import db
        
        if not db.available():
            print(f"[Altcoin Season Daily] DB not available")
            return False
        
        collection = db.get_collection("altcoin_season_history")
        
        # Round timestamp to day (to avoid duplicate snapshots)
        snapshot_time = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        
        doc = {
            "timestamp": snapshot_time.isoformat(),
            "index_value": float(index_value),
            "outperforming_count": details.get('altcoins_outperforming', 0),
            "total_count": details.get('altcoins_total', 100),
            "btc_performance_90d": details.get('btc_performance_90d', 0.0),
            "top_performers": details.get('top_performers', [])[:5],  # Top 5
            "worst_performers": details.get('worst_performers', [])[:5]  # Worst 5
        }
        
        # Upsert to avoid duplicates
        collection.update_one(
            {"timestamp": snapshot_time.isoformat()},
            {"$set": doc},
            upsert=True
        )
        
        print(f"[Altcoin Season Daily] ✅ Saved to DB: {index_value:.1f}")
        return True
        
    except Exception as e:
        _log_error(f"Failed to save to DB: {e}")
        return False


def append_to_csv(timestamp: datetime, index_value: float, details: Dict) -> bool:
    """
    Append Altcoin Season Index snapshot to CSV file.
    
    Creates file with header if not exists.
    """
    try:
        # Check if file exists
        file_exists = CSV_FILE.exists()
        
        # Round timestamp to day
        snapshot_time = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Open in append mode
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header if new file
            if not file_exists:
                writer.writerow([
                    'timestamp',
                    'index_value',
                    'outperforming_count',
                    'total_count',
                    'btc_performance_90d'
                ])
            
            # Write data row
            writer.writerow([
                snapshot_time.isoformat(),
                f"{index_value:.2f}",
                details.get('altcoins_outperforming', 0),
                details.get('altcoins_total', 50),
                f"{details.get('btc_performance_90d', 0.0):.2f}"
            ])
        
        print(f"[Altcoin Season Daily] ✅ Appended to CSV")
        return True
        
    except Exception as e:
        _log_error(f"Failed to append to CSV: {e}")
        return False


def sync_altcoin_season_snapshot() -> bool:
    """
    Take a daily snapshot of Altcoin Season Index.
    
    This function:
    1. Calculates current Altcoin Season Index (90-day analysis)
    2. Saves to MongoDB altcoin_season_history collection
    3. Appends to CSV backup file
    
    Called once per day at 1 AM UTC.
    """
    try:
        print(f"[Altcoin Season Daily] Starting daily snapshot...")
        
        # Import the calculation function
        from metrics_altcoin_season import fetch_altcoin_season_index
        
        # Calculate index (this takes 2-3 minutes due to API rate limits)
        print(f"[Altcoin Season Daily] Calculating index (may take 2-3 min)...")
        index_value, details, success = fetch_altcoin_season_index()
        
        if not success:
            _log_error("Failed to calculate Altcoin Season Index")
            return False
        
        print(f"[Altcoin Season Daily] Index calculated: {index_value:.1f}")
        
        # Create timestamp for this snapshot
        snapshot_time = datetime.now(timezone.utc)
        
        # Save to DB
        db_ok = save_to_db_history(snapshot_time, index_value, details)
        
        # Append to CSV
        csv_ok = append_to_csv(snapshot_time, index_value, details)
        
        if db_ok or csv_ok:
            with _daily_sync_lock:
                global _last_daily_sync
                _last_daily_sync = datetime.now(timezone.utc).isoformat()
            
            print(f"[Altcoin Season Daily] ✅ Snapshot complete: Index {index_value:.1f}")
            return True
        else:
            _log_error("Both DB and CSV saves failed")
            return False
        
    except Exception as e:
        _log_error(f"Snapshot failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _daily_sync_worker():
    """
    Background worker that syncs Altcoin Season Index daily.
    
    Runs once per day at 1 AM UTC.
    """
    global _daily_sync_running
    
    print("[Altcoin Season Daily] Daily snapshot worker started")
    
    while _daily_sync_running:
        try:
            now = datetime.now(timezone.utc)
            
            # Calculate next sync time (1 AM UTC)
            next_sync = now.replace(hour=DAILY_SYNC_HOUR, minute=0, second=0, microsecond=0)
            
            # If we've passed today's sync time, schedule for tomorrow
            if now >= next_sync:
                next_sync += timedelta(days=1)
            
            # Calculate seconds until next sync
            wait_seconds = (next_sync - now).total_seconds()
            
            print(f"[Altcoin Season Daily] Next snapshot at {next_sync.isoformat()} (in {wait_seconds/3600:.1f} hours)")
            
            # Wait until next sync time (check every minute to allow graceful shutdown)
            while _daily_sync_running and datetime.now(timezone.utc) < next_sync:
                time.sleep(60)  # Check every minute
            
            if not _daily_sync_running:
                break
            
            # Perform daily snapshot
            sync_altcoin_season_snapshot()
            
        except Exception as e:
            _log_error(f"Daily worker error: {e}")
            time.sleep(3600)  # Wait 1 hour on error


def start_daily_sync():
    """Start the background daily Altcoin Season snapshot thread."""
    global _daily_sync_thread, _daily_sync_running
    
    with _daily_sync_lock:
        if _daily_sync_running:
            print("[Altcoin Season Daily] Daily sync already running")
            return
        
        _daily_sync_running = True
    
    _daily_sync_thread = threading.Thread(target=_daily_sync_worker, daemon=True, name="AltcoinSeasonDailySync")
    _daily_sync_thread.start()
    print("[Altcoin Season Daily] ✅ Daily snapshot sync started (runs at 1 AM UTC)")


def stop_daily_sync():
    """Stop the background daily Altcoin Season snapshot thread."""
    global _daily_sync_running
    
    with _daily_sync_lock:
        if not _daily_sync_running:
            return
        _daily_sync_running = False
    
    print("[Altcoin Season Daily] Stopping daily sync...")
    if _daily_sync_thread:
        _daily_sync_thread.join(timeout=5)
    print("[Altcoin Season Daily] ✅ Stopped")


def force_daily_sync_now():
    """Force an immediate daily snapshot (blocking call)."""
    print("[Altcoin Season Daily] Force daily snapshot requested...")
    
    success = sync_altcoin_season_snapshot()
    
    if success:
        print(f"[Altcoin Season Daily] Force snapshot complete")
    else:
        print(f"[Altcoin Season Daily] Force snapshot failed")
    
    return success


def cleanup_old_csv_data(days_to_keep: int = 400):
    """
    Clean up old CSV data to prevent file bloat.
    
    Keeps only last N days of data.
    """
    try:
        if not CSV_FILE.exists():
            return True
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        # Read CSV
        df = pd.read_csv(CSV_FILE)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Filter to recent data
        df_recent = df[df['timestamp'] >= cutoff_date]
        
        # Save back
        df_recent.to_csv(CSV_FILE, index=False)
        
        removed_count = len(df) - len(df_recent)
        print(f"[Altcoin Season Daily] Cleaned CSV: removed {removed_count} old records")
        
        return True
        
    except Exception as e:
        _log_error(f"CSV cleanup failed: {e}")
        return False
