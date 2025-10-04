import os
os.environ['MONGO_URI'] = 'mongodb+srv://quanghuy060997_db_user:MPCuEbF2GhpmiZm8@cluster0.x3iyjjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
os.environ['CLOUD_DB_NAME'] = 'Crypto2025'

from pymongo import MongoClient
client = MongoClient(os.environ['MONGO_URI'])
db = client[os.environ['CLOUD_DB_NAME']]

# Check portfolio_meta
print('=== Portfolio Meta ===')
meta_holdings = db.get_collection('portfolio_meta').find_one({'_id': 'holdings'})
meta_avg_price = db.get_collection('portfolio_meta').find_one({'_id': 'avg_price'})
print('Holdings:', meta_holdings)
print('Avg Price:', meta_avg_price)

# Check portfolio_history count
print('\n=== Portfolio History ===')
history_count = db.portfolio_history.count_documents({})
print(f'Total history records: {history_count}')

# Show recent 3 records
recent = list(db.portfolio_history.find({}).sort('timestamp', -1).limit(3))
print('Recent 3 records:')
for r in recent:
    print(r)

# Check kv store structure
print('\n=== Key-Value Store ===')
kv_docs = list(db.portfolio_meta.find({}))
print('All portfolio_meta documents:')
for doc in kv_docs:
    print(doc)