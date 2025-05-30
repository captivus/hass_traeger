Duplicate Data Analysis & Fix Plan

  Based on my analysis, I've identified the root cause and a comprehensive fix
   strategy:

  Root Cause

  The duplicate records occur because:
  1. No deduplication in storage layer: The _save_raw_message_sync() method
  inserts every MQTT message without checking for existing records with the
  same stateIndex
  2. No database constraints: The SQLite schema lacks unique constraints on
  stateIndex or topic + stateIndex combination
  3. MQTT message redelivery: Likely due to reconnection issues or multiple
  subscriptions causing the same messages to be processed multiple times

  Fix Strategy (Without Breaking Anything)

  1. Add Deduplication at Storage Layer
  - Modify _save_raw_message_sync() to check if a message with the same
  stateIndex and topic already exists before inserting
  - Extract stateIndex from the JSON payload and use it as a unique identifier
  - Use INSERT OR IGNORE with a unique constraint for atomicity

  2. Database Schema Changes
  - Add a new column state_index to the raw_messages table
  - Create a unique index on (topic, state_index) to prevent duplicates at the
   database level
  - Migrate existing data to populate the new column

  3. MQTT Connection Management
  - Add logic to unsubscribe from topics before resubscribing during
  reconnections
  - Track subscription state to prevent multiple subscriptions to the same
  topic

  4. Database Cleanup Strategy
  - Identify duplicate records by grouping by topic and stateIndex
  - Keep only the earliest record for each unique combination
  - Create a backup before cleanup
  - Verify data integrity after cleanup

  Implementation Order

  1. First, clean up existing duplicates (safe operation)
  2. Add database schema changes with backward compatibility
  3. Implement deduplication logic in storage layer
  4. Test thoroughly with live data to ensure no data loss

  This approach ensures:
  - No data loss
  - Backward compatibility
  - Minimal performance impact
  - Prevention of future duplicates