#!/usr/bin/env python3
"""
Execute the actual migration (non-interactive version).
"""
import sys
from migrate_raw_messages import migrate_raw_messages, backup_database

def main():
    legacy_db = "/workspaces/hass_traeger/traeger-stream/data/traeger_data.db"
    new_db = "/workspaces/hass_traeger/traeger-monitor/data/traeger.db"
    
    # Backup the new database
    print("\nCreating backup before migration...")
    backup_path = backup_database(new_db)
    
    # Perform actual migration
    print("\nExecuting actual migration...")
    migrate_raw_messages(legacy_db, new_db, dry_run=False)
    
    print(f"\nMigration complete! Backup saved at: {backup_path}")

if __name__ == "__main__":
    main()