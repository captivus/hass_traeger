# ML Temperature Prediction Implementation Plan

## Overview
Replace the current simple derivative-based predictor with an XGBoost model that considers multiple factors including grill temperature, ambient conditions, and cooking patterns.

## Architecture Design

### 1. Data Collection Layer

#### 1.1 Cook Session Tracking
```python
# traeger_client/cook_session.py
class CookSession:
    """Tracks a complete cooking session for training data."""
    
    def __init__(self, grill_id: str, start_time: datetime):
        self.grill_id = grill_id
        self.start_time = start_time
        self.data_points = []
        self.target_reached_times = {}  # probe_id -> timestamp
        
    def add_data_point(self, status: GrillStatus):
        """Add a data point with all relevant features."""
        for probe in status.probes:
            if probe.connected and probe.target_temperature:
                self.data_points.append({
                    'timestamp': datetime.now(),
                    'probe_id': probe.id,
                    'probe_temp': probe.temperature,
                    'probe_target': probe.target_temperature,
                    'grill_temp': status.grill_temperature,
                    'grill_set': status.set_temperature,
                    'ambient_temp': status.ambient_temperature,
                    'smoke_mode': status.smoke_mode,
                    'cook_id': status.cook_id,
                    # Track when target was reached
                    'target_reached': probe.temperature >= probe.target_temperature
                })
```

#### 1.2 Storage Extension
```python
# Extend storage.py to save cook sessions
async def save_cook_session(self, session: CookSession):
    """Save completed cook session for training."""
    # Create new table: cook_sessions
    # Store: session_id, grill_id, start_time, end_time, data_json
```

### 2. Feature Engineering Pipeline

#### 2.1 Real-time Feature Calculator
```python
# traeger_client/ml_features.py
class FeatureEngineering:
    """Real-time feature engineering for predictions."""
    
    def __init__(self):
        self.history_window = 20  # minutes
        self.temp_history = {}    # probe_id -> list of (timestamp, temp)
        
    def calculate_features(self, 
                          current_status: GrillStatus, 
                          probe: ProbeStatus,
                          history: List[dict]) -> dict:
        """Calculate all features for prediction."""
        
        features = {
            # Current state
            'probe_temp': probe.temperature,
            'grill_temp': current_status.grill_temperature,
            'grill_set': current_status.set_temperature,
            'ambient_temp': current_status.ambient_temperature,
            
            # Differentials
            'grill_probe_diff': current_status.grill_temperature - probe.temperature,
            'grill_set_diff': current_status.set_temperature - current_status.grill_temperature,
            'probe_target_diff': probe.target_temperature - probe.temperature,
            
            # Time features
            'minutes_cooking': self._get_cook_duration(history),
            
            # Rolling statistics
            'probe_temp_mean_5': self._rolling_mean(history, 5),
            'probe_temp_std_5': self._rolling_std(history, 5),
            'probe_rate_5': self._temperature_rate(history, 5),
            
            # Binary features
            'high_grill_temp': int(current_status.set_temperature > 300),
            'smoke_mode': int(current_status.smoke_mode),
            
            # Lag features
            'probe_temp_lag_5': self._get_lag_temp(history, 5),
            'grill_temp_lag_5': self._get_lag_grill_temp(history, 5),
        }
        
        return features
```

### 3. Model Training Pipeline

#### 3.1 Offline Training Script
```python
# traeger_client/train_model.py
class ModelTrainer:
    """Train XGBoost models from historical cook data."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self.models = {}  # grill_id -> trained model
        
    async def train_models(self, min_sessions: int = 10):
        """Train models for each grill with sufficient data."""
        
        for grill_id in await self.storage.get_all_grill_ids():
            sessions = await self.storage.get_cook_sessions(grill_id)
            
            if len(sessions) >= min_sessions:
                X, y = self._prepare_training_data(sessions)
                
                model = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    objective='reg:squarederror'
                )
                
                # Time series split for validation
                X_train, X_val, y_train, y_val = self._time_series_split(X, y)
                model.fit(X_train, y_train)
                
                # Validate
                mae = mean_absolute_error(y_val, model.predict(X_val))
                print(f"Grill {grill_id}: MAE = {mae:.2f} minutes")
                
                # Save model
                await self._save_model(grill_id, model)
```

### 4. Prediction Integration

#### 4.1 ML Temperature Predictor
```python
# traeger_client/ml_temperature_predictor.py
class MLTemperaturePredictor:
    """XGBoost-based temperature predictor."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self.models = {}  # grill_id -> model
        self.feature_eng = FeatureEngineering()
        self.fallback_predictor = SimpleTemperaturePredictor()
        self._load_models()
        
    async def predict_time_to_target(self, 
                                    grill_id: str,
                                    probe: ProbeStatus,
                                    current_status: GrillStatus,
                                    history: List[dict]) -> Tuple[Optional[float], Optional[str]]:
        """Predict time to reach target temperature."""
        
        # Check if we have a model for this grill
        if grill_id not in self.models:
            # Fallback to simple predictor
            return self.fallback_predictor.predict_time_to_target(
                probe.id, probe.target_temperature
            )
        
        # Calculate features
        features = self.feature_eng.calculate_features(
            current_status, probe, history
        )
        
        # Convert to DataFrame for XGBoost
        X = pd.DataFrame([features])
        
        # Predict
        try:
            prediction = self.models[grill_id].predict(X)[0]
            
            # Confidence check
            if prediction < 0:
                return None, "Invalid prediction"
            elif prediction > 180:  # 3 hours
                return None, "More than 3 hours"
            else:
                return prediction, None
                
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            # Fallback
            return self.fallback_predictor.predict_time_to_target(
                probe.id, probe.target_temperature
            )
```

### 5. Integration Points

#### 5.1 Modify TraegerClient
```python
# In traeger_client/client.py
class TraegerClient:
    def __init__(self, ...):
        # Replace simple predictor
        if self.storage and ml_models_available():
            self.predictor = MLTemperaturePredictor(self.storage)
        else:
            self.predictor = SimpleTemperaturePredictor()
        
        # Cook session tracking
        self.current_sessions = {}  # grill_id -> CookSession
```

#### 5.2 Update GrillStatus Processing
```python
def _handle_status_update(self, thing_name: str, status: dict):
    """Process status update."""
    grill_status = self._parse_status(status)
    
    # Track cook session
    if grill_status.cook_id:
        if thing_name not in self.current_sessions:
            self.current_sessions[thing_name] = CookSession(
                thing_name, datetime.now()
            )
        
        session = self.current_sessions[thing_name]
        session.add_data_point(grill_status)
    
    # Update predictions using ML
    if self.predictor and isinstance(self.predictor, MLTemperaturePredictor):
        history = self._get_recent_history(thing_name, minutes=20)
        for probe in grill_status.probes:
            if probe.connected and probe.target_temperature:
                prediction = await self.predictor.predict_time_to_target(
                    thing_name, probe, grill_status, history
                )
                probe.predicted_time_to_target = prediction[0]
                probe.prediction_message = prediction[1]
```

### 6. Model Management

#### 6.1 Model Versioning & Updates
```python
# traeger_client/model_manager.py
class ModelManager:
    """Manage ML model lifecycle."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self.model_version = "1.0"
        self.retrain_threshold = 50  # sessions
        
    async def check_and_update_models(self):
        """Check if models need retraining."""
        for grill_id in await self.storage.get_all_grill_ids():
            new_sessions = await self.storage.get_sessions_since_last_training(grill_id)
            
            if len(new_sessions) >= self.retrain_threshold:
                await self._retrain_model(grill_id)
    
    async def _retrain_model(self, grill_id: str):
        """Retrain model with new data."""
        trainer = ModelTrainer(self.storage)
        await trainer.train_single_grill(grill_id)
        await self._notify_model_update(grill_id)
```

### 7. Implementation Timeline

#### Phase 1: Data Collection (Week 1-2)
1. Implement CookSession tracking
2. Extend storage with cook_sessions table
3. Deploy to collect training data
4. Add session completion detection

#### Phase 2: Offline Training (Week 3)
1. Implement feature engineering pipeline
2. Create training scripts
3. Train initial models from historical data
4. Validate model performance

#### Phase 3: Integration (Week 4)
1. Create MLTemperaturePredictor
2. Integrate with TraegerClient
3. Add fallback logic
4. Test with live data

#### Phase 4: Deployment (Week 5)
1. Model serving infrastructure
2. A/B testing (ML vs Simple)
3. Performance monitoring
4. User feedback collection

#### Phase 5: Optimization (Week 6+)
1. Model retraining pipeline
2. Feature importance analysis
3. Hyperparameter tuning
4. Additional features (meat type, weather)

### 8. Key Design Decisions

#### 8.1 Model Granularity
- **Per-grill models**: Better accuracy for specific cooking patterns
- **Fallback to global model**: For new grills with insufficient data
- **Cold start**: Use simple predictor until enough data collected

#### 8.2 Feature Storage
- **Real-time calculation**: For current features
- **Historical aggregation**: For rolling statistics
- **Efficient caching**: To avoid recalculation

#### 8.3 Model Updates
- **Incremental learning**: Not supported by XGBoost
- **Periodic retraining**: Every 50 cook sessions
- **A/B testing**: Compare new vs old model before switching

### 9. Configuration

```python
# config.py
ML_CONFIG = {
    'min_training_sessions': 10,
    'retrain_threshold': 50,
    'feature_window_minutes': 20,
    'max_prediction_minutes': 180,
    'model_version': '1.0',
    'features': [
        'probe_temp', 'grill_temp', 'grill_set', 'ambient_temp',
        'grill_probe_diff', 'grill_set_diff', 'probe_target_diff',
        'minutes_cooking', 'probe_temp_mean_5', 'probe_rate_5',
        'high_grill_temp', 'smoke_mode'
    ]
}
```

### 10. Monitoring & Metrics

```python
# traeger_client/ml_metrics.py
class PredictionMetrics:
    """Track ML prediction performance."""
    
    async def log_prediction(self, 
                           grill_id: str,
                           predicted_minutes: float,
                           actual_minutes: float):
        """Log prediction for analysis."""
        await self.storage.save_prediction_log({
            'grill_id': grill_id,
            'timestamp': datetime.now(),
            'predicted': predicted_minutes,
            'actual': actual_minutes,
            'error': abs(predicted_minutes - actual_minutes),
            'model_version': ML_CONFIG['model_version']
        })
```

## Summary

This implementation plan provides:
1. **Gradual rollout**: Collect data → Train models → Deploy with fallback
2. **Production-ready**: Handles edge cases, failures, and new grills
3. **Maintainable**: Clear separation of concerns and monitoring
4. **Scalable**: Per-grill models with efficient feature calculation
5. **User-friendly**: Seamless upgrade from simple to ML predictions

The key is to start collecting cook session data immediately, then gradually introduce ML predictions as models become available.