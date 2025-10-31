from redis_cache import get_client, redis_available, get_cache_stats
import os
print("REDIS_URI =", os.getenv("REDIS_URI"))
print("Client =", get_client())
print("Available =", redis_available())
print("Cache stats =", get_cache_stats())