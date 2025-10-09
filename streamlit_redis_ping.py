import streamlit as st
import redis
import os

REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")

@st.cache_resource

def get_redis_client():
    return redis.Redis.from_url(REDIS_URI)

def ping_redis(client):
    try:
        return client.ping()
    except Exception as e:
        return f"Error: {e}"

st.title("Redis Ping Test")

client = get_redis_client()

ping_result = ping_redis(client)

if ping_result is True:
    st.success("Redis ping successful!")
else:
    st.error(f"Redis ping failed: {ping_result}")

st.write(f"REDIS_URI: {REDIS_URI}")
