from pymongo import MongoClient
from redis import Redis
import os
import json

# Kết nối Redis
redis_uri = os.getenv("REDIS_URI", "redis://localhost:6379/0")
redis_client = Redis.from_url(redis_uri)

# Định nghĩa các biến toàn cục
mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")

def get_from_cache_or_db(collection_name, query, cache_key):
    """Kiểm tra Redis cache trước khi truy vấn MongoDB."""
    cached_data = redis_client.get(cache_key)
    if cached_data:
        print(f"Dữ liệu được lấy từ Redis cache: {cache_key}")
        return json.loads(cached_data)

    # Nếu không có trong cache, truy vấn MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    data = list(collection.find(query))

    # Lưu kết quả vào Redis cache
    redis_client.set(cache_key, json.dumps(data, default=str), ex=3600)  # Cache 1 giờ
    print(f"Dữ liệu được lưu vào Redis cache: {cache_key}")
    return data

def check_data():
    # Lấy thông tin kết nối từ biến môi trường
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")

    if not mongo_uri:
        print("MONGO_URI chưa được thiết lập trong biến môi trường.")
        return

    try:
        # Kiểm tra dữ liệu trong collection btc_whale_history
        print("\n--- Lịch sử giao dịch BTC (btc_whale_history) ---")
        btc_whale_history = get_from_cache_or_db("btc_whale_history", {}, "btc_whale_history_cache")
        for doc in btc_whale_history:
            print(doc)

        # Kiểm tra block cuối cùng đã xử lý
        print("\n--- Block cuối cùng đã xử lý (btc_meta) ---")
        btc_meta = get_from_cache_or_db("btc_meta", {"_id": "last_block"}, "btc_meta_last_block_cache")
        print(btc_meta)

        # Kiểm tra log giao dịch
        print("\n--- Log giao dịch (btc_logs) ---")
        btc_logs = get_from_cache_or_db("btc_logs", {}, "btc_logs_cache")
        for log in btc_logs:
            print(log)

    except Exception as e:
        print(f"Lỗi khi kết nối tới MongoDB: {e}")

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