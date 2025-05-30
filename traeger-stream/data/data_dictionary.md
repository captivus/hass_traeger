# Traeger Grill MQTT Raw Messages Data Dictionary

## Overview

This data dictionary provides a comprehensive reference for the Traeger grill monitoring system's raw MQTT messages stored in the `raw_messages` table. The data represents real-time telemetry from Traeger WiFIRE-enabled grills, including temperatures, system status, probe readings, and operational parameters.

## Database Schema

### Table: `raw_messages`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique identifier for each message |
| `timestamp` | DATETIME | DEFAULT CURRENT_TIMESTAMP | Local time when message was inserted into database |
| `topic` | TEXT | NOT NULL, INDEXED | MQTT topic path (format: `prod/thing/update/{THING_NAME}`) |
| `payload` | TEXT | NOT NULL | JSON-encoded message payload containing all grill data |
| `state_index` | INTEGER | INDEXED, UNIQUE(topic, state_index) | Extracted stateIndex from payload for deduplication |

### Indexes
- Primary key on `id`
- Index on `timestamp` for time-based queries
- Index on `topic` for filtering by grill
- Unique composite index on `(topic, state_index)` where `state_index IS NOT NULL` to prevent duplicates

## MQTT Topic Structure

Topics follow a consistent pattern:
```
prod/thing/update/{THING_NAME}
```

Where:
- `prod` - Environment (production)
- `thing` - Resource type
- `update` - Message type
- `{THING_NAME}` - Unique device identifier (e.g., `E8EB1B4C1502`)

## JSON Payload Structure

### Root Level Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `thingName` | string | Yes | Device unique identifier, matches topic |
| `jobs` | array | Yes | Always empty array in observed data |
| `status` | object | Yes | Core operational data (see Status Object) |
| `features` | object | Yes | Device capabilities and enabled features |
| `limits` | object | Yes | Temperature limits (usually all zeros) |
| `settings` | object | Yes | Device configuration and firmware versions |
| `usage` | object | Yes | Lifetime usage statistics and error counts |
| `custom_cook` | object | Yes | Stored cook cycles and recipes |
| `stateIndex` | integer | Yes | Unique message identifier for deduplication |
| `schemaVersion` | string | Yes | Payload schema version (e.g., "2.0") |
| `details` | object | Yes | Device metadata and location info |

### Status Object (`status.*`)

Core operational data updated approximately every 30 seconds.

| Field | Type | Range/Values | Description |
|-------|------|--------------|-------------|
| `pellet_level` | integer | 0-100 | Pellet hopper level percentage |
| `grill_mode` | integer | 0 | Grill mode (only 0 observed) |
| `uuid` | string | - | Device UUID (redundant with thingName) |
| `real_time` | integer | 0, 1 | Real-time mode flag (37% of messages have 1) |
| `ui` | object | - | UI-related data |
| `ui.screen_brightness` | integer | 0 | Display brightness level |
| `ui.ambient_light` | integer | 0 | Ambient light sensor reading |
| `time` | integer | Unix timestamp | Grill's current time (UTC-5 offset observed) |
| `errors` | integer | See Error Codes | Error bitmask (0 = no errors) |
| `sys_timer_start` | integer | Unix timestamp | System timer start time |
| `cook_id` | string | Empty or UUID pattern | Cook session identifier (58% have values) |
| `server_status` | integer | 0 | Server connection status |
| `units` | integer | 1 | Temperature units (1 = Fahrenheit) |
| `grill` | integer | 70-500 | Current grill temperature (°F) |
| `seasoned` | integer | 0, 1 | Grill seasoned flag |
| `current_step` | integer | 0+ | Current cook cycle step |
| `system_status` | integer | 2, 5, 6, 8, 9 | System state (see System Status Codes) |
| `sys_timer_end` | integer | Unix timestamp | System timer end time |
| `set` | integer | 0-500 | Target temperature (°F), 0 when off |
| `in_custom` | integer | 0, 1 | Currently in custom cook cycle |
| `smoke` | integer | 0, 1 | Super smoke mode enabled |
| `cook_timer_complete` | integer | 0, 1 | Cook timer completed flag |
| `grease_level` | integer | 0 | Grease trap level (not implemented) |
| `current_cycle` | integer | 0+ | Current cook cycle number |
| `grease_temperature` | integer | 0 | Grease temperature (not implemented) |
| `ambient` | integer | 71-117 | Ambient temperature (°F) |
| `sys_timer_complete` | integer | 0, 1 | System timer complete flag |
| `cook_timer_start` | integer | Unix timestamp | Cook timer start time |
| `cook_timer_end` | integer | Unix timestamp | Cook timer end time |
| `acc` | array | - | Accessories array (see Accessories) |
| `keepwarm` | integer | 0, 1 | Keep warm mode enabled |
| `connected` | boolean | true, false | Connection status |
| `probe_con` | integer | 0, 1 | Wired probe connected |
| `probe` | integer | Temperature | Wired probe temperature |
| `probe_set` | integer | Temperature | Wired probe target |
| `probe_alarm_fired` | integer | 0, 1 | Wired probe alarm status |

#### System Status Codes

| Code | State | Description | Typical Conditions |
|------|-------|-------------|-------------------|
| 2 | OFF/IDLE | Grill is off or idle | 42.4% of messages, grill cooling down |
| 5 | IGNITING | Starting up | 0.4% of messages, may have errors |
| 6 | HEATING/RUNNING | Normal cooking operation | 51% of messages, maintaining temperature |
| 8 | COOLING | Cool-down cycle | 6.2% of messages, post-cook |
| 9 | SHUTDOWN | Shutting down | Rarely observed |

#### Error Codes (Bitmask)

| Value | Hex | Binary Position | Occurrence | Description |
|-------|-----|-----------------|------------|-------------|
| 0 | 0x0 | - | 94% | No errors |
| 268435456 | 0x10000000 | Bit 28 | 4.2% | Unknown error type 1 |
| 536870912 | 0x20000000 | Bit 29 | 1.8% | Unknown error type 2 (during ignition) |

### Accessories Array (`status.acc[]`)

Array of connected accessories (probes and sensors).

#### HOB (Hopper/Pellet Sensor)
Always present, monitors pellet level.

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Always "bt" |
| `type` | string | Always "hob" |
| `uuid` | string | Device MAC address |
| `con` | integer | Connection status (1 = connected) |
| `hob` | object | HOB-specific data |
| `hob.fw` | string | Firmware version (e.g., "01.00.55") |
| `hob.level` | integer | Pellet level (0-100) |
| `hob.get_temp` | integer | Current temperature |
| `hob.set_temp` | integer | Target temperature (usually 0) |
| `hob.status` | integer | Device status |

#### Bluetooth Probe
Wireless temperature probes.

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "btprobe" |
| `channel` | string | "BT0" or "BT1" |
| `uuid` | string | Probe MAC address |
| `con` | integer | Connection status (1 = connected) |
| `btprobe` | object | Probe data (when connected) |
| `btprobe.get_temp` | integer | Current temperature (71-203°F observed) |
| `btprobe.set_temp` | integer | Target temperature |
| `btprobe.alarm_fired` | integer | Alarm triggered (0, 1) |
| `btprobe.batt` | integer | Battery level (6-8% in samples) |
| `btprobe.fw` | string | Firmware version |
| `btprobe.ambient_temp` | integer | Probe ambient temperature |

#### Wired Probe
Traditional wired probes.

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "probe" |
| `channel` | string | "p0", "p1", etc. |
| `uuid` | string | Probe identifier |
| `con` | integer | Connection status |
| `probe` | object | Probe data (when connected) |

### Features Object (`features.*`)

Device capabilities and enabled features.

| Field | Type | Description |
|-------|------|-------------|
| `pellet_sensor_enabled` | integer | Pellet sensor available (0, 1) |
| `pellet_sensor_connected` | integer | Pellet sensor connected (0, 1) |
| `open_loop_mode_enabled` | integer | Open loop mode available |
| `grease_sensor_enabled` | integer | Grease sensor available |
| `cold_smoke_enabled` | integer | Cold smoke mode available |
| `grill_mode_enabled` | integer | Grill mode available |
| `ui.ui_type` | integer | UI type identifier |
| `lid_sensor_enabled` | integer | Lid sensor available |
| `super_smoke_enabled` | integer | Super smoke mode available |
| `pizza_mode_enabled` | integer | Pizza mode available |
| `flame_sensor_enabled` | integer | Flame sensor available |
| `limits.max_grill_temp` | integer | Maximum temperature (e.g., 500) |
| `grill_light_enabled` | integer | Grill light available |

### Settings Object (`settings.*`)

Device configuration and versions.

| Field | Type | Description |
|-------|------|-------------|
| `rssi` | integer | WiFi signal strength (dBm, e.g., -74) |
| `units` | integer | Temperature units (1 = Fahrenheit) |
| `config_version` | string | Configuration version |
| `feature` | integer | Feature flags |
| `ui_fw_version` | string | UI firmware version |
| `speaker` | integer | Speaker enabled (0, 1) |
| `device_type_id` | integer | Device model ID (e.g., 2202) |
| `language` | integer | Language setting |
| `fw_version` | string | Main firmware version |
| `ui_fw_build_num` | string | UI firmware build |
| `ssid` | string | Connected WiFi network name |
| `networking_fw_version` | string | Network firmware version |
| `fw_build_num` | string | Firmware build identifier |

### Usage Object (`usage.*`)

Lifetime usage statistics.

| Field | Type | Units | Description |
|-------|------|-------|-------------|
| `auger` | integer | seconds | Total auger runtime |
| `grill_clean_countdown` | integer | cycles | Countdown to cleaning |
| `ac_ignitor` | integer | seconds | AC ignitor runtime |
| `time` | integer | seconds | Total usage time |
| `ui.screen_on` | integer | seconds | Screen on time |
| `error_stats` | object | - | Error occurrence counts |
| `error_stats.bad_thermocouple` | integer | count | Thermocouple errors |
| `error_stats.ignite_fail` | integer | count | Ignition failures |
| `error_stats.auger_ovrcur` | integer | count | Auger overcurrent |
| `error_stats.ign_ac_disco` | integer | count | AC ignitor disconnect |
| `error_stats.overheat` | integer | count | Overheat events |
| `error_stats.lowtemp` | integer | count | Low temperature events |
| `error_stats.auger_disco` | integer | count | Auger disconnect |
| `error_stats.low_ambient` | integer | count | Low ambient temp |
| `error_stats.ign_dc_disco` | integer | count | DC ignitor disconnect |
| `error_stats.fan_disco` | integer | count | Fan disconnect |
| `fan` | integer | seconds | Total fan runtime |
| `runtime` | integer | seconds | Total grill runtime |
| `hotrod` | integer | seconds | Hotrod runtime |
| `dc_ignitor` | integer | seconds | DC ignitor runtime |
| `light` | integer | seconds | Light runtime |
| `grease_trap_clean_countdown` | integer | cycles | Grease trap countdown |
| `cook_cycles` | integer | count | Total cook cycles completed |

### Custom Cook Object (`custom_cook.*`)

Stored cook programs/recipes.

| Field | Type | Description |
|-------|------|-------------|
| `cook_cycles` | array | Array of stored cook cycles |

#### Cook Cycle Structure
| Field | Type | Description |
|-------|------|-------------|
| `num_steps` | integer | Number of steps in cycle |
| `recipe_id` | string | Recipe identifier |
| `slot_num` | integer | Storage slot (0-9) |
| `cycle_name` | string | User-defined name |
| `populated` | integer | Slot has data (0, 1) |
| `food_type` | integer | Food type identifier |
| `units` | integer | Temperature units |
| `steps` | array | Array of cook steps |

#### Cook Step Structure
| Field | Type | Description |
|-------|------|-------------|
| `probe_set_temp` | integer | Target probe temperature |
| `time_set` | integer | Duration in seconds |
| `keepwarm` | integer | Keep warm after step |
| `smoke` | integer | Smoke mode enabled |
| `step_num` | integer | Step number (1-based) |
| `set_temp` | integer | Grill temperature (0 = probe-based) |
| `use_timer` | integer | Use timer vs probe |

### Details Object (`details.*`)

Device metadata and registration info.

| Field | Type | Description |
|-------|------|-------------|
| `thingName` | string | Device identifier |
| `userId` | string | Owner user ID (UUID) |
| `lastConnectedOn` | integer | Last connection timestamp |
| `thingNameLower` | string | Lowercase device ID |
| `friendlyName` | string | User-assigned name |
| `lat` | float | Latitude coordinate |
| `long` | float | Longitude coordinate |
| `deviceType` | string | Device model number |

## Data Patterns and Insights

### Update Frequency
- Normal operation: ~30 second intervals
- Real-time mode: More frequent updates
- 37% of messages have `real_time` flag set

### Temperature Patterns
- Grill temperature range: 70-448°F
- Common set temperatures: 400°F (50%), 225°F (34%), 250°F (15%)
- Ambient temperature: 71-117°F (avg 97°F)

### Pellet Level Distribution
- 90%: 54% of readings (full hopper)
- 95%: 30% of readings
- 0-40%: 16% of readings (various levels)

### Cook Sessions
- 58% of messages have active cook_id
- Cook IDs follow pattern: `{THING_NAME}{TIMESTAMP}`
- 84% of messages have active cook timer

### Probe Usage
- Wired probes: 40% of messages
- Bluetooth probes: 27% of messages
- Multiple probes common (BT0 + BT1)

### Time Synchronization
- Grill time shows consistent -5 hour offset from database time
- Suggests grill uses UTC-5 (EST) regardless of actual timezone

## Implementation Notes

### Data Storage
1. Messages are deduplicated using `stateIndex`
2. Unique constraint prevents duplicate (topic, state_index) pairs
3. NULL state_index allowed for messages without this field

### Client Processing
1. `system_status` maps to application's `GrillState` enum
2. Accessories parsed into `ProbeData` objects
3. Temperature predictions calculated from historical data
4. Raw payload preserved for debugging

### Best Practices
1. Always check `connected` status before using data
2. Handle missing probe data gracefully
3. Consider timezone offset when displaying times
4. Monitor `errors` field for device issues
5. Use `real_time` flag to adjust UI update frequency

## Version History
- Schema Version 2.0: Current version documented here
- Last Updated: 2025-05-30