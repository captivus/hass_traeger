import sqlite3

# Execute test data deletion with transaction safety
conn = sqlite3.connect("/workspaces/hass_traeger/traeger-monitor/data/traeger.db")
cursor = conn.cursor()

print("=== EXECUTING TEST DATA DELETION ===\n")

try:
    # Start transaction
    conn.execute("BEGIN")
    
    # Check current count
    cursor.execute("SELECT COUNT(*) FROM raw_messages")
    before_count = cursor.fetchone()[0]
    print(f"Records before deletion: {before_count:,}")
    
    # Count test records to delete
    cursor.execute("""
        SELECT COUNT(*) 
        FROM raw_messages 
        WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
    """)
    test_count = cursor.fetchone()[0]
    print(f"Test records to delete: {test_count}")
    
    # Execute deletion
    cursor.execute("""
        DELETE FROM raw_messages
        WHERE json_extract(payload, '$.status.cook_id') LIKE 'TEST_COOK_%'
    """)
    deleted_count = cursor.rowcount
    print(f"Records actually deleted: {deleted_count}")
    
    # Verify counts match
    if deleted_count != test_count:
        print("WARNING: Deleted count doesn't match expected!")
        conn.rollback()
        print("TRANSACTION ROLLED BACK")
    else:
        # Check final count
        cursor.execute("SELECT COUNT(*) FROM raw_messages")
        after_count = cursor.fetchone()[0]
        expected_after = before_count - deleted_count
        
        print(f"Records after deletion: {after_count:,}")
        print(f"Expected after deletion: {expected_after:,}")
        
        if after_count == expected_after:
            # Commit the transaction
            conn.commit()
            print("\n✅ DELETION SUCCESSFUL - TRANSACTION COMMITTED")
            
            # Check what's now the most recent record
            cursor.execute("""
                SELECT 
                    timestamp,
                    json_extract(payload, '$.status.cook_id') as cook_id,
                    json_extract(payload, '$.status.grill') as grill_temp
                FROM raw_messages 
                ORDER BY timestamp DESC 
                LIMIT 3
            """)
            
            print("\nMost recent records after deletion:")
            for i, (ts, cook_id, grill_temp) in enumerate(cursor.fetchall(), 1):
                print(f"  {i}. {ts} - {cook_id or '[No cook ID]'} - Grill: {grill_temp}°F")
        else:
            print("ERROR: Final count doesn't match expected!")
            conn.rollback()
            print("TRANSACTION ROLLED BACK")

except Exception as e:
    print(f"ERROR during deletion: {e}")
    conn.rollback()
    print("TRANSACTION ROLLED BACK")

finally:
    conn.close()
    print("\nDatabase connection closed.")