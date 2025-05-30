# Traeger Raw Messages Table Analysis

## Database Schema

The `raw_messages` table has the following structure:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key, auto-increment |
| timestamp | DATETIME | DB insertion time (local) |
| topic | TEXT | MQTT topic |
| payload | TEXT | JSON payload as string |
| state_index | INTEGER | Extracted stateIndex for deduplication |

**Indexes:**
- Primary key on `id`
- Index on `timestamp`
- Index on `topic`
- Unique index on `(topic, state_index)` where state_index is not null

## MQTT Topic Structure

All messages use a single topic pattern:
- `prod/thing/update/{THING_NAME}` (e.g., `prod/thing/update/E8EB1B4C1502`)

## JSON Payload Structure

### Top-Level Fields

```json
{
  "thingName": "E8EB1B4C1502",        // Device ID
  "jobs": [],                         // Always empty in samples
  "status": {...},                    // Main status data
  "features": {...},                  // Device capabilities
  "limits": {...},                    // Temperature limits (usually 0)
  "settings": {...},                  // Device configuration
  "usage": {...},                     // Usage statistics
  "custom_cook": {...},               // Custom cook cycles
  "stateIndex": 1841503,              // Unique message ID for deduplication
  "schemaVersion": "2.0",             // Payload schema version
  "details": {...}                    // Device metadata
}
```

### Status Object (status.*)

Core operational data:

```json
{
  "pellet_level": 90,                 // Pellet level percentage
  "grill_mode": 0,                    // Grill mode (0 = normal)
  "uuid": "E8EB1B4C1502",            // Device UUID
  "real_time": 0,                     // Real-time mode flag (0 or 1)
  "ui": {
    "screen_brightness": 0,           // Display brightness
    "ambient_light": 0                // Ambient light sensor
  },
  "time": 1748629614,                // Grill's Unix timestamp
  "errors": 0,                        // Error bitmask (0 = no errors)
  "sys_timer_start": 0,              // System timer start
  "cook_id": "",                     // Cook session ID (often empty)
  "server_status": 0,                // Server connection status
  "units": 1,                        // Temperature units (1 = Fahrenheit)
  "grill": 113,                      // Current grill temperature
  "seasoned": 1,                     // Grill seasoned flag
  "current_step": 0,                 // Current cook cycle step
  "system_status": 2,                // System state (see below)
  "sys_timer_end": 0,                // System timer end
  "set": 400,                        // Target temperature
  "in_custom": 0,                    // In custom cook cycle
  "smoke": 0,                        // Smoke mode enabled
  "cook_timer_complete": 0,          // Cook timer completed flag
  "grease_level": 0,                 // Grease trap level
  "current_cycle": 0,                // Current cook cycle
  "grease_temperature": 0,           // Grease temperature
  "ambient": 98,                     // Ambient temperature
  "sys_timer_complete": 1,           // System timer complete flag
  "cook_timer_start": 1748621051,    // Cook timer start timestamp
  "cook_timer_end": 1748628251,      // Cook timer end timestamp
  "acc": [...],                      // Accessories (probes)
  "keepwarm": 0,                     // Keep warm mode
  "connected": true,                 // Connection status
  "probe_con": 0,                    // Probe connected (wired)
  "probe": 0,                        // Probe temperature (wired)
  "probe_set": 0,                    // Probe target temp (wired)
  "probe_alarm_fired": 0             // Probe alarm status
}
```

#### System Status Values

Based on analysis:
- **2**: OFF/IDLE (cold grill)
- **5**: IGNITING (starting up, may have errors)
- **6**: HEATING/RUNNING (normal cooking)
- **8**: COOLING DOWN
- **9**: SHUTDOWN

#### Error Codes

Error field is a bitmask. Common values:
- **0**: No errors
- **268435456**: Unknown error type 1
- **536870912**: Unknown error type 2 (seen during ignition)

### Accessories Array (status.acc)

Three types of accessories found:

#### 1. HOB (Hopper/Pellet Sensor)
```json
{
  "channel": "bt",
  "type": "hob",
  "uuid": "8c4b14b9901e",
  "con": 1,                    // Connected flag
  "hob": {
    "fw": "01.00.55",         // Firmware version
    "level": 0,               // Pellet level
    "get_temp": 86,           // Current temperature
    "set_temp": 0,            // Target temperature
    "status": 0               // Status
  }
}
```

#### 2. Bluetooth Probe
```json
{
  "type": "btprobe",
  "channel": "BT0" or "BT1",
  "uuid": "b81f5e66940d",
  "con": 1                     // Connected flag
}
```

#### 3. Wired Probe (not seen in samples)
Would have type "probe" with probe data.

### Features Object

Device capabilities:
```json
{
  "pellet_sensor_enabled": 1,
  "pellet_sensor_connected": 1,
  "open_loop_mode_enabled": 0,
  "grease_sensor_enabled": 0,
  "cold_smoke_enabled": 0,
  "grill_mode_enabled": 0,
  "ui": {
    "ui_type": 0
  },
  "lid_sensor_enabled": 1,
  "super_smoke_enabled": 1,
  "pizza_mode_enabled": 0,
  "flame_sensor_enabled": 1,
  "limits": {
    "max_grill_temp": 500      // Maximum temperature
  },
  "grill_light_enabled": 1
}
```

### Settings Object

Device configuration:
```json
{
  "rssi": -74,                        // WiFi signal strength
  "units": 1,                         // Temperature units
  "config_version": "2202.006",       // Configuration version
  "feature": 0,                       // Feature flags
  "ui_fw_version": "UNKNOWN",         // UI firmware version
  "speaker": 1,                       // Speaker enabled
  "device_type_id": 2202,             // Device type ID
  "language": 0,                      // Language setting
  "fw_version": "01.05.01",           // Main firmware version
  "ui_fw_build_num": "0000000-00000000_000000",
  "ssid": "shift8_lame",              // WiFi network name
  "networking_fw_version": "1.4.2",   // Network firmware version
  "fw_build_num": "ac3015a-20250109_080308"  // Firmware build
}
```

### Usage Object

Lifetime usage statistics:
```json
{
  "auger": 709221,                    // Auger runtime seconds
  "grill_clean_countdown": 0,         // Cleaning countdown
  "ac_ignitor": 90535,                // AC ignitor runtime
  "time": 0,                          // Usage time
  "ui": {
    "screen_on": 0                    // Screen on time
  },
  "error_stats": {                    // Error counters
    "bad_thermocouple": 0,
    "ignite_fail": 0,
    "auger_ovrcur": 0,
    "ign_ac_disco": 0,
    "overheat": 0,
    "lowtemp": 0,
    "auger_disco": 0,
    "low_ambient": 0,
    "ign_dc_disco": 0,
    "fan_disco": 0
  },
  "fan": 816080,                      // Fan runtime seconds
  "runtime": 816178,                  // Total runtime seconds
  "hotrod": 0,                        // Hotrod runtime
  "dc_ignitor": 0,                    // DC ignitor runtime
  "light": 207465,                    // Light runtime seconds
  "grease_trap_clean_countdown": 0,   // Grease trap countdown
  "cook_cycles": 79                   // Total cook cycles
}
```

### Custom Cook Object

Stored cook cycles:
```json
{
  "cook_cycles": [
    {
      "num_steps": 2,
      "recipe_id": "0",
      "slot_num": 4,
      "cycle_name": "Smoked Brisket",
      "populated": 1,
      "food_type": 0,
      "units": 1,
      "steps": [
        {
          "probe_set_temp": 160,      // Target probe temp
          "time_set": 10800,          // Time in seconds (3 hours)
          "keepwarm": 0,
          "smoke": 0,
          "step_num": 1,
          "set_temp": 0,              // Grill temp (0 = probe-based)
          "use_timer": 0
        }
      ]
    }
  ]
}
```

### Details Object

Device metadata:
```json
{
  "thingName": "E8EB1B4C1502",
  "userId": "4ea3130c-9491-4f6d-ba0b-fae4f7aa0c22",
  "lastConnectedOn": 1748442431,     // Last connection timestamp
  "thingNameLower": "e8eb1b4c1502",
  "friendlyName": "Boss Hog",         // User-assigned name
  "lat": 41.967987,                   // Latitude
  "long": -88.408953,                  // Longitude
  "deviceType": "2202"                // Device type
}
```

## Field Analysis

### Required Fields (Always Present)
- All top-level fields
- Most status fields
- stateIndex (for deduplication)
- schemaVersion

### Optional/Variable Fields
- `status.cook_id` - Empty 42.3% of the time
- `status.errors` - Non-zero 6.3% of the time
- `status.real_time` - Set to 1 for 34.6% of messages
- `jobs` array - Always empty in samples
- Probe data in accessories - varies by connected probes

### Timestamp Handling

Multiple timestamp fields:
1. **Database timestamp** - Local time when message was stored
2. **status.time** - Grill's current Unix timestamp (appears offset by ~5 hours)
3. **cook_timer_start/end** - Unix timestamps for cook session
4. **details.lastConnectedOn** - Last connection Unix timestamp

The grill appears to use a different time zone or has a clock offset.

### Data Patterns

1. **Message Frequency**: Approximately every 30 seconds during normal operation
2. **Real-time Mode**: When `real_time=1`, updates may be more frequent
3. **State Transitions**: System status changes indicate grill state machine
4. **Deduplication**: stateIndex ensures no duplicate messages are stored
5. **Accessories**: HOB sensor always present, BT probes when connected

## Implementation Notes

The client.py maps this raw data to simplified models:
- System status codes map to GrillState enum
- Accessories are parsed into ProbeData objects
- Temperature predictions are calculated from historical data
- Raw payload is preserved in GrillStatus.raw_status for debugging