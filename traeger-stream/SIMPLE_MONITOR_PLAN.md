# Ultra-Simple Traeger Monitor - Implementation Plan

## Overview
A radically simplified three-component architecture where everything communicates through a shared SQLite database. No APIs, no events, no message queues - just files reading and writing to SQLite.

## Architecture

### Three Core Components

1. **monitor.py** - Collects data from grill → saves to SQLite (~50 lines)
2. **predict.py** - Reads SQLite → returns predictions (~100 lines)  
3. **web/server.py** - Flask server serving static files + JSON API (~50 lines)

### File Structure
```
traeger-monitor/
├── pyproject.toml       # UV dependencies
├── monitor.py           # MQTT → SQLite daemon
├── predict.py           # Prediction functions
├── web/
│   ├── server.py        # Flask web server
│   ├── static/
│   │   ├── index.html   # Single page (~100 lines)
│   │   ├── style.css    # Basic styling (~50 lines)
│   │   └── app.js       # Vanilla JS (~100 lines)
│   └── __init__.py
└── data/
    └── traeger.db       # Shared SQLite database
```

## Component Details

### monitor.py
- Connects to Traeger MQTT using existing TraegerClient code
- On each message: writes directly to SQLite
- Handles reconnection on failure
- Runs forever as background daemon
- No callbacks, no buffers, no APIs

### predict.py
Pure functions for predictions:
```python
def predict(cook_id: str, probe_id: str) -> dict:
    """Read temps from DB, return prediction"""
    data = read_recent_temps_from_db(cook_id, probe_id)
    if len(data) > 20:
        return xgboost_predict(data)
    else:
        return linear_predict(data)
```
- No state, no running service
- Called directly by web server when needed

### web/server.py
Minimal Flask server with 3 endpoints:
```python
@app.route('/api/current')
def get_current():
    """Latest grill status from DB"""
    
@app.route('/api/history/<hours>')
def get_history(hours):
    """Temperature history for charting"""
    
@app.route('/api/predict/<cook_id>/<probe_id>')
def get_prediction(cook_id, probe_id):
    """Call predict.py function, return result"""
```

### Frontend (static files)
- **index.html**: Single page, no framework
- **app.js**: Vanilla JavaScript, no build step
- **style.css**: Basic responsive styling
- **Plotly via CDN**: For interactive charts
- Polls backend every 30 seconds

## Dependencies (pyproject.toml)
```toml
[project]
name = "traeger-monitor"
version = "0.1.0"
dependencies = [
    "flask",
    "python-dotenv",
    "asyncio-mqtt",
    "boto3",
    "paho-mqtt",
    "pandas",
    "xgboost",
]
```

## Running the System
```bash
# Install dependencies
uv sync

# Terminal 1 - Start monitor (runs forever)
uv run python monitor.py

# Terminal 2 - Start web server
uv run python web/server.py

# Open browser to http://localhost:5000
```

## Key Design Decisions

### Simplifications
- **No APIs between components** - SQLite is the only integration point
- **No events/callbacks** - UI polls database on timer
- **No JavaScript bundling** - Just static files served by Flask
- **No microservices** - Predictor is just a function, not a service
- **No in-memory state** - Database is the only state

### What We Keep
- Existing TraegerClient authentication/MQTT logic
- XGBoost and linear prediction algorithms
- Interactive temperature charts
- Historical data viewing

### What We Remove
- Streamlit and all its complexity
- StreamBuffer and in-memory caching
- Callback chains
- Complex async coordination
- All the various data transformation layers

## Implementation Order
1. Create new directory structure
2. Extract monitor.py from existing TraegerClient
3. Extract predict.py from existing predictor classes
4. Create simple Flask server
5. Build minimal HTML/JS frontend
6. Test end-to-end

## Testing Plan

### 1. Testing monitor.py

#### Unit Tests
- Mock MQTT broker to verify message handling
- Test database writes and deduplication logic
- Verify reconnection after disconnect
- Test token refresh logic

#### Integration Tests
```bash
# Verify monitor is saving data
uv run python monitor.py  # Run for 5 minutes
sqlite3 data/traeger.db "SELECT COUNT(*) FROM raw_messages;"
sqlite3 data/traeger.db "SELECT datetime(timestamp, 'localtime'), topic FROM raw_messages ORDER BY timestamp DESC LIMIT 10;"

# Check for duplicates (should return no rows)
sqlite3 data/traeger.db "SELECT topic, state_index, COUNT(*) as count FROM raw_messages GROUP BY topic, state_index HAVING count > 1;"
```

#### Continuous Operation Test
- Run for 24 hours to verify:
  - Token refresh works (tokens expire)
  - MQTT reconnection works
  - No memory leaks
  - Database growth is reasonable

### 2. Testing predict.py

#### Unit Tests
```python
# test_predict.py
def test_linear_prediction():
    # Insert test data with < 20 points
    result = predict("test_cook_1", "probe_1")
    assert result['method'] == 'linear'
    assert 0 < result['minutes_to_target'] < 300

def test_xgboost_prediction():
    # Insert test data with > 20 points
    result = predict("test_cook_2", "probe_1")
    assert result['method'] == 'xgboost'
    assert result['confidence'] is not None

def test_edge_cases():
    # Test with no data, target reached, etc.
    result = predict("no_data", "probe_1")
    assert result['error'] == 'Insufficient data'
```

#### Accuracy Validation
- Use historical cook data to verify predictions improve over time
- Ensure predictions are reasonable (not negative, not years)

### 3. Testing web/server.py

#### API Tests
```bash
# Start server
uv run python web/server.py

# Test all endpoints
curl http://localhost:5000/api/current
curl http://localhost:5000/api/history/24
curl http://localhost:5000/api/predict/cook123/probe1

# Verify JSON responses are valid
curl -s http://localhost:5000/api/current | python -m json.tool
```

#### Frontend Tests
- Manual browser testing:
  - Charts render correctly with Plotly
  - Auto-refresh works every 30 seconds
  - Responsive design on mobile
  - No JavaScript console errors

#### Load Test
```bash
# Simple concurrent request test
for i in {1..100}; do
    curl http://localhost:5000/api/history/24 &
done
wait
```

### 4. End-to-End Testing

#### Full System Test Checklist
- [ ] Monitor connects to MQTT successfully
- [ ] Database receives new messages
- [ ] No duplicate messages in database
- [ ] Web server starts without errors
- [ ] API endpoints return valid JSON
- [ ] Frontend displays current temperature
- [ ] Chart renders with historical data
- [ ] Predictions appear when enough data collected
- [ ] Auto-refresh updates display every 30 seconds
- [ ] System runs stable for 1+ hours

#### Smoke Tests
```bash
# Quick verification script
uv run python monitor.py --test-connection  # Verify MQTT connection
uv run python predict.py --test            # Test with sample data
curl http://localhost:5000/api/current    # Verify web server
```

### 5. Testing Tools & Setup

```bash
# Add test dependencies
uv add --dev pytest pytest-asyncio pytest-mock

# Create test database
cp data/traeger.db data/test_traeger.db

# Monitor logs and database
uv run python monitor.py 2>&1 | tee monitor.log
tail -f monitor.log | grep -E "(ERROR|WARNING|Connected|Saved)"
watch -n 10 'ls -lh data/traeger.db'
```

### 6. Success Criteria

**Monitor Success**:
- Runs continuously without crashes
- Handles all disconnection scenarios
- Zero duplicate messages
- < 50MB/day database growth

**Predictor Success**:
- Response time < 100ms
- Predictions within 20% of actual
- Graceful handling of edge cases

**Web UI Success**:
- Page load < 2 seconds
- Smooth chart interactions
- Mobile responsive
- No memory leaks in browser

### 7. Comparison Testing

Run both old and new systems in parallel to verify:
```bash
# Compare message counts
OLD_COUNT=$(sqlite3 old_app.db "SELECT COUNT(*) FROM raw_messages WHERE timestamp > datetime('now', '-1 hour');")
NEW_COUNT=$(sqlite3 data/traeger.db "SELECT COUNT(*) FROM raw_messages WHERE timestamp > datetime('now', '-1 hour');")
echo "Old: $OLD_COUNT, New: $NEW_COUNT"
```

## Total Lines of Code
- monitor.py: ~50 lines
- predict.py: ~100 lines
- server.py: ~50 lines
- index.html: ~100 lines
- app.js: ~100 lines
- style.css: ~50 lines
- **Total: ~450 lines**

This is roughly 10% of the current codebase while maintaining all core functionality.