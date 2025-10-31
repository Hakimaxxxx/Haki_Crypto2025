"""
Test liquidation map visualization
Run this to see the chart in browser
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == '__main__':
    print("🔥 Testing Liquidation Map...")
    
    # Test imports first
    try:
        print("Importing modules...")
        from metrics_liquidation_map import (
            fetch_open_interest_multi_exchange,
            plot_liquidation_map
        )
        print("✅ Imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nInstalling required packages...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "plotly", "pandas", "numpy", "requests"])
        print("\nRetry importing...")
        from metrics_liquidation_map import (
            fetch_open_interest_multi_exchange,
            plot_liquidation_map
        )
    
    # Test multi-exchange data fetch
    print("\n📊 Fetching multi-exchange data for BTC...")
    try:
        data = fetch_open_interest_multi_exchange('BTC')
        
        if data:
            print("\n✅ Successfully fetched data from exchanges:")
            for exchange, (price, long_oi, short_oi) in data.items():
                print(f"\n  {exchange.upper()}:")
                print(f"    Price: ${price:,.2f}")
                print(f"    Long OI: ${long_oi:,.0f} ({long_oi/1e6:.2f}M)")
                print(f"    Short OI: ${short_oi:,.0f} ({short_oi/1e6:.2f}M)")
                print(f"    L/S Ratio: {long_oi/short_oi:.2f}")
        else:
            print("❌ No data returned")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Generate chart
    print("\n📈 Generating liquidation map chart...")
    try:
        fig = plot_liquidation_map(
            symbol='BTC',
            exchange='total',
            timeframe='1 day',
            leverage_levels=[10, 25, 50, 100],
            price_range_pct=10.0
        )
        
        if fig:
            print("✅ Chart generated successfully!")
            print("Opening in browser...")
            fig.show()
        else:
            print("❌ Failed to generate chart")
    except Exception as e:
        print(f"❌ Error generating chart: {e}")
        import traceback
        traceback.print_exc()

