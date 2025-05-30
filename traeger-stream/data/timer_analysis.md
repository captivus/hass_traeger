# Traeger Grill Timer Analysis

## Overview

This document summarizes the findings from analyzing actual Traeger grill timer data during a cooking session on May 30, 2025. The analysis reveals how the Traeger timer system works in practice.

## Timer Data Structure

The Traeger grill uses Unix timestamps for timer management with three primary fields:

- **`cook_timer_start`**: Unix timestamp when the timer was set (e.g., 1748621051 = 2025-05-30 11:04:11)
- **`cook_timer_end`**: Unix timestamp when the timer should complete (e.g., 1748628251 = 2025-05-30 13:04:11)
- **`time`**: Current grill system time (Unix timestamp)
- **`cook_timer_complete`**: Binary flag (0 or 1) indicating timer completion status

Additional system timer fields exist (`sys_timer_start`, `sys_timer_end`, `sys_timer_complete`) but their purpose is less clear.

## Key Findings

### 1. Timer Persistence
- Once set, timer values persist in every MQTT message throughout the cooking session
- Timer values are NOT cleared when cooking stops or the grill enters cool-down mode
- The persistence of timer values does not indicate the timer is still active

### 2. Timer Calculation
- Remaining time = `cook_timer_end - time`
- The grill's internal clock shows a consistent UTC-5 timezone offset
- Timer countdown is based on the grill's system time, not external time

### 3. Real-World Behavior
From the analyzed cooking session:
- A 2-hour (120 minute) timer was set at approximately 11:04 AM
- Timer was scheduled to expire at 1:04 PM
- Cooking actually stopped at 12:55 PM (system_status changed to 2)
- This was approximately 8-9 minutes BEFORE the timer would have expired
- The `cook_timer_complete` flag remained at 0 throughout the entire session

### 4. System Status Correlation
- `system_status = 1`: Active cooking mode (timer is meaningful)
- `system_status = 2`: Cool-down mode (timer values persist but are not active)
- Timer values alone cannot determine if cooking is active - must check system_status

## Implementation Considerations

### Timer State Logic
To properly implement timer display, the following states must be considered:

1. **Not Set**: No timer values present
2. **Active**: Timer is set AND system_status = 1 (cooking)
3. **Stopped Early**: Timer was set but cooking ended before expiration
4. **Expired**: Timer reached zero during active cooking
5. **Completed**: cook_timer_complete = 1 (though this wasn't observed in practice)

### Edge Cases
- Timer values persist even after cooking stops
- Must check system_status to determine if timer display is relevant
- Handle negative remaining time values if timer expires during cooking
- Consider showing "time remaining when stopped" for early termination

### Display Recommendations
- Only show active countdown when system_status indicates cooking
- Clearly indicate when cooking stopped before timer expired
- Use color coding for urgency (green > 10min, yellow 5-10min, orange < 5min, red expired)
- Consider showing elapsed time since timer expired if still cooking

## Data Examples

### Timer Set and Active
```json
{
  "cook_timer_start": 1748621051,
  "cook_timer_end": 1748628251,
  "time": 1748625000,
  "system_status": 1,
  "cook_timer_complete": 0
}
// Remaining time: 3251 seconds (54 minutes)
```

### Cooking Stopped Before Timer
```json
{
  "cook_timer_start": 1748621051,
  "cook_timer_end": 1748628251,
  "time": 1748627751,
  "system_status": 2,
  "cook_timer_complete": 0
}
// Timer had 500 seconds (8.3 minutes) remaining when cooking stopped
```

## Conclusions

The Traeger timer system is more sophisticated than a simple countdown timer. It uses absolute timestamps that persist throughout the cooking session, requiring careful interpretation based on the grill's operating state. The key insight is that timer values alone don't indicate an active timer - the system_status must be checked to determine if the timer is meaningful.

For user interface implementation, this means:
1. Always check system_status before displaying timer information
2. Handle the common case of cooking ending before timer expiration
3. Don't assume timer values will be cleared when cooking stops
4. Consider the timer as a reference point rather than an active countdown when not cooking