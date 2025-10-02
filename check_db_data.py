from pymongo import MongoClient
import os

def check_data():
    # Lấy thông tin kết nối từ biến môi trường
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")

    if not mongo_uri:
        print("MONGO_URI chưa được thiết lập trong biến môi trường.")
        return

    try:
        # Kết nối tới MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]

        # Kiểm tra dữ liệu trong collection btc_whale_history
        print("\n--- Lịch sử giao dịch BTC (btc_whale_history) ---")
        for doc in db["btc_whale_history"].find():
            print(doc)

        # Kiểm tra block cuối cùng đã xử lý
        print("\n--- Block cuối cùng đã xử lý (btc_meta) ---")
        last_block = db["btc_meta"].find_one({"_id": "last_block"})
        print(last_block)

        # Kiểm tra log giao dịch
        print("\n--- Log giao dịch (btc_logs) ---")
        for log in db["btc_logs"].find():
            print(log)

    except Exception as e:
        print(f"Lỗi khi kết nối tới MongoDB: {e}")

if __name__ == "__main__":
    check_data()