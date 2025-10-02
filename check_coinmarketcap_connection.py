import requests
import streamlit as st

def check_coingecko_connection():
    """
    Check the connection with CoinGecko API by making a simple request.
    """
    url = "https://api.coingecko.com/api/v3/ping"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            st.success("Successfully connected to CoinGecko API.")
        else:
            st.error(f"Failed to connect to CoinGecko API. Status code: {response.status_code}")
    except Exception as e:
        st.error(f"Error connecting to CoinGecko API: {e}")

if __name__ == "__main__":
    check_coingecko_connection()