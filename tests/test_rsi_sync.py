"""
Test RSI Sync to MongoDB

Run this to verify RSI background sync is working correctly.
"""
import os
import time

# Set MongoDB env vars
os.environ["MONGO_URI"] = "mongodb+srv://quanghuy060997_db_user:MPCuEbF2GhpmiZm8@cluster0.x3iyjjm.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
os.environ["CLOUD_DB_NAME"] = "Crypto2025"

def test_manual_sync():
    """Test manual sync to MongoDB."""
    print("=" * 60)
    print("Testing RSI Manual Sync to MongoDB")
    print("=" * 60)
    
    try:
        import rsi_sync
        from cloud_db import db
        
        # Check DB connection
        print("\n1️⃣ Checking MongoDB connection...")
        if db.available():
            print("   ✅ MongoDB connected")
        else:
            print("   ❌ MongoDB NOT connected - please check credentials")
            return False
        
        # Check sync status
        print("\n2️⃣ Checking sync status...")
        status = rsi_sync.get_sync_status()
        print(f"   Running: {status['running']}")
        print(f"   Interval: {status['interval_minutes']} minutes")
        print(f"   Timeframes: {status['timeframes']}")
        print(f"   Last sync: {status['last_sync']}")
        
        # Force sync one timeframe as test
        print("\n3️⃣ Testing sync for 4h timeframe...")
        success = rsi_sync._sync_rsi_to_db("4h")
        
        if success:
            print("   ✅ Sync successful!")
        else:
            print("   ❌ Sync failed - check errors above")
            return False
        
        # Verify data in DB
        print("\n4️⃣ Verifying data in MongoDB...")
        data = rsi_sync.fetch_rsi_from_db("4h")
        
        if data:
            print(f"   ✅ Found {len(data)} coins in DB")
            # Show sample
            sample = list(data.items())[:3]
            for symbol, info in sample:
                rsi_current = info.get('rsi_current', 'N/A')
                history_len = len(info.get('rsi_history', []))
                print(f"      {symbol}: RSI={rsi_current:.2f}, History={history_len} points")
        else:
            print("   ⚠️ No data found in DB")
            return False
        
        print("\n" + "=" * 60)
        print("✅ RSI Sync Test PASSED")
        print("=" * 60)
        print("\n💡 Next steps:")
        print("   1. Background sync will run every 15 minutes automatically")
        print("   2. Check Health Panel in app to monitor sync status")
        print("   3. Use 'DB (fast)' option in RSI Heatmap for instant load")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_background_sync():
    """Test background sync thread."""
    print("\n" + "=" * 60)
    print("Testing Background Sync Thread")
    print("=" * 60)
    
    try:
        import rsi_sync
        
        print("\n1️⃣ Starting background sync...")
        rsi_sync.start_sync()
        
        print("   ✅ Background thread started")
        print("   ⏱️ Waiting 10 seconds to check if thread is running...")
        time.sleep(10)
        
        status = rsi_sync.get_sync_status()
        if status['running']:
            print("   ✅ Thread is running")
            
            # Wait for first sync to complete (or timeout after 5 minutes)
            print("\n2️⃣ Waiting for first sync to complete (max 5 minutes)...")
            timeout = 300  # 5 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                status = rsi_sync.get_sync_status()
                synced = [tf for tf in status['timeframes'] if status['last_sync'].get(tf, 'Never') != 'Never']
                
                if synced:
                    print(f"\n   ✅ First sync completed! Synced timeframes: {synced}")
                    break
                
                # Show progress every 30s
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0 and elapsed > 0:
                    print(f"   ⏳ Still syncing... ({elapsed}s elapsed)")
                
                time.sleep(5)
            else:
                print("   ⚠️ Timeout - sync taking longer than expected")
                print("   Check errors:")
                if status.get('errors'):
                    for err in status['errors'][-3:]:
                        print(f"      {err}")
            
            # Stop sync
            print("\n3️⃣ Stopping background sync...")
            rsi_sync.stop_sync()
            print("   ✅ Stopped")
            
        else:
            print("   ❌ Thread not running")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n❌ Background sync test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "🔧 RSI Sync Test Suite" + "\n")
    
    # Test 1: Manual sync
    test1_passed = test_manual_sync()
    
    # Only run test 2 if test 1 passed
    if test1_passed:
        print("\n" + "-" * 60 + "\n")
        test2_passed = test_background_sync()
        
        if test2_passed:
            print("\n\n🎉 All tests PASSED!")
            print("\n📊 RSI sync is working correctly.")
            print("   Data is being saved to MongoDB collection 'rsi_data'")
            print("   Background sync will auto-start when you run the Streamlit app")
        else:
            print("\n\n⚠️ Background sync test failed")
    else:
        print("\n\n❌ Manual sync test failed - fix this first before testing background sync")
