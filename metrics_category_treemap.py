"""
Category Performance Treemap

Visualizes cryptocurrency market by categories (L1, L2, DeFi, AI, RWA, Gaming, etc.)
- Treemap sized by market cap, colored by 24h price change
- Click category → drill down to top coins in that category
- Data source: CoinGecko categories API

Cache: 3600s (1 hour)
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests

CACHE_FILE = "category_treemap_cache.json"
CACHE_TTL = 3600  # 1 hour

# Featured categories to track
FEATURED_CATEGORIES = [
    'layer-1',
    'layer-2',
    'decentralized-finance-defi',
    'artificial-intelligence',
    'real-world-assets-rwa',
    'gaming',
    'meme-token',
    'infrastructure',
    'smart-contract-platform',
    'exchange-based-tokens'
]


def _get_cache_path():
    return os.path.join(os.path.dirname(__file__), CACHE_FILE)


def _load_cache() -> Optional[Dict]:
    try:
        path = _get_cache_path()
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('timestamp', 0) > CACHE_TTL:
            return None
        return data
    except Exception:
        return None


def _save_cache(data: Dict):
    try:
        data['timestamp'] = time.time()
        with open(_get_cache_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def _fetch_category_data(category_id: str, limit: int = 30) -> Optional[List[Dict]]:
    """Fetch top coins in a specific category."""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'category': category_id,
            'order': 'market_cap_desc',
            'per_page': limit,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '24h,7d'
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Category Treemap] Error fetching {category_id}: {e}")
        return None


def fetch_all_categories(categories: List[str] = FEATURED_CATEGORIES) -> Tuple[Dict, bool]:
    """Fetch data for all featured categories.
    
    Returns:
        (data_dict, success): Dictionary of category data and success flag
    """
    cache = _load_cache()
    if cache and cache.get('categories'):
        return cache['categories'], True
    
    try:
        all_data = {}
        
        for cat_id in categories:
            coins = _fetch_category_data(cat_id, limit=30)
            if coins:
                all_data[cat_id] = coins
                time.sleep(1.2)  # Rate limit: 50 calls/min = ~1.2s delay
        
        if all_data:
            _save_cache({'categories': all_data})
            return all_data, True
        
        return {}, False
    except Exception as e:
        print(f"[Category Treemap] Error: {e}")
        return {}, False


def prepare_treemap_data(category_data: Dict) -> pd.DataFrame:
    """Convert category data to DataFrame for treemap."""
    try:
        rows = []
        
        # Category display names
        cat_names = {
            'layer-1': 'Layer 1',
            'layer-2': 'Layer 2',
            'decentralized-finance-defi': 'DeFi',
            'artificial-intelligence': 'AI',
            'real-world-assets-rwa': 'RWA',
            'gaming': 'Gaming',
            'meme-token': 'Meme',
            'infrastructure': 'Infrastructure',
            'smart-contract-platform': 'Smart Contract',
            'exchange-based-tokens': 'Exchange Tokens'
        }
        
        for cat_id, coins in category_data.items():
            cat_name = cat_names.get(cat_id, cat_id.replace('-', ' ').title())
            
            # Calculate category totals
            total_mcap = sum(c.get('market_cap', 0) or 0 for c in coins)
            avg_change_24h = sum(c.get('price_change_percentage_24h', 0) or 0 for c in coins) / len(coins) if coins else 0
            
            # Add category row
            rows.append({
                'category': cat_name,
                'coin': cat_name,
                'market_cap': total_mcap,
                'price_change_24h': avg_change_24h,
                'is_category': True
            })
            
            # Add top 5 coins per category
            for coin in coins[:5]:
                rows.append({
                    'category': cat_name,
                    'coin': f"{coin.get('symbol', '').upper()}",
                    'market_cap': coin.get('market_cap', 0) or 0,
                    'price_change_24h': coin.get('price_change_percentage_24h', 0) or 0,
                    'is_category': False
                })
        
        df = pd.DataFrame(rows)
        return df
    except Exception as e:
        print(f"[Category Treemap] Data preparation error: {e}")
        return pd.DataFrame()


def plot_category_treemap(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create interactive treemap of categories."""
    try:
        if df.empty:
            return None
        
        # Create custom color scale (red for negative, green for positive)
        df['color_val'] = df['price_change_24h'].apply(
            lambda x: max(min(x, 20), -20)  # Clamp to -20% to +20% for color scale
        )
        
        fig = px.treemap(
            df,
            path=['category', 'coin'],
            values='market_cap',
            color='color_val',
            color_continuous_scale=['#EF4444', '#FEF3C7', '#00D395'],
            color_continuous_midpoint=0,
            hover_data={
                'market_cap': ':,.0f',
                'price_change_24h': ':.2f',
                'color_val': False
            },
            labels={
                'market_cap': 'Market Cap',
                'price_change_24h': '24h Change %',
                'color_val': '24h %'
            }
        )
        
        fig.update_layout(
            title="Cryptocurrency Market by Category",
            height=700,
            margin=dict(l=10, r=10, t=50, b=10),
            coloraxis_colorbar=dict(
                title="24h %",
                ticksuffix="%",
                len=0.7
            )
        )
        
        # Customize hover template
        fig.update_traces(
            hovertemplate='<b>%{label}</b><br>Market Cap: $%{value:,.0f}<br>24h Change: %{customdata[1]:.2f}%<extra></extra>',
            texttemplate='<b>%{label}</b><br>%{customdata[1]:+.1f}%',
            textposition='middle center',
            textfont_size=11
        )
        
        return fig
    except Exception as e:
        print(f"[Category Treemap] Chart creation error: {e}")
        return None


def show_category_performance_metric():
    """Display category performance treemap in Streamlit."""
    st.subheader("🗺️ Market Category Performance")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        force_refresh = st.button("🔄 Refresh", key="category_refresh")
    
    if force_refresh:
        try:
            if os.path.exists(_get_cache_path()):
                os.remove(_get_cache_path())
        except Exception:
            pass
    
    with st.spinner("Loading category data..."):
        category_data, success = fetch_all_categories()
    
    if not success or not category_data:
        st.error("❌ Failed to load category data. Please try again.")
        return
    
    # Prepare and plot treemap
    df = prepare_treemap_data(category_data)
    if df.empty:
        st.error("❌ No data available for treemap.")
        return
    
    fig = plot_category_treemap(df)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False})
    
    # Category summary table
    st.markdown("### 📊 Category Summary (24h)")
    
    # Calculate category aggregates
    cat_summary = []
    for cat_id, coins in category_data.items():
        cat_name = cat_id.replace('-', ' ').title()
        total_mcap = sum(c.get('market_cap', 0) or 0 for c in coins)
        avg_change = sum(c.get('price_change_percentage_24h', 0) or 0 for c in coins) / len(coins) if coins else 0
        top_coin = max(coins, key=lambda x: x.get('market_cap', 0) or 0) if coins else {}
        
        cat_summary.append({
            'Category': cat_name,
            'Market Cap': total_mcap,
            '24h Change %': avg_change,
            'Top Coin': f"{top_coin.get('symbol', 'N/A').upper()}",
            'Coins': len(coins)
        })
    
    df_summary = pd.DataFrame(cat_summary)
    df_summary = df_summary.sort_values('Market Cap', ascending=False)
    
    st.dataframe(
        df_summary.style.format({
            'Market Cap': '${:,.0f}',
            '24h Change %': '{:+.2f}%'
        }).background_gradient(subset=['24h Change %'], cmap='RdYlGn', vmin=-5, vmax=5),
        hide_index=True,
        use_container_width=True
    )
    
    # Drill-down section
    st.markdown("---")
    st.markdown("### 🔍 Category Drill-Down")
    
    selected_cat = st.selectbox(
        "Select a category to view top 30 coins:",
        options=list(category_data.keys()),
        format_func=lambda x: x.replace('-', ' ').title()
    )
    
    if selected_cat and selected_cat in category_data:
        coins = category_data[selected_cat]
        df_coins = pd.DataFrame([
            {
                'Rank': i+1,
                'Coin': c.get('name', 'N/A'),
                'Symbol': c.get('symbol', 'N/A').upper(),
                'Price': c.get('current_price', 0),
                'Market Cap': c.get('market_cap', 0),
                '24h %': c.get('price_change_percentage_24h', 0) or 0,
                '7d %': c.get('price_change_percentage_7d_in_currency', 0) or 0
            }
            for i, c in enumerate(coins)
        ])
        
        st.dataframe(
            df_coins.style.format({
                'Price': '${:,.4f}',
                'Market Cap': '${:,.0f}',
                '24h %': '{:+.2f}%',
                '7d %': '{:+.2f}%'
            }).background_gradient(subset=['24h %'], cmap='RdYlGn', vmin=-10, vmax=10),
            hide_index=True,
            use_container_width=True,
            height=600
        )
    
    # Info section
    with st.expander("ℹ️ About Category Performance", expanded=False):
        st.markdown("""
        **Treemap hiển thị:**
        - **Kích thước ô**: Market cap của category/coin
        - **Màu sắc**: % thay đổi 24h (đỏ = giảm, xanh = tăng)
        - **Click vào category**: Zoom in để xem chi tiết top coins
        
        **Cách sử dụng:**
        - Xác định sector nào đang hot (nhiều ô xanh)
        - So sánh relative strength giữa các category
        - Phát hiện sector rotation khi vốn di chuyển giữa các category
        
        **Ý nghĩa:**
        - L1/L2 xanh → Infrastructure play đang mạnh
        - AI/RWA xanh → Narrative-driven rally
        - DeFi xanh → Risk-on sentiment, yield farming hot
        - Meme xanh → Retail FOMO, late-cycle signal
        """)


if __name__ == "__main__":
    print("Testing Category Performance Treemap...")
    data, ok = fetch_all_categories(FEATURED_CATEGORIES[:3])  # Test with 3 categories
    if ok and data:
        print(f"Loaded {len(data)} categories")
        for cat, coins in data.items():
            print(f"  {cat}: {len(coins)} coins")
    else:
        print("Failed to load category data")
