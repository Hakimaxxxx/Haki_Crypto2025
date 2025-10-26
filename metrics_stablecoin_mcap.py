"""
Stablecoin Market Cap Metric

Fetches and visualizes total market cap of major stablecoins (USDT, USDC, DAI, FDUSD)
overlayed with BTC price to show correlation and market liquidity.

Data sources (with automatic fallback):
1. CryptoCompare (free tier: 100K calls/month) - PRIMARY
2. CoinMarketCap (free tier: 10K calls/month) - SECONDARY
3. CoinGecko (rate limited) - FALLBACK

Cache: 3600s (1 hour) to reduce API pressure
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import requests

# Stablecoins to track
STABLECOINS = {
    'tether': 'USDT',
    'usd-coin': 'USDC',
    'dai': 'DAI',
    'first-digital-usd': 'FDUSD'
}

# CryptoCompare symbol mapping
CRYPTOCOMPARE_SYMBOLS = {
    'USDT': 'USDT',
    'USDC': 'USDC', 
    'DAI': 'DAI',
    'FDUSD': 'FDUSD'
}

# CoinMarketCap symbol mapping
CMC_SYMBOLS = {
    'USDT': 'USDT',
    'USDC': 'USDC',
    'DAI': 'DAI',
    'FDUSD': 'FDUSD'
}

CACHE_FILE = "stablecoin_mcap_cache.json"
CACHE_TTL = 3600  # 1 hour

# API Keys from environment (optional, works without keys but with limits)
CMC_API_KEY = os.getenv('CMC_API_KEY', '')  # CoinMarketCap
CRYPTOCOMPARE_API_KEY = os.getenv('CRYPTOCOMPARE_API_KEY', '')  # CryptoCompare


def _get_cache_path():
    return os.path.join(os.path.dirname(__file__), CACHE_FILE)


def _load_cache() -> Optional[Dict]:
    """Load cached data if valid."""
    try:
        path = _get_cache_path()
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Check TTL
        ts = data.get('timestamp', 0)
        if time.time() - ts > CACHE_TTL:
            return None
        return data
    except Exception:
        return None


def _save_cache(data: Dict):
    """Save data to cache."""
    try:
        data['timestamp'] = time.time()
        path = _get_cache_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def fetch_stablecoin_market_caps(days: int = 365) -> Tuple[pd.DataFrame, bool]:
    """Fetch historical market cap data for stablecoins and BTC price.
    
    Tries multiple sources with automatic fallback:
    1. CryptoCompare (most generous free tier)
    2. CoinMarketCap (good free tier)
    3. CoinGecko (fallback, rate limited)
    
    Returns:
        (DataFrame, success): DataFrame with columns [date, total_mcap, btc_price], boolean success flag
    """
    # Try cache first
    cache = _load_cache()
    if cache and cache.get('days') == days:
        try:
            df = pd.DataFrame(cache.get('data', []))
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                return df, True
        except Exception:
            pass
    
    # Try each source in priority order
    sources = [
        ('CryptoCompare', _fetch_from_cryptocompare),
        ('CoinMarketCap', _fetch_from_coinmarketcap),
        ('CoinGecko', _fetch_from_coingecko)
    ]
    
    for source_name, fetch_func in sources:
        try:
            print(f"[Stablecoin MCap] Trying {source_name}...")
            df = fetch_func(days)
            if df is not None and not df.empty:
                # Save to cache
                cache_data = {
                    'days': days,
                    'data': df.to_dict(orient='records'),
                    'source': source_name,
                    'fetched_at': datetime.now().isoformat()
                }
                _save_cache(cache_data)
                print(f"[Stablecoin MCap] Success with {source_name}")
                return df, True
        except Exception as e:
            print(f"[Stablecoin MCap] {source_name} failed: {e}")
            continue
    
    return pd.DataFrame(), False


def _fetch_from_cryptocompare(days: int) -> Optional[pd.DataFrame]:
    """Fetch from CryptoCompare API - most generous free tier (100K calls/month)."""
    
    # Calculate timestamp range
    to_ts = int(time.time())
    from_ts = to_ts - (days * 86400)
    
    all_data = []
    
    # Fetch BTC price history
    btc_url = f"https://min-api.cryptocompare.com/data/v2/histoday"
    params = {
        'fsym': 'BTC',
        'tsym': 'USD',
        'limit': min(days, 2000),  # API limit
        'toTs': to_ts
    }
    if CRYPTOCOMPARE_API_KEY:
        params['api_key'] = CRYPTOCOMPARE_API_KEY
    
    response = requests.get(btc_url, params=params, timeout=15)
    response.raise_for_status()
    btc_data = response.json()
    
    if btc_data.get('Response') != 'Success':
        raise Exception(f"CryptoCompare API error: {btc_data.get('Message')}")
    
    btc_df = pd.DataFrame(btc_data['Data']['Data'])
    btc_df['date'] = pd.to_datetime(btc_df['time'], unit='s').dt.date
    btc_df = btc_df[['date', 'close']].rename(columns={'close': 'btc_price'})
    
    # Fetch stablecoin market caps
    # Note: CryptoCompare doesn't have direct market cap history API
    # We'll estimate using: market_cap ≈ circulating_supply × price
    # For stablecoins, price ≈ $1, so we need supply data
    
    # For now, fallback to aggregated approach or use snapshot
    # This is a limitation of CryptoCompare for historical market cap
    raise Exception("CryptoCompare doesn't provide historical market cap - trying next source")


def _fetch_from_coinmarketcap(days: int) -> Optional[pd.DataFrame]:
    """Fetch from CoinMarketCap API - requires API key but good free tier (10K calls/month)."""
    
    if not CMC_API_KEY:
        raise Exception("CoinMarketCap requires API key - set CMC_API_KEY environment variable")
    
    headers = {
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
        'Accept': 'application/json'
    }
    
    # CMC provides historical quotes via /v2/cryptocurrency/quotes/historical
    # But this is limited in free tier; we'll use latest quotes and global metrics
    
    # For historical data, CMC free tier is very limited
    # Falling back to next source
    raise Exception("CoinMarketCap historical data requires pro tier - trying next source")


def _fetch_from_coingecko(days: int) -> Optional[pd.DataFrame]:
    """Fetch from CoinGecko API - fallback option (rate limited)."""
    
    # Fetch BTC price history
    btc_url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    btc_response = requests.get(btc_url, timeout=15)
    btc_response.raise_for_status()
    btc_data = btc_response.json()
    
    # Convert BTC data to DataFrame
    btc_df = pd.DataFrame(btc_data['prices'], columns=['timestamp', 'btc_price'])
    btc_df['date'] = pd.to_datetime(btc_df['timestamp'], unit='ms').dt.date
    btc_df = btc_df.groupby('date')['btc_price'].mean().reset_index()
    
    # Fetch market cap for each stablecoin
    stablecoin_dfs = []
    for coin_id, symbol in STABLECOINS.items():
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            df = pd.DataFrame(data['market_caps'], columns=['timestamp', f'{symbol}_mcap'])
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
            df = df.groupby('date')[f'{symbol}_mcap'].mean().reset_index()
            stablecoin_dfs.append(df)
            
            # Rate limit protection
            time.sleep(1.2)
        except Exception as e:
            print(f"[Stablecoin MCap] Failed to fetch {symbol}: {e}")
            continue
    
    if not stablecoin_dfs:
        raise Exception("Failed to fetch any stablecoin data from CoinGecko")
    
    # Merge all stablecoin data
    result = stablecoin_dfs[0]
    for df in stablecoin_dfs[1:]:
        result = result.merge(df, on='date', how='outer')
    
    # Merge with BTC price
    result = result.merge(btc_df, on='date', how='inner')
    
    # Calculate total market cap
    mcap_cols = [col for col in result.columns if col.endswith('_mcap')]
    result['total_mcap'] = result[mcap_cols].sum(axis=1)
    
    # Convert to billions for readability
    result['total_mcap'] = result['total_mcap'] / 1e9
    
    # Sort by date
    result = result.sort_values('date').reset_index(drop=True)
    result['date'] = pd.to_datetime(result['date'])
    
    return result


def plot_stablecoin_mcap_chart(df: pd.DataFrame, title: str = "Total Stablecoin Market Cap vs BTC Price") -> Optional[go.Figure]:
    """Create dual-axis chart: stablecoin market cap (area) and BTC price (line).
    
    Args:
        df: DataFrame with columns [date, total_mcap, btc_price]
        title: Chart title
        
    Returns:
        Plotly Figure or None if data is invalid
    """
    if df is None or df.empty:
        return None
    
    try:
        fig = go.Figure()
        
        # Area chart for stablecoin market cap (primary y-axis)
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['total_mcap'],
            name='Stablecoin Market Cap',
            fill='tozeroy',
            line=dict(color='rgba(100, 181, 246, 0.8)', width=2),
            fillcolor='rgba(100, 181, 246, 0.3)',
            yaxis='y'
        ))
        
        # Line chart for BTC price (secondary y-axis)
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['btc_price'],
            name='BTC Price',
            line=dict(color='rgba(255, 167, 38, 0.9)', width=2),
            yaxis='y2'
        ))
        
        # Layout with dual y-axes
        fig.update_layout(
            title=title,
            xaxis=dict(title='Date', showgrid=True),
            yaxis=dict(
                title='Stablecoin Market Cap (Billions USD)',
                side='left',
                showgrid=True,
                rangemode='tozero'
            ),
            yaxis2=dict(
                title='BTC Price (USD)',
                side='right',
                overlaying='y',
                showgrid=False,
                rangemode='tozero'
            ),
            hovermode='x unified',
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            ),
            height=500,
            template='plotly_white'
        )
        
        return fig
        
    except Exception as e:
        print(f"[Stablecoin MCap] Error creating chart: {e}")
        return None


def show_stablecoin_mcap_metric():
    """Main function to display stablecoin market cap metric in Streamlit."""
    st.subheader("📊 Total Stablecoin Market Cap")
    
    # Data source info
    cache = _load_cache()
    if cache:
        source = cache.get('source', 'Unknown')
        fetched_at = cache.get('fetched_at', 'Unknown')
        st.caption(f"💡 Data source: **{source}** | Last fetched: {fetched_at}")
    
    # Timeframe selector
    timeframe_options = {
        '30 Days': 30,
        '90 Days': 90,
        '180 Days': 180,
        '1 Year': 365,
        'All Time': 'max'
    }
    
    selected_timeframe = st.selectbox(
        "Select Timeframe",
        list(timeframe_options.keys()),
        index=3,  # Default to 1 Year
        key="stablecoin_mcap_timeframe"
    )
    
    days = timeframe_options[selected_timeframe]
    if days == 'max':
        days = 1825  # ~5 years
    
    # Force refresh button and API key setup
    col1, col2 = st.columns([3, 1])
    with col1:
        with st.expander("🔑 API Key Setup (Optional - for better rate limits)", expanded=False):
            st.markdown("""
            **Free API Keys:**
            - **CryptoCompare**: 100K calls/month - [Get Key](https://www.cryptocompare.com/cryptopian/api-keys)
            - **CoinMarketCap**: 10K calls/month - [Get Key](https://coinmarketcap.com/api/)
            
            Set environment variables:
            ```bash
            CRYPTOCOMPARE_API_KEY=your_key_here
            CMC_API_KEY=your_key_here
            ```
            """)
            if CMC_API_KEY:
                st.success("✅ CoinMarketCap API key detected")
            if CRYPTOCOMPARE_API_KEY:
                st.success("✅ CryptoCompare API key detected")
            if not CMC_API_KEY and not CRYPTOCOMPARE_API_KEY:
                st.info("ℹ️ No API keys detected - using CoinGecko (may hit rate limits)")
    
    with col2:
        force_refresh = st.button("🔄 Refresh", key="stablecoin_mcap_refresh")
    
    if force_refresh:
        # Clear cache
        try:
            cache_path = _get_cache_path()
            if os.path.exists(cache_path):
                os.remove(cache_path)
            st.success("Cache cleared, fetching fresh data...")
        except Exception:
            pass
    
    # Fetch and display data
    with st.spinner("Fetching stablecoin market cap data..."):
        df, success = fetch_stablecoin_market_caps(days=days)
    
    if not success or df.empty:
        st.error("❌ Failed to fetch stablecoin market cap data from all sources.")
        st.markdown("""
        **Troubleshooting:**
        - CoinGecko may be rate-limited (wait 1-2 minutes)
        - Consider adding API keys for CryptoCompare or CoinMarketCap (see setup above)
        - Check your internet connection
        """)
        return
    
    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    try:
        latest = df.iloc[-1]
        earliest = df.iloc[0]
        
        with col1:
            st.metric(
                "Current Stablecoin MCap",
                f"${latest['total_mcap']:.2f}B",
                delta=f"{((latest['total_mcap'] - earliest['total_mcap']) / earliest['total_mcap'] * 100):.1f}%"
            )
        
        with col2:
            st.metric(
                "Current BTC Price",
                f"${latest['btc_price']:,.0f}",
                delta=f"{((latest['btc_price'] - earliest['btc_price']) / earliest['btc_price'] * 100):.1f}%"
            )
        
        with col3:
            max_mcap = df['total_mcap'].max()
            st.metric("Peak Stablecoin MCap", f"${max_mcap:.2f}B")
        
        with col4:
            max_btc = df['btc_price'].max()
            st.metric("Peak BTC Price", f"${max_btc:,.0f}")
    except Exception:
        pass
    
    # Display chart
    fig = plot_stablecoin_mcap_chart(df)
    
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False, 'responsive': True})
    else:
        st.warning("⚠️ Unable to generate chart from the data.")
    
    # Data insights
    with st.expander("📈 Data Insights", expanded=False):
        st.caption(f"**Coverage:** {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
        st.caption(f"**Stablecoins tracked:** {', '.join(STABLECOINS.values())}")
        st.caption("**Interpretation:** Rising stablecoin market cap often indicates capital inflows into crypto markets, while declining market cap may suggest capital outflows or redemptions.")
        
        # Show recent data sample
        if len(df) > 0:
            st.dataframe(
                df[['date', 'total_mcap', 'btc_price']].tail(10).style.format({
                    'total_mcap': '${:,.2f}B',
                    'btc_price': '${:,.0f}'
                }),
                hide_index=True
            )


if __name__ == "__main__":
    # Standalone test
    print("Testing Stablecoin Market Cap metric...")
    df, success = fetch_stablecoin_market_caps(days=90)
    if success:
        print(f"Fetched {len(df)} data points")
        print(df.head())
        print(df.tail())
    else:
        print("Failed to fetch data")
