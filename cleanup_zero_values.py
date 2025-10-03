"""Cleanup script: remove noisy portfolio_history documents with value = 0.

Usage (PowerShell):
  python cleanup_zero_values.py --uri "<MONGO_URI>" --db Crypto2025 --collection portfolio_history --dry-run
  python cleanup_zero_values.py --uri "<MONGO_URI>" --db Crypto2025 --collection portfolio_history

Features:
- Dry-run mode shows how many docs would be deleted and sample ids.
- Batched deletion to avoid large single write load.
- Optional filter refinement (total-only, per-coin only, time range).
- Automatic backup export (optional) before deletion.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from typing import Any, Dict
from datetime import datetime

try:
    from pymongo import MongoClient
except ImportError:
    print("pymongo chưa được cài. Cài bằng: pip install pymongo", file=sys.stderr)
    sys.exit(1)


def build_filter(include_string_zero: bool, only_coin: bool, only_total: bool,
                 since: int | None, until: int | None) -> Dict[str, Any]:
    conditions = []
    # numeric zero
    conditions.append({'value': 0})
    if include_string_zero:
        conditions.append({'value': {'$in': ['0', '0.0', '0.00']}})
    base = {'$or': conditions} if len(conditions) > 1 else conditions[0]

    if only_coin and only_total:
        raise ValueError("Chỉ chọn một trong --only-coin hoặc --only-total, không phải cả hai")
    if only_coin:
        base = {'$and': [base, {'coin': {'$exists': True}}]}
    if only_total:
        base = {'$and': [base, {'coin': {'$exists': False}}]}
    time_range = []
    if since is not None:
        time_range.append({'timestamp': {'$gte': since}})
    if until is not None:
        time_range.append({'timestamp': {'$lte': until}})
    if time_range:
        base = {'$and': [base] + time_range}
    return base


def backup_subset(uri: str, db: str, collection: str, query: Dict[str, Any], backup_path: str):
    try:
        # Build mongoexport command (requires mongo tools installed)
        import json
        q_json = json.dumps(query)
        cmd = [
            'mongoexport', '--uri', uri, '--db', db, '--collection', collection,
            '--query', q_json, '--out', backup_path
        ]
        subprocess.run(cmd, check=True)
        print(f"[Backup] Đã export subset vào {backup_path}")
    except Exception as e:
        print(f"[Backup] Bỏ qua export (lỗi hoặc chưa cài mongoexport): {e}")


def main():
    parser = argparse.ArgumentParser(description="Xóa các bản ghi value = 0 khỏi collection portfolio_history")
    parser.add_argument('--uri', required=True, help='MongoDB URI (mongodb+srv://...)')
    parser.add_argument('--db', required=True, help='Database name, ví dụ Crypto2025')
    parser.add_argument('--collection', default='portfolio_history', help='Collection name')
    parser.add_argument('--batch-size', type=int, default=5000, help='Số doc xóa mỗi batch')
    parser.add_argument('--dry-run', action='store_true', help='Chỉ thống kê, không xóa')
    parser.add_argument('--include-string-zero', action='store_true', help='Bao gồm value dạng chuỗi "0", "0.0"')
    parser.add_argument('--only-coin', action='store_true', help='Chỉ xóa bản ghi có field coin')
    parser.add_argument('--only-total', action='store_true', help='Chỉ xóa bản ghi tổng (không có field coin)')
    parser.add_argument('--since', type=int, help='Chỉ xóa từ timestamp >= since (epoch seconds)')
    parser.add_argument('--until', type=int, help='Chỉ xóa đến timestamp <= until (epoch seconds)')
    parser.add_argument('--backup', action='store_true', help='Tạo file backup subset trước khi xóa (cần mongoexport)')
    args = parser.parse_args()

    filt = build_filter(args.include_string_zero, args.only_coin, args.only_total, args.since, args.until)
    print(f"Filter dùng để xóa: {filt}")

    client = MongoClient(args.uri)
    coll = client[args.db][args.collection]

    total = coll.count_documents(filt)
    print(f"Tổng số document match = {total}")
    if total == 0:
        print("Không có gì để xóa.")
        return

    sample = list(coll.find(filt, {'_id': 1, 'timestamp': 1, 'coin': 1, 'value': 1}).limit(5))
    print("Ví dụ 5 doc sẽ bị ảnh hưởng:")
    for s in sample:
        ts = s.get('timestamp')
        if isinstance(ts, int):
            try:
                ts_h = datetime.utcfromtimestamp(ts).isoformat()
            except Exception:
                ts_h = ts
        else:
            ts_h = ts
        print(f"  _id={s.get('_id')} coin={s.get('coin')} value={s.get('value')} ts={ts_h}")

    if args.backup:
        backup_subset(args.uri, args.db, args.collection, filt, f"backup_zero_values_{int(datetime.utcnow().timestamp())}.json")

    if args.dry_run:
        print("Dry-run: không xóa gì. Thoát.")
        return

    deleted = 0
    while True:
        # Lấy một batch _id để xóa (tránh long running delete lớn)
        ids = [d['_id'] for d in coll.find(filt, {'_id': 1}).limit(args.batch_size)]
        if not ids:
            break
        res = coll.delete_many({'_id': {'$in': ids}})
        deleted += res.deleted_count
        print(f"Đã xóa {res.deleted_count} (tổng {deleted}/{total})")
        if res.deleted_count == 0:
            break
    print(f"Hoàn thành. Đã xóa tổng cộng {deleted} doc.")


if __name__ == '__main__':
    main()
