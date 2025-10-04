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

from pymongo import MongoClient
import json
def check_data_portfolio():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["portfolio_history"]

    data = list(collection.find({}))
    with open("portfolio_history_DB_fetch.json", "w") as f:
        json.dump(data, f, default=str)


def import_portfolio_history():
    import json
    from pymongo import MongoClient
    # Thay đổi thông tin kết nối
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")

    with open("d:\\Crypto\\portfolio_history_DB.json", "r", encoding="utf-8") as f:
        data = json.load(f)  # Nếu là JSON array
        # Nếu là NDJSON, dùng: data = [json.loads(line) for line in f if line.strip()]

    # Kết nối tới MongoDB và xác định collection
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["portfolio_history"]

    collection.insert_many(data)

    print("Import thành công!")

if __name__ == "__main__":
    check_data()
    #check_data_portfolio()
    #import_portfolio_history()