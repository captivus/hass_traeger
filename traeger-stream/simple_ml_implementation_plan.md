# Simple ML Implementation Plan

## Core Idea
Train an XGBoost model using ONLY the current cook's data - no database, no historical sessions, no complex infrastructure. Just like we proved it works today!

## How It Works

### 1. Simple In-Memory Training
- Start collecting data when cook begins (probe has target temp)
- After 20 data points (~10 minutes), train initial model
- Retrain every 10 new data points to improve accuracy
- All in memory - no persistence needed

### 2. Direct Replacement
Replace `SimpleTemperaturePredictor` with `XGBoostTemperaturePredictor` that:
- Collects temperature history for current cook only
- Trains model on-the-fly using current cook data
- Falls back to simple linear prediction if < 20 data points
- Resets when new cook starts

### 3. Implementation Steps

#### Step 1: Create XGBoostTemperaturePredictor
```python
# traeger_client/xgboost_temperature_predictor.py
class XGBoostTemperaturePredictor:
    def __init__(self):
        self.cook_data = {}  # probe_id -> list of data points
        self.models = {}     # probe_id -> trained model
        self.min_points = 20 # Need 20 points before first training
        
    def add_reading(self, probe_id, probe_temp, target_temp, 
                   grill_temp, grill_set, ambient_temp):
        """Add data point and retrain if needed."""
        
        # Initialize if new probe
        if probe_id not in self.cook_data:
            self.cook_data[probe_id] = []
            
        # Add data point
        self.cook_data[probe_id].append({
            'timestamp': datetime.now(),
            'probe_temp': probe_temp,
            'target_temp': target_temp,
            'grill_temp': grill_temp,
            'grill_set': grill_set,
            'ambient_temp': ambient_temp
        })
        
        # Train/retrain model
        data_points = len(self.cook_data[probe_id])
        if data_points >= self.min_points:
            if probe_id not in self.models or data_points % 10 == 0:
                self._train_model(probe_id)
    
    def predict_time_to_target(self, probe_id, current_temp, target_temp,
                             grill_temp, grill_set, ambient_temp):
        """Predict minutes to target."""
        
        # Use simple prediction if no model yet
        if probe_id not in self.models:
            return self._simple_prediction(probe_id, current_temp, target_temp)
            
        # Calculate features for current state
        features = self._calculate_features(
            probe_id, current_temp, grill_temp, grill_set, ambient_temp
        )
        
        # Predict
        prediction = self.models[probe_id].predict([features])[0]
        return prediction, None
```

#### Step 2: Modify TraegerClient 
Just change the predictor initialization:
```python
# In client.py __init__:
self.predictor = XGBoostTemperaturePredictor()  # Instead of SimpleTemperaturePredictor

# In update_predictions:
self.predictor.add_reading(
    probe.id, 
    probe.temperature,
    probe.target_temperature,
    status.grill_temperature,
    status.set_temperature,
    status.ambient_temperature
)
```

### 4. Key Features (Calculated Real-time)
- Current temps (probe, grill, ambient)
- Temperature differentials 
- Rolling averages (last 5, 10 readings)
- Rate of change
- Time elapsed
- Grill setting indicators

### 5. Why This Works
- Each cook is unique but follows patterns
- XGBoost learns the pattern after ~10 minutes
- Adapts when you change grill settings
- No need for historical data from other cooks

### 6. Advantages
- SIMPLE - Just one new class
- FAST - Starts working after 10 minutes of cooking
- ADAPTIVE - Learns your current cook's behavior
- NO DEPENDENCIES - No database, no model storage
- IMMEDIATE - Can deploy today

## That's it! No fancy infrastructure needed.