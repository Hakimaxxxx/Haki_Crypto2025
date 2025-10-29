"""
Backfill Altcoin Season Index History

Creates synthetic historical data for testing timeline chart.
This simulates what daily snapshots would look like over 1 year.

For production use, this should be replaced with actual daily snapshots.
But for testing/demo, we generate realistic-looking data based on:
- Bitcoin price movements
- Market cycles
- Seasonal patterns
"""
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from pathlib import Path


def generate_synthetic_altcoin_season_history(days: int = 365, current_value: float = 41.0) -> pd.DataFrame:
    """
    Generate synthetic Altcoin Season Index history anchored to current real value.
    
    Simulates realistic market cycles based on actual current index (e.g., 41 from Coinglass).
    Pattern follows typical crypto market cycles:
    - Bitcoin dominance periods (index 20-40)
    - Mixed markets (index 40-60)
    - Altcoin seasons (index 60-80, rare peaks to 90+)
    
    Args:
        days: Number of days of history
        current_value: Current real index value (default 41 from Coinglass)
    """
    end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    
    # Create daily timestamps
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    t = np.arange(len(dates))
    
    # Start from current_value and work backwards
    # Typical pattern: BTC bull → Alt season → BTC dominance → Mixed
    
    # Base trend (annual cycle)
    # Assume we're currently in "Bitcoin Season" phase (index ~41)
    # Previous alt season was ~6 months ago (peak ~75)
    # Next alt season will be ~6 months from now
    
    # Create a realistic sine wave peaking in past (6 months ago)
    phase_shift = -np.pi / 2  # Peak was 90 days ago
    annual_cycle = 55 + 25 * np.sin(2 * np.pi * (t - len(t)) / 365 + phase_shift)
    
    # Add quarterly volatility (90-day cycles)
    quarterly_cycle = 8 * np.sin(2 * np.pi * t / 90)
    
    # Add monthly noise
    monthly_noise = 5 * np.sin(2 * np.pi * t / 30)
    
    # Random walk component (realistic price action)
    random_walk = np.cumsum(np.random.normal(0, 2, len(dates)))
    random_walk = random_walk - random_walk[-1]  # Anchor to 0 at end
    
    # Combine all components
    index_values = annual_cycle + quarterly_cycle + monthly_noise + random_walk
    
    # Adjust to anchor last value to current_value
    adjustment = current_value - index_values[-1]
    index_values = index_values + adjustment
    
    # Clip to valid range [5, 95] (realistic bounds, extreme values are rare)
    index_values = np.clip(index_values, 5, 95)
    
    # Smooth out unrealistic jumps (max 15 points per day)
    for i in range(1, len(index_values)):
        max_change = 15
        if abs(index_values[i] - index_values[i-1]) > max_change:
            if index_values[i] > index_values[i-1]:
                index_values[i] = index_values[i-1] + max_change
            else:
                index_values[i] = index_values[i-1] - max_change
    
    # Calculate outperforming counts (realistic: index/2 out of 100)
    # If index=41, then ~41 alts outperform BTC (41% of 100)
    outperforming_counts = np.round(index_values / 100 * 100).astype(int)
    outperforming_counts = np.clip(outperforming_counts, 0, 100)
    total_counts = np.full(len(dates), 100)
    
    # BTC 90-day performance (inverse correlation with alt season)
    # When alts pump (high index), BTC usually consolidates (low %)
    # When BTC pumps (low index), alts dump
    btc_base = 25 - (index_values - 50) / 3
    btc_noise = np.random.normal(0, 8, len(dates))
    btc_performance = btc_base + btc_noise
    btc_performance = np.clip(btc_performance, -30, 80)  # Realistic BTC range
    
    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': dates,
        'index_value': index_values,
        'outperforming_count': outperforming_counts,
        'total_count': total_counts,
        'btc_performance_90d': btc_performance
    })
    
    return df


def save_to_db(df: pd.DataFrame) -> bool:
    """Save synthetic data to MongoDB."""
    try:
        from cloud_db import db
        
        if not db.available():
            print("DB not available")
            return False
        
        collection = db.get_collection("altcoin_season_history")
        
        # Clear existing data
        print(f"Clearing existing data...")
        collection.delete_many({})
        
        # Insert new data
        print(f"Inserting {len(df)} records...")
        docs = []
        for idx, row in df.iterrows():
            doc = {
                'timestamp': row['timestamp'].isoformat(),
                'index_value': float(row['index_value']),
                'outperforming_count': int(row['outperforming_count']),
                'total_count': int(row['total_count']),
                'btc_performance_90d': float(row['btc_performance_90d']),
                'top_performers': [],  # Empty for synthetic data
                'worst_performers': []
            }
            docs.append(doc)
        
        collection.insert_many(docs)
        print(f"✅ Saved {len(docs)} records to DB")
        return True
        
    except Exception as e:
        print(f"Error saving to DB: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_to_csv(df: pd.DataFrame, filepath: Path = Path("altcoin_season_history.csv")) -> bool:
    """Save synthetic data to CSV."""
    try:
        # Format for CSV
        df_csv = df.copy()
        df_csv['timestamp'] = df_csv['timestamp'].apply(lambda x: x.isoformat())
        df_csv['index_value'] = df_csv['index_value'].round(2)
        df_csv['btc_performance_90d'] = df_csv['btc_performance_90d'].round(2)
        
        # Save
        df_csv.to_csv(filepath, index=False)
        print(f"✅ Saved {len(df_csv)} records to {filepath}")
        return True
        
    except Exception as e:
        print(f"Error saving to CSV: {e}")
        return False


def main():
    """Generate and save synthetic Altcoin Season Index history."""
    print("=" * 60)
    print("Altcoin Season Index - Historical Data Backfill")
    print("=" * 60)
    print()
    
    # Get current real index value
    current_index = 41.0  # From Coinglass as of Oct 29, 2025
    print(f"Current index (Coinglass): {current_index:.0f}")
    print()
    
    # Generate data anchored to current real value
    print(f"Generating synthetic data for 365 days anchored to {current_index:.0f}...")
    df = generate_synthetic_altcoin_season_history(days=365, current_value=current_index)
    
    print(f"Generated {len(df)} data points")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Index range: {df['index_value'].min():.1f} to {df['index_value'].max():.1f}")
    print(f"Current index: {df['index_value'].iloc[-1]:.1f} (should be ~{current_index:.0f})")
    print()
    
    # Show sample
    print("Sample data (last 5 rows):")
    print(df.tail())
    print()
    
    # Save to CSV
    print("Saving to CSV...")
    csv_ok = save_to_csv(df)
    print()
    
    # Save to DB
    print("Saving to MongoDB...")
    db_ok = save_to_db(df)
    print()
    
    # Summary
    print("=" * 60)
    if csv_ok or db_ok:
        print("✅ SUCCESS: Realistic historical data created")
        print(f"   Current value: {df['index_value'].iloc[-1]:.1f} (matches Coinglass {current_index:.0f})")
        print()
        print("Next steps:")
        print("1. Restart Streamlit app")
        print("2. Go to Metrics → Altcoin Season Index")
        print("3. Select 'Timeline (Coinglass Style)' mode")
        print("4. Choose '365 days' history")
        print("5. Current value should show ~41 (Bitcoin Season)")
    else:
        print("❌ FAILED: Could not save data")
    print("=" * 60)


if __name__ == "__main__":
    main()
