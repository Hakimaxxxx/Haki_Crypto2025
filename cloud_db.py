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
import time

MONGO_CLIENT = None


class CloudDB:
    """Cloud database abstraction for MongoDB Atlas."""

    def __init__(self) -> None:
        """Initialize the CloudDB instance and connect to MongoDB if URI is provided."""
        self._provider = None
        self._db = None
        self._mongo_uri = os.getenv("MONGO_URI")
        self._db_name = os.getenv("CLOUD_DB_NAME", "Crypto2025")  # Fixed typo
        self._last_attempt = 0.0
        self._retry_interval = 30  # seconds between reconnect attempts
        self._last_error_msg = None  # type: Optional[str]
        self._connect_initial()

    def _connect_initial(self):
        if not self._mongo_uri:
            return
        try:
            global MONGO_CLIENT
            if MONGO_CLIENT is None:
                MONGO_CLIENT = MongoClient(
                    self._mongo_uri, 
                    tz_aware=True, 
                    serverSelectionTimeoutMS=15000,  # Increased timeout
                    connectTimeoutMS=15000,
                    socketTimeoutMS=15000,
                    maxPoolSize=10
                )
            # Force a ping to validate
            MONGO_CLIENT.admin.command('ping')
            self._db = MONGO_CLIENT[self._db_name]
            self._provider = "mongo"
        except PyMongoError as e:
            self._provider = None
            self._last_error_msg = f"initial connect error: {e}"[:300]

    def _maybe_reconnect(self):
        if self._db is not None or not self._mongo_uri:
            return
        now = time.time()
        if now - self._last_attempt < self._retry_interval:
            return
        self._last_attempt = now
        try:
            global MONGO_CLIENT
            MONGO_CLIENT = MongoClient(
                self._mongo_uri, 
                tz_aware=True, 
                serverSelectionTimeoutMS=15000,  # Increased timeout
                connectTimeoutMS=15000,
                socketTimeoutMS=15000,
                maxPoolSize=10
            )
            MONGO_CLIENT.admin.command('ping')
            self._db = MONGO_CLIENT[self._db_name]
            self._provider = "mongo"
            self._last_error_msg = None  # Clear error on successful connect
        except PyMongoError as e:
            self._provider = None
            self._last_error_msg = f"reconnect error: {e}"[:300]

    def available(self) -> bool:
        """Check if the database connection is available (attempt lazy reconnect)."""
        if self._db is None:
            self._maybe_reconnect()
        
        # Additional ping test to ensure connection is really alive
        if self._db is not None:
            try:
                global MONGO_CLIENT
                if MONGO_CLIENT:
                    MONGO_CLIENT.admin.command('ping')
                return True
            except Exception as e:
                self._last_error_msg = f"ping failed: {e}"[:300]
                self._db = None
                return False
        
        return self._db is not None

    def last_error(self) -> str | None:
        return self._last_error_msg

    def get_connection_info(self) -> Dict[str, Any]:
        """Get detailed connection information for debugging."""
        return {
            "mongo_uri_set": bool(self._mongo_uri),
            "db_name": self._db_name,
            "provider": self._provider,
            "db_available": self._db is not None,
            "last_error": self._last_error_msg,
            "last_attempt": self._last_attempt,
            "retry_interval": self._retry_interval
        }

    def force_reconnect(self) -> bool:
        """Force an immediate reconnect attempt regardless of backoff."""
        self._last_attempt = 0
        old_db = self._db
        self._db = None
        self._maybe_reconnect()
        return self._db is not None and old_db is not self._db

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


# Singleton exposed for importers
db = CloudDB()

__all__ = ["CloudDB", "db"]

# (Optional lightweight connection log – disabled in Streamlit to avoid clutter)
if os.getenv("PRINT_DB_STATUS_ON_IMPORT", "0") == "1":
    print("Cloud DB connected" if db.available() else "Cloud DB NOT available")