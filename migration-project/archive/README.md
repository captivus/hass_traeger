# Migration Scripts Archive

This directory contains all scripts used during the data migration process.

## Directory Structure

### `/analysis/`
Scripts used for initial database analysis and migration planning:
- `analyze_databases.py` - Initial schema comparison
- `analyze_migration_candidates.py` - Deep analysis revealing 3,865 messages
- `analyze_overlap_detail.py` - Overlap period analysis
- `analyze_duplicate_breakdown.py` - Duplicate detection logic
- `analyze_probe_data.py` - Probe channel analysis

### `/debug/`
Scripts created during post-migration debugging:
- `debug_june22.py` - Initial investigation of "missing" data
- `check_june22_times.py` - Timestamp analysis
- `verify_june22_visibility.py` - API visibility testing
- `debug_api_query.py` - Timestamp format issue discovery
- `cook_summary.py` - Comprehensive cook data summary

### `/core/`
Core migration scripts:
- `migrate_raw_messages.py` - Main migration script with safety features
- `validate_migration.py` - Post-migration validation

## Key Findings
- Migration was 100% successful
- Timestamp format mismatch causes UI visibility issues
- All probe data correctly migrated