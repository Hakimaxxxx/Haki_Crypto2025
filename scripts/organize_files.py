"""
Auto-cleanup script for misplaced test/debug files

Moves test/debug/utility files from root to appropriate directories.
Run this after AI agent creates files in wrong location.

Usage:
    python scripts/organize_files.py [--dry-run]
"""

import os
import shutil
from pathlib import Path

# Define file patterns and their destinations
FILE_PATTERNS = {
    'test_*.py': 'tests',
    'debug_*.py': 'scripts',
    'check_*.py': 'scripts',
    'cleanup_*.py': 'scripts',
    'clean_*.py': 'scripts',
    'examine_*.py': 'scripts',
    'filter_*.py': 'scripts',
    'fix_*.py': 'scripts',
    'fetch_*.py': 'scripts',
    'quick_*.py': 'scripts',
}

# Files to keep in root (exceptions)
KEEP_IN_ROOT = {
    'cleanup_temp_files.py',  # Called by app_init.py
}

def organize_files(dry_run=False):
    """Move misplaced files to correct directories."""
    root = Path('.')
    moved_count = 0
    
    print("=" * 70)
    print("File Organization Script")
    print("=" * 70)
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No files will be moved\n")
    
    for pattern, dest_dir in FILE_PATTERNS.items():
        # Find files matching pattern in root
        files = list(root.glob(pattern))
        
        # Filter out exceptions
        files = [f for f in files if f.name not in KEEP_IN_ROOT]
        
        if not files:
            continue
        
        # Create destination directory if needed
        dest_path = root / dest_dir
        if not dry_run and not dest_path.exists():
            dest_path.mkdir(parents=True)
            print(f"📁 Created directory: {dest_dir}/")
        
        # Move files
        for file_path in files:
            dest_file = dest_path / file_path.name
            
            if dry_run:
                print(f"   Would move: {file_path.name} → {dest_dir}/")
            else:
                try:
                    shutil.move(str(file_path), str(dest_file))
                    print(f"✅ Moved: {file_path.name} → {dest_dir}/")
                    moved_count += 1
                except Exception as e:
                    print(f"❌ Error moving {file_path.name}: {e}")
    
    print("\n" + "=" * 70)
    if dry_run:
        print(f"🔍 Dry run complete - {len([f for p in FILE_PATTERNS for f in root.glob(p) if f.name not in KEEP_IN_ROOT])} files would be moved")
    else:
        print(f"✅ Organization complete - {moved_count} files moved")
    print("=" * 70)
    
    # Show current organization
    print("\n📊 Current Organization:")
    print(f"   tests/   : {len(list(Path('tests').glob('*.py')))} files")
    print(f"   scripts/ : {len(list(Path('scripts').glob('*.py')))} files")
    
    # Check for remaining misplaced files
    remaining = []
    for pattern in FILE_PATTERNS.keys():
        remaining.extend([f for f in root.glob(pattern) if f.name not in KEEP_IN_ROOT])
    
    if remaining:
        print(f"\n⚠️  Still {len(remaining)} files in root:")
        for f in remaining[:5]:  # Show first 5
            print(f"   - {f.name}")
        if len(remaining) > 5:
            print(f"   ... and {len(remaining) - 5} more")
    else:
        print("\n✅ Root directory is clean!")

if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    organize_files(dry_run=dry_run)
