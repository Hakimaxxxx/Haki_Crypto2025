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
_db_last_retry = 0
_db_retry_interval = 60  # giây

def db_upsert_portfolio_docs_with_retry(db, docs: list):
    docs = validate_portfolio_docs(docs)
    if not docs:
        return
    global _db_write_queue, _db_last_retry
    try:
        if db.available():
            db.upsert_many("portfolio_history", docs, unique_keys=["timestamp", "coin"])
            return
        else:
            raise Exception("DB not available")
    except Exception as e:
        _db_write_queue.append((time.time(), docs))
        print(f"[DB] Lỗi ghi, đã lưu vào queue: {e}")

def db_retry_queue(db):
    global _db_write_queue, _db_last_retry
    now = time.time()
    if _db_write_queue and db.available() and now - _db_last_retry > _db_retry_interval:
        for ts, docs in list(_db_write_queue):
            try:
                db.upsert_many("portfolio_history", docs, unique_keys=["timestamp", "coin"])
                _db_write_queue.remove((ts, docs))
                print(f"[DB] Đã retry ghi thành công docs lúc {ts}")
            except Exception as e:
                print(f"[DB] Retry ghi thất bại: {e}")
        _db_last_retry = now

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
