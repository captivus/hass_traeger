# Traeger Legacy Data Migration Plan

## Quick Start for New Engineers

If you're starting fresh with just this plan:

1. **Create migration directory**:
   ```bash
   mkdir -p /workspaces/hass_traeger/migration-project
   cd /workspaces/hass_traeger/migration-project
   ```

2. **Create tracking files** using templates in the "Work Tracking Setup" section below

3. **Get the migration script** from the appendix at the end of this document

4. **Follow the Implementation Plan** starting with Phase 2 (Phase 1 is already complete)

## Executive Summary

This plan outlines the migration of historical raw message data from the legacy Traeger Stream application to the new simplified Traeger Monitor system. The migration will preserve 3,865 unique historical messages, dramatically expanding the historical dataset available for temperature predictions while avoiding any duplicate data.

## Project Overview

### Objective
Migrate pre-overlap historical data from legacy system to new system while maintaining data integrity and avoiding duplication.

### Scope
- **In Scope**: All unique raw message data from `traeger-stream/data/traeger_data.db` not already in new system
- **Out of Scope**: 
  - Schema changes (both use identical schema)
  - Application code modifications
  - Messages with duplicate stateIndex values (true duplicates)

### Timeline
- Estimated Duration: 30-45 minutes
- Analysis Phase: ✅ Complete
- Execution Phase: Ready to start
- Validation Phase: 10 minutes post-migration

## Technical Analysis

### Database Comparison

| Aspect | Legacy Database | New Database |
|--------|----------------|--------------|
| Location | `traeger-stream/data/traeger_data.db` | `traeger-monitor/data/traeger.db` |
| Schema | Identical `raw_messages` table | Same |
| Total Messages | 4,537 | 2,759 |
| Date Range | 2025-05-26 to 2025-06-22 | 2025-05-30 to 2025-06-22 |
| State Index Range | 1827677 to 1910060 | 0 to 1861456 |

### Data Analysis Results
- **Overlap Period**: 2025-05-30 16:22:04 to 2025-06-22 20:34:10
- **Messages to Migrate**: 3,865 total
  - Before overlap: 180
  - During overlap (unique): 3,685
  - After new DB ends: 0
- **True Duplicates**: 672 (matching stateIndex = same grill state)
- **Expected Final Count**: 6,624 (2,759 + 3,865)

## Key Discovery: Overlap Period Contains Unique Data

During detailed analysis, we discovered that the "overlap" period (2025-05-30 to 2025-06-22) contains significant unique data:

- **Legacy system**: 4,357 messages during overlap
- **New system**: 2,719 messages during overlap  
- **True duplicates**: Only 672 messages

This means 3,685 messages during the overlap were captured by the legacy system but NOT by the new system. Possible reasons:
- Different connection stability
- Different message polling/subscription rates
- Periods where one system was offline
- Network issues affecting one system but not the other

This dramatically increases the value of the migration - we're recovering 3,865 unique state updates that would otherwise be lost.

## Migration Strategy

### Approach
1. **Comprehensive Migration**: Migrate ALL messages except true duplicates
2. **Deduplication**: Use state_index as primary key (represents unique grill states)
3. **Validation**: JSON payload validation before insertion
4. **Safety First**: Dry-run, backup, transaction-based execution

### Deduplication Logic
```python
# Primary deduplication - stateIndex uniquely identifies grill states
if state_index in existing_state_indexes:
    skip_message()  # This is the same grill state update

# Secondary deduplication - for messages without state_index
if (timestamp, topic) in existing_timestamp_topics:
    skip_message()
```

**Why stateIndex is the key:**
- It's a counter from the grill itself that increments with each state update
- Messages with the same stateIndex contain identical grill data (temps, times, etc.)
- Only the system timestamps differ (when each monitor received the message)
- Example: stateIndex 1859679 has grill time 1749147577 in both systems

### Data Validation
- JSON payload must be valid
- Timestamp must be valid datetime
- State_index can be NULL but must be unique if present

## Risk Analysis

### Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Data Corruption | Low | High | Transaction-based migration with rollback |
| Duplicate Creation | Low | Medium | Two-layer deduplication logic |
| Application Disruption | Very Low | High | No code changes, only data addition |
| Missing Historical Data | Low | Low | Comprehensive analysis completed |

### Rollback Plan
1. If migration fails during execution → Automatic transaction rollback
2. If issues found post-migration → Restore from automatic backup
3. Backup naming: `traeger.db.backup_YYYYMMDD_HHMMSS`

## Work Tracking Setup

### Creating the Tracking System

Before starting the migration, create these tracking files in your migration directory:

#### 1. MIGRATION_LOG.md
Create this file with initial status:
```markdown
# Migration Work Log

## Status: Ready to Execute

### Completed Analysis
- ✅ Migration plan reviewed
- ✅ Database paths verified
- ✅ Migration script ready

### Next Steps
1. Run dry-run migration
2. Review results (expect ~3,865 to migrate)
3. Execute actual migration if counts match
4. Validate results

### Database Paths
- Legacy: `/workspaces/hass_traeger/traeger-stream/data/traeger_data.db`
- New: `/workspaces/hass_traeger/traeger-monitor/data/traeger.db`

### Expected Results
- Messages before migration: [CHECK ACTUAL COUNT]
- Messages to add: ~3,865
- Messages after migration: ~[CALCULATE]
- Duplicates to skip: ~672
```

#### 2. TASKS.md
Create this file with migration tasks:
```markdown
# Data Migration Task Tracking

## High Priority Tasks

### 1. Pre-Migration Verification
- [ ] Verify database paths exist
- [ ] Check current message count in new DB
- [ ] Ensure migration script is executable
- [ ] Verify no active connections to databases

### 2. Migration Execution
- [ ] Run migration in dry-run mode
- [ ] Verify dry-run shows ~3,865 messages to migrate
- [ ] Verify dry-run shows ~672 duplicates to skip
- [ ] Review any validation errors
- [ ] Execute actual migration
- [ ] Confirm backup was created

## Medium Priority Tasks

### 3. Post-Migration Validation
- [ ] Verify new database has expected total messages
- [ ] Check no duplicate state_index values exist
- [ ] Run validation queries from plan
- [ ] Test monitor app still works
- [ ] Document final results

## Low Priority Tasks

### 4. Cleanup
- [ ] Archive migration artifacts
- [ ] Update documentation with results
- [ ] Remove temporary analysis scripts
```

#### 3. WORK_LOG.md
Create this file to track your work:
```markdown
# Data Migration Work Log

## Overview
This document tracks the execution of the Traeger data migration from legacy to new database.

## Session Template
Copy this template for each work session:

```
### Session N: [Description] (HH:MM - HH:MM UTC)
**Started**: [What was reviewed/checked]
**Completed**:
- [ ] Task details
**Issues Found**:
- Any problems
**Results**: 
- Outcomes
**Time Spent**: ~X minutes
```

## Sessions

### Session 1: Migration Preparation (HH:MM UTC)
**Started**: Created tracking files, reviewing migration plan
**Next**: Execute dry-run migration
```

## Work Tracking Protocol

### Before Starting Migration
1. **Read Current Status**:
   ```bash
   cat MIGRATION_LOG.md  # Quick overview
   cat TASKS.md          # Check pending tasks
   ```

2. **Update WORK_LOG.md** with session start:
   ```markdown
   ### Session 2: Migration Execution (HH:MM UTC)
   **Started**: Reviewed MIGRATION_LOG.md, ready to execute dry-run
   ```

### During Migration
1. **Update TASKS.md** as you complete each step:
   - Check off completed items
   - Add any new tasks discovered
   
2. **Document issues immediately** in WORK_LOG.md:
   - Unexpected results
   - Errors encountered
   - Decisions made

### After Each Major Step
1. **Update MIGRATION_LOG.md** if status changes significantly
2. **Check off tasks** in TASKS.md
3. **Add notes** to WORK_LOG.md about what happened

### End of Session
1. **Complete WORK_LOG.md entry**:
   ```markdown
   **Completed**:
   - [x] Ran dry-run (3,865 messages identified)
   - [x] Executed migration successfully
   **Issues Found**:
   - None/Any issues
   **Results**: 
   - Migrated 3,865 messages
   - Final count: 6,624
   **Time Spent**: ~X minutes
   ```

2. **Update MIGRATION_LOG.md** to reflect new status

3. **Commit all tracking files**:
   ```bash
   git add WORK_LOG.md TASKS.md MIGRATION_LOG.md
   git commit -m "Update migration tracking - <status>"
   ```

## Implementation Plan

### Phase 1: Pre-Migration Checklist ✅
- [x] Analyze both databases
- [x] Identify messages to migrate
- [x] Create migration script
- [x] Set up work tracking
- [x] Create project documentation

### Phase 2: Dry Run Execution
1. **Update tracking** (before starting):
   ```bash
   # Update WORK_LOG.md with session start
   # Mark task as in_progress in TASKS.md
   ```

2. Navigate to migration directory:
   ```bash
   cd /workspaces/hass_traeger/migration-project
   ```

3. Run migration script (starts with dry run):
   ```bash
   python migrate_raw_messages.py
   ```

4. **Document results** in WORK_LOG.md:
   - Actual messages to migrate
   - Actual duplicates found
   - Any unexpected findings

5. Verify dry run output shows:
   - Messages to migrate: ~3,865
   - Messages skipped (duplicates): ~672
   - Invalid JSON: 0 (expected)

6. **Update TASKS.md**: Check off dry-run task

### Phase 3: Actual Migration
1. Review dry run results
2. **Decision point** - Document in WORK_LOG.md:
   - If results match expectations → proceed
   - If unexpected → document and investigate

3. Confirm execution when prompted

4. Script will:
   - Create timestamped backup
   - Begin transaction
   - Migrate messages
   - Commit on success
   - Report statistics

5. **Immediately document** in WORK_LOG.md:
   - Backup filename created
   - Final migration statistics
   - Any errors or warnings

6. **Update TASKS.md**: Check off migration execution

### Phase 4: Post-Migration Validation

#### Automated Checks (by script)
- Final message count reported
- No exceptions during execution
- Transaction committed successfully

#### Manual Validation
1. Verify total message count:
   ```sql
   SELECT COUNT(*) FROM raw_messages;
   -- Expected: ~6,624
   ```

2. Check for duplicates:
   ```sql
   SELECT state_index, COUNT(*) 
   FROM raw_messages 
   WHERE state_index IS NOT NULL 
   GROUP BY state_index 
   HAVING COUNT(*) > 1;
   -- Expected: 0 rows
   ```

3. Verify date range expanded:
   ```sql
   SELECT MIN(timestamp), MAX(timestamp) FROM raw_messages;
   -- Expected MIN: 2025-05-26 (earlier than before)
   ```

4. Test application still works:
   - Monitor continues receiving messages
   - Web UI displays current data
   - Predictions function normally

5. **Final tracking updates**:
   - Update MIGRATION_LOG.md status to "Complete"
   - Check off all validation tasks in TASKS.md
   - Complete session in WORK_LOG.md with final results

## Success Criteria

### Must Have (Required for Success)
- ✅ No data loss in new database
- ✅ No duplicate state_index values created
- ✅ All 3,865 unique messages migrated
- ✅ Application continues functioning normally
- ✅ Backup created successfully

### Should Have (Expected Outcomes)
- ✅ Migration completes in < 5 minutes
- ✅ Clear audit trail in logs
- ✅ No manual intervention required
- ✅ Final count matches prediction (~6,624)

### Nice to Have
- Migration summary report generated
- Performance metrics captured
- Detailed validation output

## Migration Script Features

### Safety Features
1. **Dry Run Mode**: Preview changes without modification
2. **Automatic Backup**: Timestamped backup before changes
3. **Transaction Wrapper**: All-or-nothing execution
4. **Duplicate Detection**: Two-layer deduplication
5. **Data Validation**: JSON integrity checking
6. **User Confirmation**: Explicit approval required
7. **Progress Reporting**: Real-time status updates

### Error Handling
- Database connection failures → Clear error message
- Invalid JSON → Skip message, count as invalid
- Duplicate detection → Skip silently, count as duplicate
- Transaction failure → Automatic rollback
- Unexpected errors → Rollback and preserve backup

## Command Reference

### Execution Commands
```bash
# Run migration (includes dry run)
cd /workspaces/hass_traeger/migration-project
python migrate_raw_messages.py

# Check message count
sqlite3 /workspaces/hass_traeger/traeger-monitor/data/traeger.db "SELECT COUNT(*) FROM raw_messages;"

# View recent messages
sqlite3 /workspaces/hass_traeger/traeger-monitor/data/traeger.db "SELECT timestamp, topic FROM raw_messages ORDER BY timestamp DESC LIMIT 5;"
```

### Validation Queries
```sql
-- Check for duplicates
SELECT state_index, COUNT(*) as count 
FROM raw_messages 
WHERE state_index IS NOT NULL 
GROUP BY state_index 
HAVING count > 1;

-- Verify date range
SELECT 
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    COUNT(*) as total
FROM raw_messages;

-- Check specific message counts by date
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as messages
FROM raw_messages
GROUP BY date
ORDER BY date;
```

## Troubleshooting

### Issue: Dry run shows 0 messages to migrate
- **Cause**: Already migrated or date filter issue
- **Solution**: Check date ranges with validation queries

### Issue: More duplicates than expected
- **Cause**: Previous partial migration attempt
- **Solution**: Normal - deduplication will handle it

### Issue: Script fails with database locked
- **Cause**: Monitor application has active connection
- **Solution**: Normal for SQLite, retry in a few seconds

### Issue: JSON validation errors
- **Cause**: Corrupted message in legacy database
- **Solution**: Script will skip and continue, note in results

## Post-Migration Cleanup

1. **After Successful Migration**:
   - Archive migration scripts (optional)
   - Keep backup for 24-48 hours
   - Update documentation with results

2. **If Migration Fails**:
   - Check error messages
   - Restore from backup if needed
   - Fix issues and retry

## Work Tracking Integration

### Tracking Files Overview

This project uses a four-file tracking system:

1. **MIGRATION_LOG.md** (30 lines)
   - Quick status overview
   - Current state of migration
   - Key metrics and next steps
   - Update when: Major milestones reached

2. **TASKS.md** (Checklist format)
   - All tasks with checkboxes
   - Organized by priority
   - Update when: Tasks completed or discovered

3. **WORK_LOG.md** (Growing log)
   - Detailed session history
   - Issues and resolutions
   - Time tracking
   - Update when: Starting/ending work sessions

4. **MIGRATION_PLAN.md** (This file)
   - Reference document
   - Don't update unless plan changes

### When to Update Each File

| Event | MIGRATION_LOG | TASKS | WORK_LOG |
|-------|--------------|-------|----------|
| Starting work | - | Review | Add session start |
| Dry-run complete | Update counts | ✓ Check off | Document results |
| Migration done | Update status | ✓ Check off | Full summary |
| Issue found | If major | Add new tasks | Document details |
| Session end | If status changed | Ensure current | Complete entry |

## Appendix: Script Architecture

### Core Functions
- `backup_database()` - Creates timestamped backup
- `validate_json_payload()` - Ensures JSON integrity
- `migrate_raw_messages()` - Main migration logic
  - Connects to both databases
  - Loads existing state_indexes for deduplication
  - Processes messages in chronological order
  - Handles transaction management
  - Reports statistics

### Design Decisions
- **No Framework Dependencies**: Pure Python with sqlite3
- **Single-File Script**: All logic in one file for simplicity
- **Explicit Over Implicit**: Clear messages at each step
- **Conservative Approach**: Multiple safety checks
- **Idempotent**: Can be run multiple times safely

## Final Notes

This migration is a one-time operation to consolidate historical data. The script is designed to be:
- Safe (multiple safeguards)
- Simple (single purpose, clear flow)
- Transparent (detailed output)
- Reversible (via backup)

After successful migration, the new Traeger Monitor system will have complete historical context for better temperature predictions while maintaining data integrity.

## Appendix: Migration Script

Save this as `migrate_raw_messages.py` in your migration directory:

```python
#!/usr/bin/env python3
"""
Migration script for Traeger raw messages from legacy to new database.
Migrates ALL non-duplicate messages based on stateIndex.
"""
import sqlite3
import json
import shutil
from datetime import datetime
import sys

def backup_database(db_path):
    """Create a backup of the database before migration."""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Created backup: {backup_path}")
    return backup_path

def validate_json_payload(payload):
    """Validate that payload is valid JSON."""
    try:
        json.loads(payload)
        return True
    except:
        return False

def migrate_raw_messages(legacy_db_path, new_db_path, dry_run=True):
    """
    Migrate raw messages from legacy to new database.
    
    Args:
        legacy_db_path: Path to legacy database
        new_db_path: Path to new database
        dry_run: If True, only simulate migration without making changes
    """
    print(f"\n{'DRY RUN' if dry_run else 'ACTUAL'} MIGRATION")
    print("=" * 60)
    
    # Connect to databases
    legacy_conn = sqlite3.connect(legacy_db_path)
    new_conn = sqlite3.connect(new_db_path)
    
    legacy_cursor = legacy_conn.cursor()
    new_cursor = new_conn.cursor()
    
    try:
        # Get existing state_indexes in new database for deduplication
        new_cursor.execute("SELECT state_index FROM raw_messages WHERE state_index IS NOT NULL")
        existing_state_indexes = set(row[0] for row in new_cursor.fetchall())
        
        # Get existing timestamp+topic combinations for secondary deduplication
        new_cursor.execute("SELECT timestamp, topic FROM raw_messages")
        existing_timestamp_topics = set((row[0], row[1]) for row in new_cursor.fetchall())
        
        print(f"Existing records in new DB: {len(existing_state_indexes)} with state_index")
        print(f"Existing timestamp+topic combinations: {len(existing_timestamp_topics)}")
        
        # Get ALL messages from legacy DB (not just before overlap!)
        legacy_cursor.execute("""
            SELECT id, timestamp, topic, payload, state_index 
            FROM raw_messages 
            ORDER BY timestamp ASC
        """)
        
        all_legacy_messages = legacy_cursor.fetchall()
        print(f"\nTotal messages in legacy DB: {len(all_legacy_messages)}")
        
        # Process migration
        migrated_count = 0
        skipped_state_index = 0
        skipped_timestamp = 0
        invalid_json_count = 0
        
        if not dry_run:
            new_conn.execute("BEGIN TRANSACTION")
        
        for msg in all_legacy_messages:
            msg_id, timestamp, topic, payload, state_index = msg
            
            # Validate JSON payload
            if not validate_json_payload(payload):
                print(f"WARNING: Invalid JSON in message ID {msg_id}")
                invalid_json_count += 1
                continue
            
            # Check for duplicates by state_index (primary deduplication)
            if state_index and state_index in existing_state_indexes:
                skipped_state_index += 1
                continue
            
            # Check for duplicates by timestamp+topic (secondary deduplication)
            if (timestamp, topic) in existing_timestamp_topics:
                skipped_timestamp += 1
                continue
            
            # Migrate the message
            if not dry_run:
                new_cursor.execute("""
                    INSERT INTO raw_messages (timestamp, topic, payload, state_index)
                    VALUES (?, ?, ?, ?)
                """, (timestamp, topic, payload, state_index))
            
            migrated_count += 1
            
            # Add to deduplication sets for subsequent checks
            if state_index:
                existing_state_indexes.add(state_index)
            existing_timestamp_topics.add((timestamp, topic))
        
        # Commit or rollback
        if not dry_run:
            new_conn.commit()
            print("\nMigration completed successfully!")
        
        # Final statistics
        print(f"\n=== MIGRATION STATISTICS ===")
        print(f"Messages analyzed: {len(all_legacy_messages)}")
        print(f"Messages migrated: {migrated_count}")
        print(f"Messages skipped (duplicate state_index): {skipped_state_index}")
        print(f"Messages skipped (duplicate timestamp+topic): {skipped_timestamp}")
        print(f"Total skipped: {skipped_state_index + skipped_timestamp}")
        print(f"Messages with invalid JSON: {invalid_json_count}")
        
        # Verify final count
        if not dry_run:
            new_cursor.execute("SELECT COUNT(*) FROM raw_messages")
            final_count = new_cursor.fetchone()[0]
            print(f"\nFinal total messages in new DB: {final_count}")
        
    except Exception as e:
        if not dry_run:
            new_conn.rollback()
        print(f"\nERROR: Migration failed - {e}")
        raise
    finally:
        legacy_conn.close()
        new_conn.close()

def main():
    legacy_db = "/workspaces/hass_traeger/traeger-stream/data/traeger_data.db"
    new_db = "/workspaces/hass_traeger/traeger-monitor/data/traeger.db"
    
    # First, do a dry run
    print("Starting dry run to validate migration...")
    migrate_raw_messages(legacy_db, new_db, dry_run=True)
    
    # Ask for confirmation
    print("\n" + "="*60)
    response = input("\nProceed with actual migration? (yes/no): ")
    
    if response.lower() == 'yes':
        # Backup the new database
        backup_path = backup_database(new_db)
        
        # Perform actual migration
        migrate_raw_messages(legacy_db, new_db, dry_run=False)
        
        print(f"\nMigration complete! Backup saved at: {backup_path}")
    else:
        print("Migration cancelled.")

if __name__ == "__main__":
    main()
```

Make the script executable:
```bash
chmod +x migrate_raw_messages.py
```