import os
import pandas as pd
from metrics_dominance import get_dominance_data

import requests
url = "https://api.coingecko.com/api/v3/global"
response = requests.get(url, timeout=15)
print(response.status_code, response.json())

def test_save_dominance_to_csv():
    """Test if dominance data can be saved to a CSV file."""
    # Fetch dominance data
    df = get_dominance_data()

    # Check if data is not empty
    if df.empty:
        print("Test failed: No data fetched.")
        return

    # Define test CSV file path
    test_csv_path = "test_dominance_output.csv"

    try:
        # Save to CSV
        df.to_csv(test_csv_path, index=False)

        # Verify file exists
        if not os.path.exists(test_csv_path):
            print("Test failed: CSV file was not created.")
            return

        # Verify content
        loaded_df = pd.read_csv(test_csv_path)
        if loaded_df.empty or not all(col in loaded_df.columns for col in ["timestamp", "BTC", "ETH", "Others"]):
            print("Test failed: CSV content is invalid.")
            return

        print("Test passed: Dominance data saved and verified successfully.")
    finally:
        # Clean up test file
        if os.path.exists(test_csv_path):
            os.remove(test_csv_path)

if __name__ == "__main__":
    test_save_dominance_to_csv()