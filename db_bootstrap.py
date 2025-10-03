import json
import os
from cloud_db import db

PORTFOLIO_HISTORY_FILE = "portfolio_history.json"
DATA_FILE = "data.json"
AVG_PRICE_FILE = "avg_price.json"


def bootstrap_from_cloud():
    """Tải dữ liệu từ Cloud DB xuống local nếu có."""
    if not db.available():
        return False, "DB không khả dụng khi bootstrap"
    changed = False
    try:
        kv_hold = db.get_kv("portfolio_meta", "holdings") or {}
        kv_avg = db.get_kv("portfolio_meta", "avg_price") or {}
        if kv_hold:
            try:
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(kv_hold, f)
                changed = True
            except Exception:
                pass
        if kv_avg:
            try:
                with open(AVG_PRICE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(kv_avg, f)
                changed = True
            except Exception:
                pass
        hist_docs = db.find_all("portfolio_history", sort_field="timestamp", ascending=True)
        if hist_docs:
            try:
                with open(PORTFOLIO_HISTORY_FILE, 'w', encoding='utf-8') as f:
                    json.dump(hist_docs, f)
                changed = True
            except Exception:
                pass
        return changed, "Bootstrap thành công" if changed else "Không có thay đổi khi bootstrap"
    except Exception as e:
        return False, f"Lỗi bootstrap: {e}"
