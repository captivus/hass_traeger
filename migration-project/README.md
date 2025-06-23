# Traeger Data Migration Project

## Overview
This project migrates historical raw message data from the legacy Traeger Stream application database to the new simplified Traeger Monitor database.

## Goal
Preserve historical cook data (180 messages from before 2025-05-30) without creating duplicates, allowing the new system to have complete historical context.

## Files
- `analyze_databases.py` - Initial database schema analysis
- `analyze_detailed.py` - Detailed analysis of both databases
- `check_overlap.py` - Overlap and duplicate detection
- `analyze_overlap_detail.py` - Detailed overlap period analysis
- `migrate_raw_messages.py` - Main migration script with safety features

## Migration Summary
- **Legacy DB**: 4,537 messages (2025-05-26 to 2025-06-22)
- **New DB**: 2,759 messages (2025-05-30 to 2025-06-22)
- **To Migrate**: 180 messages from before overlap
- **Duplicates to Skip**: 672 (based on state_index)

## Usage
```bash
cd /workspaces/hass_traeger/migration-project
python migrate_raw_messages.py
```

The script will:
1. Run a dry-run first (no changes)
2. Ask for confirmation
3. Create a backup of the new database
4. Migrate non-duplicate messages
5. Report results

## Safety Features
- Dry-run mode
- Automatic backup
- Transaction-based (rollback on error)
- Duplicate detection
- JSON validation