def sync_ada_data():
    """Ensure ADA data is synchronized between DB, cache, and API."""
    try:
        from cloud_db import db
        
        # Fetch ADA data from DB
        ada_data = db.find("portfolio_history", {"coin": "cardano"})
        if ada_data:
            print(f"[DEBUG] ADA data from DB: {ada_data}")
            _DATA_CACHE["ada"] = ada_data
        else:
            print("[WARNING] ADA data not found in DB.")

        # Fetch ADA price from API
        from price_utils import fetch_prices_and_changes
        prices, _, success, msg = fetch_prices_and_changes(["cardano"], force=True)
        if success and "cardano" in prices:
            _DATA_CACHE["ada_price"] = prices["cardano"]
            print(f"[DEBUG] ADA price from API: {prices['cardano']}")
        else:
            print(f"[WARNING] Failed to fetch ADA price from API: {msg}")

    except Exception as e:
        print(f"[ERROR] ADA data sync error: {e}")

# Call sync_ada_data during initialization
sync_ada_data()