# UI Fix Implementation Checklist

## Pre-Implementation
- [ ] Review UI_FIX_PLAN.md completely
- [ ] Take screenshot of current UI state showing test data
- [ ] Backup database (already have traeger.db.backup_20250623_002208)
- [ ] Note current test data timestamps for comparison

## Implementation Steps

### 1. Update server.py API Routes
- [ ] Open `/workspaces/hass_traeger/traeger-monitor/web/server.py`
- [ ] Update `/api/current` route (line ~56):
  ```python
  # Change FROM:
  row = conn.execute("SELECT timestamp, payload FROM raw_messages ORDER BY timestamp DESC LIMIT 1").fetchone()
  
  # Change TO:
  row = conn.execute("SELECT timestamp, payload FROM raw_messages ORDER BY datetime(timestamp) DESC LIMIT 1").fetchone()
  ```

- [ ] Update `/api/history/<hours>` route (line ~67):
  ```python
  # Change FROM:
  rows = conn.execute("SELECT timestamp, payload FROM raw_messages WHERE timestamp > ? ORDER BY timestamp", (cutoff,))
  
  # Change TO:
  rows = conn.execute("SELECT timestamp, payload FROM raw_messages WHERE datetime(timestamp) > datetime(?) ORDER BY datetime(timestamp)", (cutoff,))
  ```

### 2. Restart Server
- [ ] Stop current Flask server (if running)
- [ ] Start server: `cd /workspaces/hass_traeger/traeger-monitor && uv run python web/server.py`

### 3. Testing

#### Basic Functionality
- [ ] Navigate to http://localhost:5000
- [ ] Verify current temperature shows real cook data (not test data)
- [ ] Check that grill temp is NOT 225°F (test value)

#### Probe Visibility
- [ ] Confirm TWO probe cards are displayed
- [ ] Verify Probe p0 shows real data
- [ ] Verify Probe p1 shows real data
- [ ] Check probe temperatures are different (p1 should be ~4-6°F higher)

#### Time Range Testing
- [ ] Test "Last Hour" - should show recent data
- [ ] Test "Last 3 Hours" - should show more history
- [ ] Test "Last 6 Hours" - should include cook data
- [ ] Test "Last 12 Hours" - should show full cook
- [ ] Test "Last 24 Hours" - should show all data

#### Chart Validation
- [ ] Verify temperature history chart displays
- [ ] Confirm TWO probe lines visible (blue and purple)
- [ ] Check grill temperature line (red)
- [ ] Verify x-axis shows correct times

### 4. Document Results
- [ ] Take screenshot of fixed UI showing real cook data
- [ ] Note any performance differences
- [ ] Document any unexpected behavior

## Rollback Plan (if needed)
1. Stop server
2. Restore original server.py (git checkout)
3. Restart server
4. Restore database from backup if data was modified

## Success Confirmation
- [ ] June 22 cook data visible
- [ ] Both probes displaying
- [ ] All time ranges working
- [ ] No errors in console
- [ ] Performance acceptable

## Post-Implementation
- [ ] Commit the fix with appropriate message
- [ ] Update UI_FIX_PLAN.md with results
- [ ] Consider long-term improvements