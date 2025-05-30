# Traeger Raw Messages - Practical Examples and Usage Guide

This companion document to the Data Dictionary provides practical examples and usage patterns for working with Traeger grill MQTT data.

## Common Query Examples

### 1. Get Latest Grill Status
```sql
-- Get the most recent status for a specific grill
SELECT 
    timestamp,
    json_extract(payload, '$.status.system_status') as state,
    json_extract(payload, '$.status.grill') as grill_temp,
    json_extract(payload, '$.status.set') as set_temp,
    json_extract(payload, '$.status.real_time') as real_time
FROM raw_messages
WHERE topic = 'prod/thing/update/E8EB1B4C1502'
ORDER BY id DESC
LIMIT 1;
```

### 2. Find Active Cook Sessions
```sql
-- Find all unique cook sessions
SELECT DISTINCT 
    json_extract(payload, '$.status.cook_id') as cook_id,
    MIN(timestamp) as start_time,
    MAX(timestamp) as end_time,
    COUNT(*) as message_count
FROM raw_messages
WHERE json_extract(payload, '$.status.cook_id') != ''
GROUP BY cook_id
ORDER BY start_time DESC;
```

### 3. Temperature History for a Cook
```sql
-- Get temperature progression during a specific cook
SELECT 
    timestamp,
    json_extract(payload, '$.status.grill') as grill_temp,
    json_extract(payload, '$.status.set') as set_temp,
    json_extract(payload, '$.status.ambient') as ambient_temp
FROM raw_messages
WHERE json_extract(payload, '$.status.cook_id') = 'E8EB1B4C15021748620109'
ORDER BY timestamp;
```

### 4. Probe Temperature Analysis
```sql
-- Extract Bluetooth probe temperatures
SELECT 
    timestamp,
    json_extract(payload, '$.status.acc[' || idx || '].channel') as channel,
    json_extract(payload, '$.status.acc[' || idx || '].btprobe.get_temp') as probe_temp,
    json_extract(payload, '$.status.acc[' || idx || '].btprobe.set_temp') as target_temp,
    json_extract(payload, '$.status.acc[' || idx || '].btprobe.batt') as battery
FROM raw_messages,
     (SELECT 0 as idx UNION SELECT 1 UNION SELECT 2 UNION SELECT 3) as indices
WHERE json_extract(payload, '$.status.acc[' || idx || '].type') = 'btprobe'
  AND json_extract(payload, '$.status.acc[' || idx || '].con') = 1
  AND json_extract(payload, '$.status.acc[' || idx || '].btprobe') IS NOT NULL
ORDER BY timestamp DESC
LIMIT 20;
```

## Python Processing Examples

### Basic Message Parsing
```python
import json
import sqlite3
from datetime import datetime

def parse_grill_message(payload_json):
    """Parse a raw message payload into useful data."""
    data = json.loads(payload_json)
    
    status = data['status']
    
    # Map system status to readable state
    state_map = {
        2: 'OFF',
        5: 'IGNITING', 
        6: 'HEATING',
        8: 'COOLING',
        9: 'SHUTDOWN'
    }
    
    result = {
        'state': state_map.get(status['system_status'], 'UNKNOWN'),
        'grill_temp': status['grill'],
        'set_temp': status['set'],
        'ambient_temp': status['ambient'],
        'pellet_level': status['pellet_level'],
        'real_time': bool(status['real_time']),
        'has_errors': status['errors'] != 0,
        'cook_id': status['cook_id'] or None,
        'connected': status['connected'],
        'probes': []
    }
    
    # Extract probe data
    for acc in status['acc']:
        if acc['type'] == 'btprobe' and acc.get('con') == 1:
            if 'btprobe' in acc:
                probe_data = acc['btprobe']
                result['probes'].append({
                    'channel': acc['channel'],
                    'temp': probe_data.get('get_temp'),
                    'target': probe_data.get('set_temp'),
                    'battery': probe_data.get('batt')
                })
        elif acc['type'] == 'probe' and acc.get('con') == 1:
            result['probes'].append({
                'channel': acc['channel'],
                'temp': status.get('probe'),
                'target': status.get('probe_set')
            })
    
    return result
```

### Temperature Trend Analysis
```python
def analyze_temperature_trend(db_path, hours=1):
    """Analyze temperature trends over time."""
    conn = sqlite3.connect(db_path)
    
    query = '''
    SELECT 
        timestamp,
        json_extract(payload, '$.status.grill') as temp,
        json_extract(payload, '$.status.set') as target
    FROM raw_messages
    WHERE timestamp > datetime('now', '-{} hours')
    ORDER BY timestamp
    '''.format(hours)
    
    cursor = conn.execute(query)
    
    temps = []
    times = []
    
    for row in cursor:
        times.append(datetime.fromisoformat(row[0]))
        temps.append(row[1])
    
    if len(temps) > 1:
        # Calculate rate of change
        time_diff = (times[-1] - times[0]).total_seconds() / 60  # minutes
        temp_diff = temps[-1] - temps[0]
        rate = temp_diff / time_diff if time_diff > 0 else 0
        
        return {
            'current': temps[-1],
            'rate_per_min': round(rate, 2),
            'trend': 'rising' if rate > 0.5 else 'falling' if rate < -0.5 else 'stable',
            'min': min(temps),
            'max': max(temps),
            'samples': len(temps)
        }
    
    conn.close()
```

### Error Detection
```python
def check_grill_errors(payload_json):
    """Decode error flags from a message."""
    data = json.loads(payload_json)
    error_code = data['status']['errors']
    
    if error_code == 0:
        return []
    
    errors = []
    
    # Known error bits (positions are 0-based)
    error_map = {
        28: 'Unknown Error Type 1',  # 0x10000000
        29: 'Unknown Error Type 2'   # 0x20000000
    }
    
    for bit_position, description in error_map.items():
        if error_code & (1 << bit_position):
            errors.append(description)
    
    # Check for unknown error bits
    known_mask = sum(1 << pos for pos in error_map.keys())
    unknown_bits = error_code & ~known_mask
    if unknown_bits:
        errors.append(f'Unknown error bits: {hex(unknown_bits)}')
    
    return errors
```

### Pellet Level Monitoring
```python
def get_pellet_status(db_path, thing_name):
    """Get current pellet level and consumption rate."""
    conn = sqlite3.connect(db_path)
    
    # Get recent pellet levels
    cursor = conn.execute('''
        SELECT 
            timestamp,
            json_extract(payload, '$.status.pellet_level') as level
        FROM raw_messages
        WHERE topic = ?
        ORDER BY id DESC
        LIMIT 100
    ''', (f'prod/thing/update/{thing_name}',))
    
    levels = []
    times = []
    
    for row in cursor:
        if row[1] is not None:
            times.append(datetime.fromisoformat(row[0]))
            levels.append(row[1])
    
    if not levels:
        return None
    
    current_level = levels[0]
    
    # Calculate burn rate if we have enough data
    burn_rate = None
    if len(levels) > 10:
        # Look for level changes
        for i in range(1, len(levels)):
            if levels[i] != current_level:
                time_diff = (times[0] - times[i]).total_seconds() / 3600  # hours
                level_diff = levels[i] - current_level
                if time_diff > 0 and level_diff > 0:
                    burn_rate = level_diff / time_diff
                break
    
    return {
        'current_level': current_level,
        'burn_rate_per_hour': burn_rate,
        'time_to_empty': current_level / burn_rate if burn_rate else None
    }
    
    conn.close()
```

## Common Patterns and Gotchas

### 1. Time Zone Handling
The grill's internal clock runs 5 hours behind the database timestamp (UTC-5):
```python
def convert_grill_time(grill_timestamp):
    """Convert grill timestamp to local time."""
    from datetime import timezone, timedelta
    
    # Grill time appears to be in EST (UTC-5)
    grill_dt = datetime.fromtimestamp(grill_timestamp, tz=timezone(timedelta(hours=-5)))
    return grill_dt.astimezone()  # Convert to local time
```

### 2. Real-Time Mode Detection
When `real_time = 1`, expect more frequent updates:
```python
def should_increase_polling(payload_json):
    """Check if we should poll more frequently."""
    data = json.loads(payload_json)
    return data['status']['real_time'] == 1
```

### 3. Cook Session Tracking
Cook IDs follow the pattern `{THING_NAME}{TIMESTAMP}`:
```python
def parse_cook_id(cook_id):
    """Extract info from cook ID."""
    if not cook_id:
        return None
    
    # Example: E8EB1B4C15021748620109
    thing_name = cook_id[:12]  # First 12 chars
    timestamp = int(cook_id[12:])  # Rest is timestamp
    
    return {
        'thing_name': thing_name,
        'start_time': datetime.fromtimestamp(timestamp)
    }
```

### 4. Probe Connection Status
Always check connection status before using probe data:
```python
def get_active_probes(payload_json):
    """Get only connected probes with valid data."""
    data = json.loads(payload_json)
    active_probes = []
    
    for acc in data['status']['acc']:
        if acc.get('con') != 1:
            continue
            
        if acc['type'] == 'btprobe' and 'btprobe' in acc:
            probe = acc['btprobe']
            if probe.get('get_temp') is not None:
                active_probes.append({
                    'type': 'bluetooth',
                    'channel': acc['channel'],
                    'temperature': probe['get_temp'],
                    'target': probe.get('set_temp'),
                    'battery': probe.get('batt')
                })
        elif acc['type'] == 'probe':
            # Wired probe data is in status object
            if data['status'].get('probe') is not None:
                active_probes.append({
                    'type': 'wired',
                    'channel': acc['channel'],
                    'temperature': data['status']['probe'],
                    'target': data['status'].get('probe_set')
                })
    
    return active_probes
```

### 5. State Transition Detection
```python
def detect_state_changes(db_path, thing_name, minutes=10):
    """Find state transitions in recent data."""
    conn = sqlite3.connect(db_path)
    
    cursor = conn.execute('''
        SELECT 
            timestamp,
            json_extract(payload, '$.status.system_status') as state
        FROM raw_messages
        WHERE topic = ?
            AND timestamp > datetime('now', '-{} minutes')
        ORDER BY timestamp
    '''.format(minutes), (f'prod/thing/update/{thing_name}',))
    
    transitions = []
    prev_state = None
    
    for timestamp, state in cursor:
        if prev_state is not None and state != prev_state:
            transitions.append({
                'time': timestamp,
                'from': prev_state,
                'to': state
            })
        prev_state = state
    
    conn.close()
    return transitions
```

## Data Validation Rules

1. **Temperature Ranges**
   - Grill: 70-500°F (operational range)
   - Ambient: 50-120°F (typical outdoor temps)
   - Probes: 32-300°F (food safety range)

2. **Required Fields**
   - Every message must have: stateIndex, status object, thingName
   - status must contain: grill, system_status, time

3. **Consistency Checks**
   - cook_timer_end >= cook_timer_start
   - Pellet level: 0-100%
   - Battery levels: 0-100%

4. **State Logic**
   - State 2 (OFF): set temp can be > 0 (last setting retained)
   - State 6 (HEATING): grill temp converges to set temp
   - State 8 (COOLING): grill temp decreasing

## Performance Considerations

1. **Indexing Strategy**
   - Index on timestamp for time-range queries
   - Index on topic for multi-grill systems
   - Unique index on (topic, state_index) for deduplication

2. **Query Optimization**
   - Use JSON extraction in WHERE clauses sparingly
   - Consider materialized views for frequently accessed data
   - Batch operations when processing historical data

3. **Storage Management**
   - Messages arrive every ~30 seconds (2,880/day per grill)
   - Average message size: ~4KB
   - Plan for ~12MB/day per grill
   - Implement retention policies for old data