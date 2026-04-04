#!/usr/bin/env python3
"""
Production Wrapper for Dashboard Generation
Adds error handling, logging, retries, and recovery mechanisms
"""

import sys
import subprocess
import os
import time
import json
import shutil
from datetime import datetime
from pathlib import Path

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds
BACKUP_DIR = Path("backups")
LOG_FILE = Path("production.log")

def log(message, level="INFO"):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] [{level}] {message}"
    print(log_message)

    # Also write to log file
    with open(LOG_FILE, "a") as f:
        f.write(log_message + "\n")

def run_script_with_retry(script_name, description, max_retries=MAX_RETRIES):
    """Run a Python script with retry logic"""
    for attempt in range(1, max_retries + 1):
        try:
            log(f"Running {description} (attempt {attempt}/{max_retries})")
            result = subprocess.run(
                ["python3", script_name],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode == 0:
                log(f"✅ {description} completed successfully")
                if result.stdout:
                    log(f"Output: {result.stdout[:500]}")  # First 500 chars
                return True
            else:
                log(f"❌ {description} failed with exit code {result.returncode}", "ERROR")
                log(f"Error output: {result.stderr}", "ERROR")

                if attempt < max_retries:
                    log(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return False

        except subprocess.TimeoutExpired:
            log(f"❌ {description} timed out after 10 minutes", "ERROR")
            if attempt < max_retries:
                log(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                return False

        except Exception as e:
            log(f"❌ {description} raised exception: {e}", "ERROR")
            if attempt < max_retries:
                log(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                return False

    return False

def backup_existing_dashboard():
    """Backup existing dashboard HTML if it exists"""
    dashboard_file = Path("simple_daily_dashboard_interactive.html")

    if not dashboard_file.exists():
        log("No existing dashboard to backup")
        return None

    # Create backup directory
    BACKUP_DIR.mkdir(exist_ok=True)

    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"dashboard_backup_{timestamp}.html"

    try:
        shutil.copy2(dashboard_file, backup_file)
        log(f"✅ Backed up existing dashboard to {backup_file}")

        # Keep only last 7 backups
        cleanup_old_backups()

        return backup_file
    except Exception as e:
        log(f"⚠️ Warning: Could not backup dashboard: {e}", "WARNING")
        return None

def cleanup_old_backups(keep_count=7):
    """Keep only the most recent N backups"""
    if not BACKUP_DIR.exists():
        return

    backups = sorted(BACKUP_DIR.glob("dashboard_backup_*.html"), reverse=True)

    if len(backups) > keep_count:
        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
                log(f"Deleted old backup: {old_backup}")
            except Exception as e:
                log(f"Could not delete old backup {old_backup}: {e}", "WARNING")

def restore_from_backup(backup_file):
    """Restore dashboard from backup"""
    if backup_file and backup_file.exists():
        dashboard_file = Path("simple_daily_dashboard_interactive.html")
        try:
            shutil.copy2(backup_file, dashboard_file)
            log(f"✅ Restored dashboard from backup: {backup_file}")
            return True
        except Exception as e:
            log(f"❌ Failed to restore from backup: {e}", "ERROR")
            return False
    return False

def validate_output():
    """Validate generated dashboard"""
    dashboard_file = Path("simple_daily_dashboard_interactive.html")

    if not dashboard_file.exists():
        log("❌ Dashboard file was not generated", "ERROR")
        return False

    # Check file size (should be > 100KB)
    file_size = dashboard_file.stat().st_size
    if file_size < 100000:
        log(f"❌ Dashboard file is too small ({file_size} bytes)", "ERROR")
        return False

    # Check for expected content
    try:
        with open(dashboard_file, 'r', encoding='utf-8') as f:
            content = f.read(10000)  # Read first 10KB

            if "FE App Dashboard" not in content:
                log("❌ Dashboard content validation failed", "ERROR")
                return False

        log(f"✅ Dashboard validated (size: {file_size:,} bytes)")
        return True

    except Exception as e:
        log(f"❌ Could not validate dashboard: {e}", "ERROR")
        return False

def create_status_report(success, start_time, backup_file=None):
    """Create a status report JSON"""
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    status = {
        "success": success,
        "timestamp": end_time.isoformat(),
        "duration_seconds": duration,
        "backup_file": str(backup_file) if backup_file else None,
        "dashboard_exists": Path("simple_daily_dashboard_interactive.html").exists()
    }

    # Add file sizes
    if Path("simple_daily_dashboard_interactive.html").exists():
        status["dashboard_size"] = Path("simple_daily_dashboard_interactive.html").stat().st_size

    if Path("data/latest_hive_data.csv").exists():
        status["ticket_data_size"] = Path("data/latest_hive_data.csv").stat().st_size

    if Path("data/latest_funnel_transformed.csv").exists():
        status["funnel_data_size"] = Path("data/latest_funnel_transformed.csv").stat().st_size

    with open("production_status.json", "w") as f:
        json.dump(status, f, indent=2)

    log(f"Status report created: {status}")

def main():
    """Main production wrapper"""
    start_time = datetime.now()
    log("=" * 80)
    log("PRODUCTION DASHBOARD GENERATION STARTED")
    log("=" * 80)

    # Step 1: Backup existing dashboard
    backup_file = backup_existing_dashboard()

    # Step 2: Fetch ticket data (using improved version with custom filters)
    if not run_script_with_retry("fetch_from_trino_improved.py", "Fetch ticket data"):
        log("❌ CRITICAL: Failed to fetch ticket data", "ERROR")
        create_status_report(False, start_time, backup_file)
        sys.exit(1)

    # Step 3: Fetch agent funnel data
    if not run_script_with_retry("fetch_agent_funnel_from_trino.py", "Fetch agent funnel data"):
        log("❌ CRITICAL: Failed to fetch agent funnel data", "ERROR")
        create_status_report(False, start_time, backup_file)
        sys.exit(1)

    # Step 4: Transform funnel data
    if not run_script_with_retry("transform_funnel_data.py", "Transform funnel data", max_retries=2):
        log("❌ CRITICAL: Failed to transform funnel data", "ERROR")
        create_status_report(False, start_time, backup_file)
        sys.exit(1)

    # Step 5: Create MTD comparison views
    if not run_script_with_retry("create_mtd_comparison_views.py", "Create MTD views", max_retries=2):
        log("⚠️ WARNING: Failed to create MTD views, continuing anyway", "WARNING")
        # Don't exit, MTD views are optional

    # Step 6: Generate dashboard
    if not run_script_with_retry("simple_daily_dashboard_interactive.py", "Generate dashboard", max_retries=2):
        log("❌ CRITICAL: Failed to generate dashboard", "ERROR")

        # Try to restore from backup
        if backup_file:
            log("Attempting to restore from backup...")
            if restore_from_backup(backup_file):
                log("✅ Dashboard restored from backup")
                create_status_report(False, start_time, backup_file)
                sys.exit(1)  # Still exit with error since generation failed

        create_status_report(False, start_time, backup_file)
        sys.exit(1)

    # Step 7: Validate output
    if not validate_output():
        log("❌ CRITICAL: Dashboard validation failed", "ERROR")

        # Try to restore from backup
        if backup_file:
            log("Attempting to restore from backup...")
            restore_from_backup(backup_file)

        create_status_report(False, start_time, backup_file)
        sys.exit(1)

    # Success!
    log("=" * 80)
    log("✅ PRODUCTION DASHBOARD GENERATION COMPLETED SUCCESSFULLY")
    log("=" * 80)

    duration = (datetime.now() - start_time).total_seconds()
    log(f"Total duration: {duration:.2f} seconds")

    create_status_report(True, start_time, backup_file)
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ Process interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        log(f"❌ FATAL ERROR: {e}", "ERROR")
        import traceback
        log(traceback.format_exc(), "ERROR")
        sys.exit(1)
