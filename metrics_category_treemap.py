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

CACHE_FILE = 'category_treemap_cache.json'
CACHE_TTL = 3600  # 1 hour (refresh hourly for updated market data)

# Core categories that are most reliable on CoinGecko
FEATURED_CATEGORIES = [
    # Layer & Infrastructure (3)
    'layer-1',
    'layer-2',
    'infrastructure',
    
    # DeFi Ecosystem (5)
    'decentralized-finance-defi',
    'decentralized-exchange',
    'lending-borrowing',
    'yield-farming',
    'stablecoins',
    
    # AI & Trending (4)
    'artificial-intelligence',
    'ai-meme-coins',
    'real-world-assets-rwa',
    'meme-token',
    
    # Gaming & NFT (3)
    'gaming',
    'metaverse',
    'non-fungible-tokens-nft',
    
    # Other (4)
    'exchange-based-tokens',
    'privacy-coins',
    'storage',
    'oracle'
]

# Total: 19 categories


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


def _fetch_category_data(category_id: str, limit: int = 20) -> Optional[List[Dict]]:
    """Fetch top 20 coins in a specific category with retry on rate limit."""
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
    
    # Retry up to 2 times on rate limit
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 429:
                if attempt == 0:
                    print(f"    Rate limited, waiting 10s...")
                    time.sleep(10)
                    continue
                else:
                    return None
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            if attempt == 1:
                print(f"[Category Treemap] Error fetching {category_id}: {e}")
            return None
    
    return None


def fetch_all_categories(categories: List[str] = FEATURED_CATEGORIES) -> Tuple[Dict, bool]:
    """Fetch data for all featured categories with robust error handling.
    
    Returns:
        (data_dict, success): Dictionary of category data and success flag
    """
    cache = _load_cache()
    if cache and cache.get('categories'):
        loaded_count = len(cache['categories'])
        missing_count = len(categories) - loaded_count
        
        if missing_count == 0:
            print(f"[Category Treemap] OK Loaded all {loaded_count}/{len(categories)} categories from cache")
            return cache['categories'], True
        else:
            print(f"[Category Treemap] WARN Cache has only {loaded_count}/{len(categories)} categories")
            print(f"[Category Treemap] Will attempt to fetch missing {missing_count} categories...")
            all_data = cache['categories'].copy()
    else:
        all_data = {}
        print(f"[Category Treemap] Fetching all {len(categories)} categories from CoinGecko...")
    
    try:
        total_categories = len(categories)
        fetched_count = len(all_data)
        failed_categories = []
        
        print(f"[Category Treemap] Estimated time: ~{total_categories * 2.5} seconds (rate limited)")
        
        for i, cat_id in enumerate(categories, 1):
            # Skip if already in cache
            if cat_id in all_data:
                print(f"  [{i}/{total_categories}] CACHE {cat_id}: {len(all_data[cat_id])} coins (skipped)")
                continue
            
            print(f"  [{i}/{total_categories}] Fetching {cat_id}...", end=' ')
            coins = _fetch_category_data(cat_id, limit=20)
            
            if coins and len(coins) > 0:
                all_data[cat_id] = coins
                fetched_count += 1
                print(f"OK ({len(coins)} coins)")
            elif coins is not None and len(coins) == 0:
                print(f"WARN (No coins)")
                failed_categories.append(f"{cat_id} (empty)")
            else:
                print(f"ERROR (API failed)")
                failed_categories.append(f"{cat_id} (error)")
            
            # Save partial results after each fetch (resilience against rate limits)
            if len(all_data) > 0 and (i % 5 == 0 or i == total_categories):
                _save_cache({'categories': all_data})
                print(f"  [Progress saved: {len(all_data)}/{total_categories} categories]")
            
            # Progressive delay to avoid rate limits
            if i < total_categories:
                if i % 10 == 0:
                    # Every 10 requests, wait longer
                    print(f"  [Cooldown: 15s to avoid rate limit...]")
                    time.sleep(15)
                else:
                    time.sleep(2.5)  # Standard delay
        
        # Final summary
        success_rate = (fetched_count / total_categories) * 100
        print(f"\n[Category Treemap] ========================================")
        print(f"[Category Treemap] SUMMARY:")
        print(f"  Total categories: {total_categories}")
        print(f"  Successfully loaded: {len(all_data)} ({success_rate:.1f}%)")
        print(f"  Failed/Empty: {len(failed_categories)}")
        
        if failed_categories:
            print(f"[Category Treemap] Failed categories:")
            for cat in failed_categories:
                print(f"    - {cat}")
        
        if len(all_data) >= total_categories * 0.7:  # 70% success threshold
            _save_cache({'categories': all_data})
            print(f"[Category Treemap] ✅ Cache saved (expires in 1 hour)")
            print(f"[Category Treemap] ========================================\n")
            return all_data, True
        elif len(all_data) > 0:
            _save_cache({'categories': all_data})
            print(f"[Category Treemap] ⚠️  Partial success - using {len(all_data)} categories")
            print(f"[Category Treemap] ========================================\n")
            return all_data, True
        else:
            print(f"[Category Treemap] ❌ No categories fetched - likely rate limited")
            print(f"[Category Treemap] Please wait 5-10 minutes before retrying")
            print(f"[Category Treemap] ========================================\n")
            return {}, False
            
    except Exception as e:
        print(f"[Category Treemap] FATAL Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Return partial data if available
        if len(all_data) > 0:
            print(f"[Category Treemap] Returning {len(all_data)} partial results")
            return all_data, True
        return {}, False


def prepare_treemap_data(category_data: Dict) -> pd.DataFrame:
    """Convert category data to DataFrame for treemap - CATEGORIES ONLY."""
    try:
        rows = []
        
        # Expanded category display names
        cat_names = {
            'layer-1': 'Layer 1',
            'layer-2': 'Layer 2',
            'decentralized-finance-defi': 'DeFi',
            'artificial-intelligence': 'AI',
            'ai-meme-coins': 'AI Agent',
            'real-world-assets-rwa': 'RWA',
            'tokenized-real-estate': 'RWA Real Estate',
            'gaming': 'Gaming',
            'meme-token': 'Meme',
            'dog-themed-coins': 'Dog Meme',
            'cat-themed-coins': 'Cat Meme',
            'infrastructure': 'Infrastructure',
            'exchange-based-tokens': 'CEX Tokens',
            'decentralized-exchange': 'DEX',
            'lending-borrowing': 'Lending',
            'yield-farming': 'Yield Farming',
            'stablecoins': 'Stablecoins',
            'metaverse': 'Metaverse',
            'non-fungible-tokens-nft': 'NFT',
            'privacy-coins': 'Privacy',
            'storage': 'Storage',
            'oracle': 'Oracle',
            'dao': 'DAO'
        }
        
        for cat_id, coins in category_data.items():
            cat_name = cat_names.get(cat_id, cat_id.replace('-', ' ').title())
            
            # Calculate category totals
            total_mcap = sum(c.get('market_cap', 0) or 0 for c in coins)
            avg_change_24h = sum(c.get('price_change_percentage_24h', 0) or 0 for c in coins) / len(coins) if coins else 0
            
            # Add ONLY category row (no individual coins in treemap)
            rows.append({
                'label': cat_name,
                'market_cap': total_mcap,
                'price_change_24h': avg_change_24h,
                'coin_count': len(coins)
            })
        
        df = pd.DataFrame(rows)
        return df
    except Exception as e:
        print(f"[Category Treemap] Data preparation error: {e}")
        return pd.DataFrame()


def plot_category_treemap(df: pd.DataFrame) -> Optional[go.Figure]:
    """Create interactive treemap of categories ONLY (no individual coins).
    
    Sizes boxes by absolute % change (volatility) instead of market cap
    to prevent BTC/ETH dominance and highlight hot sectors.
    """
    try:
        if df.empty:
            return None
        
        # Use absolute % change for sizing (volatility = importance)
        df['abs_change'] = df['price_change_24h'].abs()
        
        # Clamp color values for better visualization (±10% max for better contrast)
        df['color_val'] = df['price_change_24h'].apply(
            lambda x: max(min(x, 10), -10)  # Clamp to -10% to +10%
        )
        
        # Treemap with volatility-based sizing
        fig = go.Figure(go.Treemap(
            labels=df['label'],
            parents=[''] * len(df),  # All categories at root level
            values=df['abs_change'],  # Size by volatility, not market cap
            customdata=df[['market_cap', 'coin_count']],
            marker=dict(
                colorscale=[
                    [0.0, '#DC2626'],   # Deep Red (negative)
                    [0.3, '#EF4444'],   # Red
                    [0.45, '#FCA5A5'], # Light Red
                    [0.5, '#F3F4F6'],  # Neutral Gray
                    [0.55, '#86EFAC'], # Light Green
                    [0.7, '#22C55E'],  # Green
                    [1.0, '#16A34A']   # Deep Green (positive)
                ],
                cmid=0,
                cmin=-10,
                cmax=10,
                colorbar=dict(
                    title="24h %",
                    ticksuffix="%",
                    len=0.7
                ),
                line=dict(width=2, color='white')
            ),
            text=[f"{row['price_change_24h']:+.1f}%" 
                  for _, row in df.iterrows()],
            textposition='middle center',
            textfont=dict(size=14, color='#1a1a1a', family='Arial Black'),
            hovertemplate='<b>%{label}</b><br>' +
                          'Market Cap: $%{customdata[0]:,.0f}<br>' +
                          '24h Change: %{color:+.2f}%<br>' +
                          'Coins: %{customdata[1]}<br>' +
                          '<extra></extra>',
            marker_colors=df['color_val']
        ))
        
        fig.update_layout(
            title="Cryptocurrency Market by Category (Click category to drill down)",
            height=650,
            margin=dict(l=10, r=10, t=50, b=10)
        )
        
        return fig
    except Exception as e:
        print(f"[Category Treemap] Chart creation error: {e}")
        return None


def show_category_performance_metric():
    """Display category performance treemap in Streamlit."""
    st.subheader("🗺️ Market Category Performance")
    
    st.info("💡 **Treemap hiển thị các category crypto (L1, DeFi, Meme...).** Kích thước = Volatility (abs % change) → category biến động mạnh = box lớn. Màu = Direction (+/-, max ±10% cho contrast cao).")
    
    # Show cache status and missing categories
    total_categories = len(FEATURED_CATEGORIES)
    loaded_categories = 0
    missing_categories = []
    
    if os.path.exists(_get_cache_path()):
        cache = _load_cache()
        if cache and cache.get('categories'):
            loaded_categories = len(cache['categories'])
            missing_categories = [cat for cat in FEATURED_CATEGORIES if cat not in cache['categories']]
            
            cache_age_mins = (time.time() - cache.get('timestamp', 0)) / 60
            
            col1, col2 = st.columns([3, 1])
            with col1:
                if loaded_categories == total_categories:
                    st.success(f"✅ All {total_categories} categories loaded • Cache: {cache_age_mins:.0f}m ago")
                else:
                    st.warning(f"⚠️ {loaded_categories}/{total_categories} categories loaded • Missing: {len(missing_categories)}")
                    if missing_categories:
                        missing_names = [cat.replace('-', ' ').title() for cat in missing_categories[:5]]
                        st.caption(f"Missing: {', '.join(missing_names)}" + (" ..." if len(missing_categories) > 5 else ""))
    else:
        st.warning(f"⏳ **First load:** Fetching top 20 coins × {total_categories} categories (~50s)...")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col2:
        force_refresh = st.button("🔄 Full Refresh", key="category_refresh")
    with col3:
        if missing_categories:
            retry_missing = st.button(f"♻️ Retry ({len(missing_categories)})", key="retry_missing")
        else:
            retry_missing = False
    
    if force_refresh:
        try:
            if os.path.exists(_get_cache_path()):
                os.remove(_get_cache_path())
                st.info("♻️ Cache cleared, fetching all categories...")
        except Exception:
            pass
    
    if retry_missing and missing_categories:
        st.info(f"♻️ Attempting to fetch {len(missing_categories)} missing categories...")
        # Will fetch only missing ones since cache is kept
    
    with st.spinner("Loading category data..."):
        category_data, success = fetch_all_categories()
    
    if not success or not category_data:
        st.error("❌ Failed to load category data from CoinGecko API.")
        st.warning("""
        **Có thể do:**
        - CoinGecko rate limit (50 calls/min) - đợi 5-10 phút rồi click 🔄 Refresh
        - Network issue - check internet connection
        
        **Metric này:** Top 20 coins × 19 categories, updates mỗi giờ, cache 1h.
        """)
        return
    
    # Show final status
    loaded_count = len(category_data)
    if loaded_count < total_categories:
        st.warning(f"⚠️ Displaying {loaded_count}/{total_categories} categories (some failed to load)")
    
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
    
    # Simple color coding without matplotlib
    def color_change(val):
        if val > 5:
            return 'background-color: #d4edda; color: #155724'  # Green
        elif val > 0:
            return 'background-color: #d1ecf1; color: #0c5460'  # Light green
        elif val > -5:
            return 'background-color: #fff3cd; color: #856404'  # Yellow
        else:
            return 'background-color: #f8d7da; color: #721c24'  # Red
    
    st.dataframe(
        df_summary.style.format({
            'Market Cap': '${:,.0f}',
            '24h Change %': '{:+.2f}%'
        }).applymap(color_change, subset=['24h Change %']),
        hide_index=True,
        use_container_width=True
    )
    
    # Drill-down section
    st.markdown("---")
    st.markdown("### 🔍 Category Drill-Down")
    st.caption("👇 Chọn category để xem top 20 coins đại diện cho category đó")
    
    # Enhanced category names for dropdown
    cat_display_map = {
        'layer-1': '🔷 Layer 1',
        'layer-2': '⚡ Layer 2',
        'infrastructure': '🏗️ Infrastructure',
        'decentralized-finance-defi': '💰 DeFi',
        'decentralized-exchange': '🔄 DEX',
        'lending-borrowing': '🏦 Lending',
        'yield-farming': '🌾 Yield Farming',
        'stablecoins': '💵 Stablecoins',
        'artificial-intelligence': '🤖 AI',
        'ai-meme-coins': '🧠 AI Agent',
        'real-world-assets-rwa': '🏛️ RWA',
        'tokenized-real-estate': '� RWA Real Estate',
        'meme-token': '🐶 Meme',
        'dog-themed-coins': '🐕 Dog Meme',
        'cat-themed-coins': '🐱 Cat Meme',
        'gaming': '🎮 Gaming',
        'metaverse': '🌐 Metaverse',
        'non-fungible-tokens-nft': '🖼️ NFT',
        'exchange-based-tokens': '🏢 CEX Tokens',
        'privacy-coins': '🔒 Privacy',
        'storage': '💾 Storage',
        'oracle': '� Oracle',
        'dao': '�️ DAO',
    }
    
    selected_cat = st.selectbox(
        "Select a category:",
        options=list(category_data.keys()),
        format_func=lambda x: cat_display_map.get(x, x.replace('-', ' ').title())
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
        
        # Color coding for 24h change
        def color_24h(val):
            if val > 10:
                return 'background-color: #28a745; color: white'  # Strong green
            elif val > 5:
                return 'background-color: #d4edda; color: #155724'  # Green
            elif val > 0:
                return 'background-color: #d1ecf1; color: #0c5460'  # Light green
            elif val > -5:
                return 'background-color: #fff3cd; color: #856404'  # Yellow
            elif val > -10:
                return 'background-color: #f8d7da; color: #721c24'  # Light red
            else:
                return 'background-color: #dc3545; color: white'  # Strong red
        
        st.dataframe(
            df_coins.style.format({
                'Price': '${:,.4f}',
                'Market Cap': '${:,.0f}',
                '24h %': '{:+.2f}%',
                '7d %': '{:+.2f}%'
            }).applymap(color_24h, subset=['24h %']),
            hide_index=True,
            use_container_width=True,
            height=600
        )
    
    # Info section
    with st.expander("ℹ️ About Category Performance", expanded=False):
        st.markdown("""
        **Treemap hiển thị:**
        - **Kích thước ô**: Abs % change (volatility) → box lớn = biến động mạnh
        - **Màu sắc**: Direction (đỏ = giảm, xanh = tăng)
        - **BTC/ETH nhỏ**: Vì biến động ít (~2-3%/day) so với altcoin (~10-20%)

        **Cách sử dụng:**
        - Box lớn + xanh → Sector đang hot pump (AI Meme, Gaming, etc.)
        - Box lớn + đỏ → Sector đang dump mạnh
        - L1 nhỏ → Ổn định, không biến động
        
        **Data:**
        - Top 20 coins/category (đại diện sector)
        - Updates mỗi giờ
        - Cache 1h để giảm API pressure
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
