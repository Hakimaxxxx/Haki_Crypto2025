import json

HISTORY_FILE = "btc_whale_alert_history.json"

def remove_self_transfer():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        print("Không thể đọc file history.")
        return
    new_history = [tx for tx in history if tx.get("from") != tx.get("to")]
    print(f"Đã loại bỏ {len(history) - len(new_history)} transaction tự chuyển (from == to)")
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(new_history, f, ensure_ascii=False, indent=2)
        print("Đã cập nhật lại file history.")
    except Exception:
        print("Không thể ghi lại file history.")

if __name__ == "__main__":
    remove_self_transfer()
