"""Constants for traeger."""

# Base component constants
NAME = "Traeger"
DOMAIN = "traeger"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.1.0"
ATTRIBUTION = ""
ISSUE_URL = "https://github.com/sebirdman/hass_traeger/issues"

# Icons
ICON = "mdi:format-quote-close"

# Platforms
CLIMATE = "climate"
SENSOR = "sensor"
SWITCH = "switch"
NUMBER = "number"
PLATFORMS = [CLIMATE, SENSOR, SWITCH, NUMBER]

# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_NAME = DOMAIN

# Grill Modes
GRILL_MODE_OFFLINE = 99     # Offline
GRILL_MODE_SHUTDOWN = 9     # Cooled down, heading to sleep
GRILL_MODE_COOL_DOWN = 8    # Cool down cycle
GRILL_MODE_CUSTOM_COOK = 7  # Custom cook
GRILL_MODE_MANUAL_COOK = 6  # Manual cook
GRILL_MODE_PREHEATING = 5   # Preheating
GRILL_MODE_IGNITING = 4     # Igniting
GRILL_MODE_IDLE = 3         # Idle (Power switch on, screen on)
GRILL_MODE_SLEEPING = 2     # Sleeping (Power switch on, screen off)

# Grill Temps
# these are the min temps the traeger app would set
GRILL_MIN_TEMP_C = 75
GRILL_MIN_TEMP_F = 165

# Probe Preset Modes
PROBE_PRESET_MODES = {
        "Chicken": {
            "Fahrenheit": 165,
            "Celsius": 74,
            },
        "Turkey": {
            "Fahrenheit": 165,
            "Celsius": 74,
            },
        "Beef (Rare)": {
            "Fahrenheit": 125,
            "Celsius": 52,
            },
        "Beef (Medium Rare)": {
            "Fahrenheit": 135,
            "Celsius": 57,
            },
        "Beef (Medium)": {
            "Fahrenheit": 140,
            "Celsius": 60,
            },
        "Beef (Medium Well)": {
            "Fahrenheit": 145,
            "Celsius": 63,
            },
        "Beef (Well Done)": {
            "Fahrenheit": 155,
            "Celsius": 68,
            },
        "Beef (Ground)": {
            "Fahrenheit": 160,
            "Celsius": 71,
            },
        "Lamb (Rare)": {
            "Fahrenheit": 125,
            "Celsius": 52,
            },
        "Lamb (Medium Rare)": {
            "Fahrenheit": 135,
            "Celsius": 57,
            },
        "Lamb (Medium)": {
            "Fahrenheit": 140,
            "Celsius": 60,
            },
        "Lamb (Medium Well)": {
            "Fahrenheit": 145,
            "Celsius": 63,
            },
        "Lamb (Well Done)": {
            "Fahrenheit": 155,
            "Celsius": 68,
            },
        "Lamb (Ground)": {
            "Fahrenheit": 160,
            "Celsius": 71,
            },
        "Pork (Medium Rare)": {
            "Fahrenheit": 135,
            "Celsius": 57,
            },
        "Pork (Medium)": {
            "Fahrenheit": 140,
            "Celsius": 60,
            },
        "Pork (Well Done)": {
            "Fahrenheit": 155,
            "Celsius": 68,
            },
        "Fish": {
            "Fahrenheit": 145,
            "Celsius": 63,
            },
        }

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""