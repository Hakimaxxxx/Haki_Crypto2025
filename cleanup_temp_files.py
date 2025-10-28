"""
Temp File Cleanup Utility

Automatically cleans up orphaned temporary files created by portfolio_history.py
and other modules that use tempfile.mkstemp().

These .tmp_* files should be deleted after successful atomic writes,
but may remain if exceptions occur or app crashes.
"""
import os
import time
from pathlib import Path

def cleanup_temp_files(directory: str = ".", max_age_hours: int = 24, dry_run: bool = False):
    """
    Remove temporary files older than specified age.
    
    Args:
        directory: Directory to search for temp files
        max_age_hours: Maximum age in hours before deletion
        dry_run: If True, only print what would be deleted without actually deleting
    
    Returns:
        Tuple of (files_deleted, bytes_freed)
    """
    pattern = ".tmp_*"
    max_age_seconds = max_age_hours * 3600
    now = time.time()
    
    deleted_count = 0
    bytes_freed = 0
    
    temp_files = list(Path(directory).glob(pattern))
    
    if not temp_files:
        print(f"No temp files found matching {pattern}")
        return 0, 0
    
    print(f"Found {len(temp_files)} temp files")
    
    for temp_file in temp_files:
        try:
            # Get file stats
            stat = temp_file.stat()
            age_seconds = now - stat.st_mtime
            age_hours = age_seconds / 3600
            size_mb = stat.st_size / (1024 * 1024)
            
            if age_seconds > max_age_seconds:
                if dry_run:
                    print(f"[DRY RUN] Would delete: {temp_file.name} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                else:
                    temp_file.unlink()
                    print(f"Deleted: {temp_file.name} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                    deleted_count += 1
                    bytes_freed += stat.st_size
            else:
                print(f"Keeping: {temp_file.name} (age: {age_hours:.1f}h, too recent)")
                
        except Exception as e:
            print(f"Error processing {temp_file.name}: {e}")
    
    if not dry_run and deleted_count > 0:
        print(f"\n✅ Cleanup complete:")
        print(f"   Files deleted: {deleted_count}")
        print(f"   Space freed: {bytes_freed / (1024*1024):.2f} MB")
    elif dry_run:
        print(f"\n[DRY RUN] Would delete {deleted_count} files, freeing {bytes_freed / (1024*1024):.2f} MB")
    
    return deleted_count, bytes_freed


def cleanup_all_temp_files_force(directory: str = "."):
    """
    Force delete ALL temp files regardless of age.
    Use with caution - may delete files from running operations.
    
    Returns:
        Tuple of (files_deleted, bytes_freed)
    """
    pattern = ".tmp_*"
    deleted_count = 0
    bytes_freed = 0
    
    temp_files = list(Path(directory).glob(pattern))
    
    if not temp_files:
        print(f"No temp files found")
        return 0, 0
    
    print(f"⚠️  FORCE DELETE: Found {len(temp_files)} temp files")
    
    for temp_file in temp_files:
        try:
            size = temp_file.stat().st_size
            temp_file.unlink()
            print(f"Deleted: {temp_file.name} ({size / (1024*1024):.2f} MB)")
            deleted_count += 1
            bytes_freed += size
        except Exception as e:
            print(f"Failed to delete {temp_file.name}: {e}")
    
    print(f"\n✅ Force cleanup complete:")
    print(f"   Files deleted: {deleted_count}")
    print(f"   Space freed: {bytes_freed / (1024*1024):.2f} MB")
    
    return deleted_count, bytes_freed


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up temporary files")
    parser.add_argument("--max-age", type=int, default=24, help="Maximum age in hours (default: 24)")
    parser.add_argument("--force", action="store_true", help="Delete all temp files regardless of age")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--dir", type=str, default=".", help="Directory to search (default: current)")
    
    args = parser.parse_args()
    
    if args.force:
        if args.dry_run:
            print("⚠️  Cannot use --force with --dry-run")
        else:
            confirm = input("⚠️  This will DELETE ALL temp files. Continue? (yes/no): ")
            if confirm.lower() == "yes":
                cleanup_all_temp_files_force(args.dir)
            else:
                print("Aborted.")
    else:
        cleanup_temp_files(args.dir, args.max_age, args.dry_run)
