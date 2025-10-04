import os
os.environ['MONGO_URI'] = 'mongodb+srv://quanghuy060997_db_user:MPCuEbF2GhpmiZm8@cluster0.x3iyjjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
os.environ['CLOUD_DB_NAME'] = 'Crypto2025'

from cloud_db import db

print("=== Testing get_kv method ===")
holdings = db.get_kv("portfolio_meta", "holdings")
avg_prices = db.get_kv("portfolio_meta", "avg_price")

print("Holdings returned by get_kv:", holdings)
print("Avg Prices returned by get_kv:", avg_prices)

print("\n=== Key Analysis ===")
if holdings:
    print("Holdings keys:", list(holdings.keys()))
    print("Has _id?", "_id" in holdings)
    
if avg_prices:
    print("Avg prices keys:", list(avg_prices.keys()))
    print("Has _id?", "_id" in avg_prices)