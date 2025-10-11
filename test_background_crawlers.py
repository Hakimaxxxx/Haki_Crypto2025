import requests
import pandas as pd
import time
from datetime import datetime
import os

def test_dominance_crawler():
    """Test dominance data crawling and CSV saving."""
    print("=== Testing Dominance Crawler ===")
    
    file = "test_dominance_history.csv"
    
    try:
        # Fetch data from CoinGecko
        resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
        data = resp.json().get("data", {})
        dom = data.get("market_cap_percentage", {})
        btc = dom.get("btc", 0.0)
        eth = dom.get("eth", 0.0)
        others = 100 - btc - eth
        ts = int(time.time())
        
        print(f"Fetched data: BTC={btc:.2f}%, ETH={eth:.2f}%, Others={others:.2f}%")
        
        # Create row with proper format to match existing CSV
        ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        row = {"timestamp": ts_str, "BTC": btc, "ETH": eth, "Others": others}
        
        # Save to CSV
        if os.path.exists(file):
            df = pd.read_csv(file)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
        else:
            df = pd.DataFrame(columns=["timestamp","BTC","ETH","Others"])
        
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(file, index=False)
        
        print(f"✅ Dominance data saved to {file}")
        print(f"CSV content:\n{df.tail()}")
        
    except Exception as e:
        print(f"❌ Dominance test failed: {e}")
    finally:
        # Clean up
        if os.path.exists(file):
            os.remove(file)

def test_marketcap_crawler():
    """Test market cap data crawling and CSV saving."""
    print("\n=== Testing Market Cap Crawler ===")
    
    file = "test_marketcap_history.csv"
    
    try:
        # Fetch data from CoinGecko
        resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
        g = resp.json().get("data", {})
        mcap = float((g.get("total_market_cap") or {}).get("usd", 0.0))
        vol = float((g.get("total_volume") or {}).get("usd", 0.0))
        ts = int(time.time())
        
        print(f"Fetched data: Market Cap=${mcap/1e12:.2f}T, Volume=${vol/1e9:.2f}B")
        
        # Create row with proper format
        ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        row = {"timestamp": ts_str, "market_cap": mcap, "volume_1d": vol}
        
        # Save to CSV
        if os.path.exists(file):
            df = pd.read_csv(file)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
        else:
            df = pd.DataFrame(columns=["timestamp","market_cap","volume_1d"])
        
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(file, index=False)
        
        print(f"✅ Market cap data saved to {file}")
        print(f"CSV content:\n{df.tail()}")
        
    except Exception as e:
        print(f"❌ Market cap test failed: {e}")
    finally:
        # Clean up
        if os.path.exists(file):
            os.remove(file)

if __name__ == "__main__":
    test_dominance_crawler()
    test_marketcap_crawler()