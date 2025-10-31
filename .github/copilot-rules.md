# Copilot Agent Rules for Crypto2025 Project

## File Organization Rules

### ⚠️ CRITICAL: Never create test/debug files in root directory

**All test and utility files MUST be created in appropriate subdirectories:**

1. **Test files** (`test_*.py`):
   - ✅ CORRECT: `tests/test_feature.py`
   - ❌ WRONG: `test_feature.py` (root)

2. **Debug files** (`debug_*.py`):
   - ✅ CORRECT: `scripts/debug_feature.py`
   - ❌ WRONG: `debug_feature.py` (root)

3. **Check/Verify files** (`check_*.py`):
   - ✅ CORRECT: `scripts/check_feature.py`
   - ❌ WRONG: `check_feature.py` (root)

4. **Utility scripts** (`fix_*.py`, `cleanup_*.py`, `examine_*.py`, `filter_*.py`):
   - ✅ CORRECT: `scripts/utility_name.py`
   - ❌ WRONG: `utility_name.py` (root)

5. **One-off scripts** (fetch, quick test, etc.):
   - ✅ CORRECT: `scripts/script_name.py`
   - ❌ WRONG: `script_name.py` (root)

### Directory Structure

```
d:\Crypto\
├── tests/              # All test_*.py files
├── scripts/            # All debug_*.py, check_*.py, utility scripts
├── docs/               # Documentation
├── .github/            # GitHub config, prompts, workflows
├── [Chain folders]/    # BTC/, ETH/, SOL/, etc. - chain-specific scanners
└── [Core modules]/     # Main application files (Crypto2025.py, metrics_*.py, etc.)
```

### Root Directory - Keep Clean!

**Only these types of files should be in root:**
- Main application: `Crypto2025.py`
- Core modules: `metrics_*.py`, `overlay_*.py`, `portfolio_*.py`
- Configuration: `config.py`, `requirements.txt`, `README.md`
- Database/Cloud: `cloud_db.py`, `db_utils.py`
- Cache/Storage: `redis_cache.py`, `price_utils.py`
- Initialization: `app_init.py`
- Data files: `*.json`, `*.csv` (runtime data)

**Never create in root:**
- Test files
- Debug scripts
- Utility scripts
- Temporary experimental code
- One-off verification scripts

## Code Quality Rules

### Performance
- Avoid heavy computations in Streamlit pages (use caching)
- Move intensive features to dedicated pages (e.g., Liquidation Heatmap → Futures page)
- Clean up temporary files on app startup

### Data Management
- Use `app_init.py` for data access (don't read files directly)
- Atomic writes for JSON files (use `portfolio_history.py` helpers)
- Always handle DB fallback to local files

### Error Handling
- All API calls must have try/except
- Show user-friendly error messages in Streamlit
- Log errors to `_APP_STATE["errors"]` for diagnostics

### Naming Conventions
- Metrics modules: `metrics_<feature>.py`
- Overlay modules: `overlay_<feature>.py`
- Chain scanners: `<CHAIN>/metrics_<chain>_whale_alert_realtime.py`
- Test files: `tests/test_<feature>.py`
- Scripts: `scripts/<purpose>_<description>.py`

## Before Creating Any File

**Ask yourself:**
1. Is this a test file? → Put in `tests/`
2. Is this a debug/utility script? → Put in `scripts/`
3. Is this a core module? → Only then put in root
4. Does it already exist? → Search before creating

## Migration History

**2025-10-29**: Migrated all test/debug/utility files from root to organized structure
- 9 test files → `tests/`
- 7 debug files → `scripts/`
- 4 check files → `scripts/`
- 10+ utility scripts → `scripts/`

**Keep root clean for maintainability!**
