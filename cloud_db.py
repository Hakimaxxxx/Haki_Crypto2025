"""
Cloud database adapter with a simple abstraction.

Current backend: MongoDB Atlas (free tier supported).

Usage:
  - Set environment variables before running Streamlit:
      MONGO_URI=mongodb+srv://quanghuy060997_db_user:MPCuEbF2GhpmiZm8@cluster0.x3iyjjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
      CLOUD_DB_NAME=Crypto2025

  - Import and use the singleton `db`:
      from cloud_db import db
      if db.available():
          db.insert_one('logs', {...})
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGO_CLIENT = None


class CloudDB:
    """Cloud database abstraction for MongoDB Atlas."""

    def __init__(self) -> None:
        """Initialize the CloudDB instance and connect to MongoDB if URI is provided."""
        self._provider = None
        self._db = None
        mongo_uri = os.getenv("MONGO_URI")
        if mongo_uri:
            try:
                db_name = os.getenv("CLOUD_DB_NAME", "Cypto2025")
                global MONGO_CLIENT
                if MONGO_CLIENT is None:
                    MONGO_CLIENT = MongoClient(mongo_uri, tz_aware=True)
                self._db = MONGO_CLIENT[db_name]
                self._provider = "mongo"
            except PyMongoError:
                self._provider = None

    def available(self) -> bool:
        """Check if the database connection is available."""
        return self._db is not None

    def insert_one(self, collection: str, doc: Dict[str, Any]) -> Optional[str]:
        """Insert a single document into the specified collection."""
        if not self.available():
            return None
        try:
            res = self._db[collection].insert_one(doc)
            return str(res.inserted_id)
        except PyMongoError:
            return None

    def upsert_many(self, collection: str, docs: Iterable[Dict[str, Any]], unique_keys: List[str]) -> int:
        """Upsert multiple documents into the specified collection."""
        if not self.available():
            return 0
        count = 0
        col = self._db[collection]
        for d in docs:
            try:
                filt = {k: d.get(k) for k in unique_keys if k in d}
                update = {k: v for k, v in d.items() if k not in ("_id",)}
                if not filt:
                    # Skip docs without unique keys
                    continue
                col.update_one(filt, {"$set": update}, upsert=True)
                count += 1
            except PyMongoError:
                continue
        return count

    def find_all(self, collection: str, sort_field: Optional[str] = None, ascending: bool = True, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find all documents in the specified collection with optional sorting and limiting."""
        if not self.available():
            return []
        try:
            cur = self._db[collection].find({})
            if sort_field:
                cur = cur.sort(sort_field, 1 if ascending else -1)
            if limit:
                cur = cur.limit(int(limit))
            return [self._strip_id(d) for d in cur]
        except PyMongoError:
            return []

    def get_kv(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """Get a key-value pair from the specified collection."""
        if not self.available():
            return None
        try:
            doc = self._db[collection].find_one({"_id": key})
            return self._strip_id(doc) if doc else None
        except PyMongoError:
            return None

    def set_kv(self, collection: str, key: str, value: Dict[str, Any]) -> bool:
        """Set a key-value pair in the specified collection."""
        if not self.available():
            return False
        try:
            doc = dict(value)
            doc["_id"] = key
            self._db[collection].update_one({"_id": key}, {"$set": doc}, upsert=True)
            return True
        except PyMongoError:
            return False

    @staticmethod
    def _strip_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Remove the '_id' field from a document."""
        if not doc:
            return doc
        d = dict(doc)
        d.pop("_id", None)
        return d


# Singleton
db = CloudDB()

from cloud_db import db

if db.available():
    print("Cloud database connected successfully!")
else:
    print("Failed to connect to the cloud database.")
if db.available():
    result = db.insert_one("test_collection", {"key": "value"})
    if result:
        print(f"Document inserted with ID: {result}")
    else:
        print("Failed to insert document.")


import unittest
from cloud_db import db

class TestCloudDB(unittest.TestCase):
    def test_connection(self):
        self.assertTrue(db.available(), "Database connection failed!")

    def test_insert_one(self):
        result = db.insert_one("test_collection", {"key": "test_value"})
        self.assertIsNotNone(result, "Failed to insert document!")

    def test_find_all(self):
        docs = db.find_all("test_collection")
        self.assertGreater(len(docs), 0, "No documents found!")

if __name__ == "__main__":
    unittest.main()