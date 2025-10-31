# Scripts Directory

This directory contains utility scripts, debug tools, and maintenance scripts for the Crypto2025 project.

## Organization

### Debug Scripts (`debug_*.py`)
Tools for debugging specific features:
- `debug_ada.py` - Debug ADA-specific issues
- `debug_cache.py` - Cache debugging
- `debug_db.py` - Database debugging
- `debug_kv.py` - Key-value store debugging
- `debug_ohlcv.py` - OHLCV data debugging
- `debug_okx_api.py` - OKX API debugging
- `debug_redis.py` - Redis cache debugging

### Check Scripts (`check_*.py`)
Verification and validation tools:
- `check_altcoin_data.py` - Verify altcoin data integrity
- `check_coinmarketcap_connection.py` - Test CMC API connection
- `check_db_data.py` - Database data verification
- `check_whale_files.py` - Whale alert file validation

### Cleanup Scripts (`cleanup_*.py`, `clean_*.py`)
Maintenance and cleanup utilities:
- `cleanup_zero_values.py` - Remove zero values from DB
- `clean_portfolio_history_large.py` - Clean large portfolio files

### Utility Scripts
Various utility tools:
- `db_bootstrap.py` - Bootstrap database with initial data
- `examine_whale_data.py` - Analyze whale alert data
- `fetch_and_extract_sol_transfer.py` - SOL chain data extraction
- `filter_sol_whale_history.py` - Filter SOL whale alerts
- `fix_*.py` - Various fix utilities
- `quick_redis_ping.py` - Quick Redis connection test

## Usage

Run any script directly:
```bash
python scripts/script_name.py
```

Most scripts are self-documenting - check the file header for usage instructions.

## Guidelines

1. **Naming Conventions**:
   - Debug tools: `debug_<feature>.py`
   - Checks: `check_<what>.py`
   - Cleanup: `cleanup_<what>.py` or `clean_<what>.py`
   - Utilities: Descriptive name with `_` separators

2. **Documentation**:
   - Always include docstring at top
   - Explain purpose and usage
   - Document any command-line arguments

3. **Safety**:
   - Scripts that modify data should ask for confirmation
   - Use `--dry-run` flag for destructive operations
   - Log what the script is doing

4. **Dependencies**:
   - Import only what's needed
   - Handle missing dependencies gracefully
   - Document any special requirements

## Adding New Scripts

When creating a new script:
1. Choose appropriate naming convention
2. Add comprehensive docstring
3. Include usage examples in comments
4. Make it executable and standalone
5. Update this README if it's a new category

## Root Directory Rule

**⚠️ IMPORTANT**: All utility, debug, and maintenance scripts MUST be created in this `scripts/` directory, NOT in the project root. This keeps the root directory clean and organized.
