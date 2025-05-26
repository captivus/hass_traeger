# Traeger Stream

A clean, Python-native library for streaming live data from Traeger grills with real-time web visualization.

## Features

- 📊 **Real-time Data Streaming** - Get live updates from your Traeger grill via MQTT WebSocket
- 🌐 **Interactive Web Dashboard** - Beautiful Streamlit interface with Plotly charts
- 🌡️ **Multi-Probe Support** - Monitor grill and up to 4 probe temperatures
- ⏱️ **Smart Temperature Predictions** - ML-powered time-to-target predictions for each probe
- 📱 **Mobile Friendly** - Responsive design works on any device
- 💾 **Data Persistence** - SQLite storage with historical data viewing
- 📈 **Data Export** - Export cook data for analysis
- 🔒 **Type-Safe** - Pydantic models for all data structures

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/traeger-stream.git
cd traeger-stream

# Install dependencies with uv
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your Traeger credentials
```

## Quick Start

### 1. Simple Console Monitor

```python
python examples/simple_monitor.py
```

This will connect to your grill and print status updates to the console.

### 2. Web Dashboard

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser to see the live dashboard.

### Timezone Configuration

By default, the app displays times in America/Chicago (CDT/CST) timezone. To use a different timezone, set the `TIMEZONE` environment variable:

```bash
# Use Eastern Time
TIMEZONE=America/New_York streamlit run app.py

# Use Pacific Time  
TIMEZONE=America/Los_Angeles streamlit run app.py

# Use UTC
TIMEZONE=UTC streamlit run app.py
```

Or add it to your `.env` file:
```
TIMEZONE=America/New_York
```

## Temperature Predictions

The app includes intelligent temperature prediction that estimates time to reach target temperature for each probe. The prediction system uses:

- **Physics-based modeling** - Uses heat transfer principles and real-time temperature curves
- **Machine learning ready** - Can be trained on your historical cook data for improved accuracy
- **Confidence indicators** - Shows prediction confidence based on available data
- **Real-time updates** - Predictions improve as more temperature data is collected

### How the Physics-Based Model Works

The physics-based predictor provides immediate, reasonable predictions without requiring training data:

1. **Temperature History Tracking**
   - Maintains a rolling 5-minute history of temperature readings for each probe
   - Calculates instantaneous heating rate from the last 60 seconds
   - Tracks temperature acceleration to detect changes in heating rate

2. **Smart Heating Rate Analysis**
   - Calculates current heating rate in °F/minute when sufficient data exists
   - Uses weighted averaging to smooth out temperature fluctuations
   - Detects and adapts to temperature stalls

3. **Non-Linear Heating Compensation**
   - Recognizes that food heats faster when cold and slower near target
   - Calculates cooking progress: `(current_temp - ambient) / (target_temp - ambient)`
   - Applies 1.3x multiplier for the final 30% of cooking (progress > 0.7)

4. **Grill State Awareness**
   - Only makes predictions when grill is at operating temperature (≥90% of set temp)
   - Prevents unreliable predictions during startup or temperature changes
   - Adjusts for temperature differential between grill and food

5. **Empirical Fallback Estimates**
   - Base heating rate: 3°F/minute (typical for proteins at 250°F)
   - Adjusts based on: `base_rate * (0.5 + (grill_temp - food_temp)/100 * 0.5)`
   - Provides estimates even with limited temperature history

6. **Confidence-Based Display**
   - High confidence (>0.7): Shows as "~15 minutes"
   - Low confidence (<0.7): Shows as "~15 minutes (estimate)"
   - No prediction when grill is heating up or data is insufficient

### Physics Principles Applied

The model incorporates several heat transfer principles:

- **Newton's Law of Cooling/Heating**: Rate of temperature change proportional to temperature difference
- **Thermal Mass Effects**: Larger/denser foods heat more slowly
- **Boundary Layer Phenomena**: Accounts for evaporative cooling ("the stall")
- **Asymptotic Temperature Approach**: Heating slows as food nears grill ambient temperature

### Training Custom Models

Once you have sufficient cooking data, you can train a custom ML model:

```bash
# Analyze your temperature data
uv run python analyze_temperature_data.py

# Train the ML model
uv run python train_temperature_model.py
```

The system will automatically use your trained model for more accurate predictions based on your specific grill and cooking patterns.

## Architecture

```
                                                  
   Traeger       →    Client        →   Stream    
    Grill            (MQTT)             Buffer    
                        ↓                   ↓     
                   Predictor          Storage     
                        ↓                   ↓     
                                           ↓      
                                      Streamlit   
                                         Web      
                                                  
```

### Core Components

- **`traeger_client/`** - Clean async client for Traeger API and MQTT
  - AWS Cognito authentication with auto-refresh
  - WebSocket MQTT connection management
  - Type-safe command interface
  - Temperature prediction engine

- **`streaming/`** - Data streaming and buffering
  - Circular buffer for time-series data
  - Pandas DataFrame conversion for plotting
  - Event-driven callbacks

- **`app.py`** - Streamlit web application
  - Real-time temperature charts with target lines
  - Grill controls (temperature, probes, shutdown)
  - Auto-refreshing interface
  - Time-to-target predictions

## Usage

### Connect to Grill

```python
from traeger_client import TraegerClient

client = TraegerClient(username, password)
await client.connect()
```

### Monitor Status

```python
def on_status(status):
    print(f"Grill: {status.grill_temperature}°F")
    print(f"Probe 1: {status.probes[0].temperature}°F")
    if status.probes[0].predicted_time_to_target:
        print(f"Time to target: ~{status.probes[0].predicted_time_to_target:.0f} minutes")

client.add_status_callback(on_status)
```

### Send Commands

```python
from traeger_client.models import GrillCommand

# Set temperature
cmd = GrillCommand.set_temperature("grill_id", 225)
await client.send_command(cmd)

# Set probe target
cmd = GrillCommand.set_probe_temperature("grill_id", 203)
await client.send_command(cmd)
```

## Data Models

### GrillStatus
- `thing_name`: Unique grill identifier
- `friendly_name`: Human-readable name
- `state`: Current operational state (IDLE, SMOKING, etc.)
- `grill_temperature`: Current grill temperature
- `probes`: List of probe data
- `fan_speed`: Fan speed percentage

### ProbeData
- `temperature`: Current probe temperature
- `target_temperature`: Target temperature
- `is_connected`: Connection status
- `alarm_fired`: Alert status
- `predicted_time_to_target`: Estimated minutes to reach target
- `prediction_confidence`: Confidence level (0-1)

## Development

```bash
# Run tests
pytest

# Format code
black .

# Lint
ruff check .
```

## License

This project is licensed under the GNU General Public License v2.0 - see the LICENSE file for details.

## Acknowledgments

- Learned from this great [hass-traeger](https://github.com/sebirdman/hass_traeger) project
- Uses Traeger's unofficial API (subject to change)