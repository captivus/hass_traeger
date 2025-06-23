# UI Timestamp Fix Plan

## Problem Summary

The web UI cannot display migrated cook data due to timestamp format inconsistencies:
- **Migrated data**: `2025-06-22 16:55:53` (space separator)
- **Test data**: `2025-06-22T20:26:25.317328` (ISO format with 'T' and microseconds)
- **API issue**: String comparison `WHERE timestamp > ?` fails with mixed formats
- **Impact**: Test messages appear "newer" and hide real cook data

## Root Cause Analysis

1. **Database contains mixed timestamp formats**
   - Legacy migration preserved original format (space separator)
   - New monitor app creates ISO format timestamps
   - SQLite stores as TEXT, making string comparison unreliable

2. **API relies on string comparison**
   - `/api/history/<hours>` uses `WHERE timestamp > ?`
   - `/api/current` uses `ORDER BY timestamp DESC`
   - Both fail when formats differ

3. **Test data has "future" appearance**
   - ISO format with 'T' sorts differently than space format
   - Makes test data appear as most recent

## Solution Options

### Option 1: Fix API Queries (Recommended)
**Approach**: Update server.py to use SQLite datetime functions
```python
# Instead of: WHERE timestamp > ?
# Use: WHERE datetime(timestamp) > datetime(?)
```

**Pros**:
- Minimal changes required
- Works with existing mixed formats
- No data modification needed
- Preserves data integrity

**Cons**:
- Slight performance impact (datetime parsing)
- Must update all timestamp comparisons

### Option 2: Normalize All Timestamps
**Approach**: Update all timestamps to consistent ISO format
```sql
UPDATE raw_messages 
SET timestamp = datetime(timestamp) || 'Z'
WHERE timestamp NOT LIKE '%T%'
```

**Pros**:
- Permanent fix
- Optimal query performance
- Clean data format

**Cons**:
- Modifies historical data
- Risk of data corruption
- Requires backup/restore strategy

### Option 3: Remove Test Data
**Approach**: Delete test messages with TEST_COOK prefix
```sql
DELETE FROM raw_messages 
WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
```

**Pros**:
- Simple solution
- Removes confusion

**Cons**:
- Only partial fix (future data could have same issue)
- Loses test data for development

## Recommended Implementation Plan

### Phase 1: Immediate Fix (Option 1)
1. **Update API queries** in server.py:
   - Modify `/api/history/<hours>` route
   - Modify `/api/current` route
   - Update any other timestamp comparisons

2. **Specific changes**:
   ```python
   # /api/current - line 56
   row = conn.execute("SELECT timestamp, payload FROM raw_messages ORDER BY datetime(timestamp) DESC LIMIT 1").fetchone()
   
   # /api/history/<hours> - line 67
   rows = conn.execute("SELECT timestamp, payload FROM raw_messages WHERE datetime(timestamp) > datetime(?) ORDER BY datetime(timestamp)", (cutoff,))
   ```

3. **Test thoroughly**:
   - Verify real cook data displays
   - Confirm both probe channels visible
   - Check time range selections work

### Phase 2: Long-term Cleanup (Optional)
1. **Archive test data** (if needed for reference)
2. **Normalize timestamps** in a future maintenance window
3. **Update monitor app** to ensure consistent format for new data

## Testing Strategy

1. **Pre-fix validation**:
   - Document current UI state (screenshots)
   - Note which data is visible/hidden

2. **Post-fix validation**:
   - Verify June 22 cook displays correctly
   - Confirm both probes show in UI
   - Test all time range options (1, 3, 6, 12, 24 hours)
   - Verify chart displays historical data

3. **Regression testing**:
   - Ensure new data still displays
   - Confirm predictions still work
   - Check no performance degradation

## Risk Mitigation

1. **Backup current database** before any changes
2. **Test in development** first if possible
3. **Have rollback plan** ready
4. **Monitor performance** after deployment

## Success Criteria

- ✅ June 22 cook data visible in UI
- ✅ Both probe channels display correctly
- ✅ Historical chart shows full cook timeline
- ✅ Time range selector works for all options
- ✅ No breaking changes to existing functionality

## Timeline

- **Immediate fix**: 30 minutes
- **Testing**: 30 minutes
- **Total**: ~1 hour

## Notes

- This fix addresses the immediate UI visibility issue
- Does not modify any migrated data
- Maintains backward compatibility
- Can be enhanced later with data normalization