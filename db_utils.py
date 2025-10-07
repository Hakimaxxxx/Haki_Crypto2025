import os
import shutil
import time
import json

def validate_portfolio_docs(docs: list) -> list:
    required_keys = {"timestamp", "value"}
    valid_docs = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if not required_keys.issubset(doc.keys()):
            continue
        if not isinstance(doc["timestamp"], int):
            continue
        if not isinstance(doc["value"], (int, float)):
            continue
        valid_docs.append(doc)
    return valid_docs

_db_write_queue = []
# Queue for key-value writes: list of (time_added, collection, key, value)
_db_kv_queue = []
_db_last_retry = 0
_db_retry_interval = 30  # giây
_db_backoff_multiplier = 2
_db_max_retry_interval = 600  # 10 phút
_db_consecutive_failures = 0
_DB_QUEUE_MAX = 5000  # tránh nở vô hạn bộ nhớ

def get_db_queue_info():
    """Return dict with queue diagnostics for health panel."""
    next_retry_in = max(0, int(_db_retry_interval - (time.time() - _db_last_retry))) if (_db_write_queue or _db_kv_queue) else 0
    return {
        "queue_length": len(_db_write_queue),
        "kv_queue_length": len(_db_kv_queue),
        "consecutive_failures": _db_consecutive_failures,
        "retry_interval": _db_retry_interval,
        "next_retry_in": next_retry_in,
    }

def db_upsert_portfolio_docs_with_retry(db, docs: list):
    docs = validate_portfolio_docs(docs)
    if not docs:
        return
    global _db_write_queue, _db_last_retry, _db_consecutive_failures, _db_retry_interval
    try:
        if db.available():
            db.upsert_many("portfolio_history", docs, unique_keys=["timestamp", "coin"])
            _db_consecutive_failures = 0
            _db_retry_interval = 30
            return
        else:
            raise Exception("DB not available")
    except Exception as e:
        # Giới hạn độ dài queue
        if len(_db_write_queue) >= _DB_QUEUE_MAX:
            # Bỏ bớt bản ghi cũ nhất (FIFO) để tránh tràn bộ nhớ
            _db_write_queue.pop(0)
        _db_write_queue.append((time.time(), docs))
        _db_consecutive_failures += 1
        # Tăng backoff nhưng không vượt quá max
        _db_retry_interval = min(_db_retry_interval * _db_backoff_multiplier, _db_max_retry_interval)
        if _db_consecutive_failures % 10 == 1:
            print(f"[DB] Lỗi ghi (x{_db_consecutive_failures}), queue={len(_db_write_queue)}, next retry interval={_db_retry_interval}s: {e}")

def db_retry_queue(db):
    global _db_write_queue, _db_kv_queue, _db_last_retry, _db_consecutive_failures, _db_retry_interval
    now = time.time()
    if not (_db_write_queue or _db_kv_queue):
        return
    if not db.available():
        return
    if now - _db_last_retry <= _db_retry_interval:
        return
    # Retry theo batch nhỏ để tránh tạo áp lực
    success_any = False
    # 1. Handle history upserts first
    if _db_write_queue:
        batch_upsert = list(_db_write_queue)[:50]
        for ts, docs in batch_upsert:
            try:
                db.upsert_many("portfolio_history", docs, unique_keys=["timestamp", "coin"])
                _db_write_queue.remove((ts, docs))
                success_any = True
            except Exception as e:
                print(f"[DB] Retry ghi thất bại batch item: {e}")
                break
    # 2. Then process kv queue
    if _db_kv_queue and db.available():
        batch_kv = list(_db_kv_queue)[:100]
        for ts, coll, key, value in batch_kv:
            try:
                db.set_kv(coll, key, value)
                _db_kv_queue.remove((ts, coll, key, value))
                success_any = True
            except Exception as e:
                print(f"[DB] Retry KV thất bại: {coll}:{key} err={e}")
                break
    _db_last_retry = now
    if success_any:
        _db_consecutive_failures = 0
        _db_retry_interval = 30
        print(f"[DB] Retry thành công: history_queue={len(_db_write_queue)}, kv_queue={len(_db_kv_queue)}")

def db_set_kv_with_retry(db, collection: str, key: str, value):
    """Reliable set_kv with queue & backoff.

    Nếu DB không available hoặc set_kv lỗi sẽ đưa vào _db_kv_queue.
    """
    global _db_kv_queue, _db_consecutive_failures, _db_retry_interval
    try:
        if db.available():
            db.set_kv(collection, key, value)
            # Reset failure state on success
            _db_consecutive_failures = 0
            _db_retry_interval = 30
            return True
        else:
            raise Exception("DB not available")
    except Exception as e:
        if len(_db_kv_queue) >= _DB_QUEUE_MAX:
            _db_kv_queue.pop(0)
        _db_kv_queue.append((time.time(), collection, key, value))
        _db_consecutive_failures += 1
        _db_retry_interval = min(_db_retry_interval * _db_backoff_multiplier, _db_max_retry_interval)
        if _db_consecutive_failures % 10 == 1:
            print(f"[DB] Lỗi set_kv (x{_db_consecutive_failures}) queued={len(_db_kv_queue)} retry={_db_retry_interval}s: {e}")
        return False

def save_portfolio_history_optimized(history, file_path="portfolio_history.json"):
    old = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                old = json.load(f)
        except Exception:
            old = []
    new_entries = [h for h in history if h not in old]
    if new_entries:
        all_entries = old + new_entries
        with open(file_path, "w") as f:
            json.dump(all_entries, f)
        print(f"[File] Đã ghi {len(new_entries)} bản ghi mới vào {file_path}")
    else:
        print(f"[File] Không có bản ghi mới để ghi vào {file_path}")

def backup_file(file_path, backup_dir="backups"):
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(file_path)
    backup_path = os.path.join(backup_dir, f"{base}.{ts}.bak")
    try:
        shutil.copy2(file_path, backup_path)
        print(f"[Backup] Đã backup {file_path} -> {backup_path}")
    except Exception as e:
        print(f"[Backup] Lỗi backup {file_path}: {e}")
