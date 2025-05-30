# Machine Learning Model Recommendations for Probe Temperature Prediction

## Analysis Results

Based on the feature analysis of your Traeger data, I found several key insights:

### Key Feature Correlations with Temperature Rate:
1. **grill_probe_diff** (0.166): The temperature difference between grill and probe
2. **grill_set** (0.130): The target grill temperature
3. **grill_temp** (0.114): The actual grill temperature
4. **probe_target_diff** (0.111): How far the probe is from target

### Important Findings:
- When you increased grill temp from 225°F to 400°F, the probe heating rate increased dramatically
- The temperature differential between grill and probe is the strongest predictor
- Smoke mode has a negative correlation (-0.127) with heating rate

## ML Model Recommendations

### 1. **XGBoost Regressor** (Recommended)
**Why:** 
- Excellent for non-linear relationships
- Handles feature interactions naturally (e.g., grill_temp × temperature_differential)
- Built-in feature importance analysis
- Fast training and prediction
- Handles missing data well

**Libraries needed:**
```bash
pip install xgboost scikit-learn
```

**Key features to use:**
- Current probe temperature
- Target probe temperature  
- Grill temperature (actual)
- Grill set temperature
- Temperature differentials (grill-probe, grill_set-grill, target-probe)
- Ambient temperature
- Smoke mode indicator
- Time-based features (minutes since cook start)
- Rolling averages of temperature rate (last 5, 10 minutes)

### 2. **Random Forest Regressor** (Alternative)
**Why:**
- Good baseline model
- Naturally captures non-linear patterns
- Less prone to overfitting
- Easy to interpret

**Pros:** Simple to implement, good performance
**Cons:** Slower than XGBoost, larger model size

### 3. **Neural Network (LSTM)** (Advanced Option)
**Why:**
- Can learn complex temporal patterns
- Handles sequential nature of temperature data
- Can learn phase transitions (stall → rapid rise)

**Libraries needed:**
```bash
pip install tensorflow keras
```

**Cons:** Requires more data, harder to interpret, longer training time

### 4. **Ensemble Approach** (Best Performance)
Combine multiple models:
1. XGBoost for general predictions
2. Phase detector (classifier) to identify cooking phases:
   - Initial warming
   - Stall phase
   - Rapid rise phase
3. Phase-specific predictors

## Implementation Strategy

### Phase 1: XGBoost Base Model
```python
features = [
    'probe_temp',
    'grill_temp', 
    'grill_set',
    'ambient_temp',
    'grill_probe_diff',
    'grill_set_diff',
    'probe_target_diff',
    'smoke_mode',
    'probe_rate_5min_avg',    # Rolling average
    'probe_rate_10min_avg',   # Rolling average
    'minutes_cooking',        # Time since cook start
    'probe_temp_lag_5min',    # Temperature 5 minutes ago
]

target = 'time_to_target'  # Minutes until probe reaches target
```

### Phase 2: Feature Engineering
1. **Rolling statistics**: Mean, std of temperature rates over different windows
2. **Lag features**: Previous temperatures and rates
3. **Interaction features**: grill_temp × grill_probe_diff
4. **Polynomial features**: probe_temp², grill_probe_diff²

### Phase 3: Model Training Pipeline
1. Collect labeled training data (actual time to target)
2. Feature engineering
3. Train/test split with time-based splitting
4. Hyperparameter tuning with cross-validation
5. Model evaluation on holdout set

## Data Requirements

To train an effective model, we need:
1. **Multiple complete cook sessions** with various:
   - Target temperatures
   - Grill settings
   - Meat types/sizes
2. **Ground truth labels**: Actual time it took to reach target
3. **Minimum 50-100 cook sessions** for reliable predictions

## Quick Start Implementation

```python
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

# Prepare features (X) and target (y)
# X = feature matrix, y = actual time to target

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Train model
model = xgb.XGBRegressor(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1,
    objective='reg:squarederror'
)

model.fit(X_train, y_train)

# Evaluate
predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
print(f"Mean Absolute Error: {mae:.1f} minutes")
```

## Next Steps

1. **Data Collection**: Set up automated collection of cook sessions with ground truth
2. **Feature Pipeline**: Build real-time feature engineering
3. **Model Training**: Start with XGBoost on historical data
4. **Evaluation**: Test on new cook sessions
5. **Deployment**: Integrate into the Traeger client

## Libraries You'll Need

```bash
# Core ML libraries
pip install scikit-learn xgboost pandas numpy

# For neural networks (optional)
pip install tensorflow

# For model persistence
pip install joblib

# For real-time feature engineering
pip install scipy
```

This approach will give you much more accurate predictions than the simple derivative model, especially when you change grill settings mid-cook!