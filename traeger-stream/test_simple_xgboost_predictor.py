#!/usr/bin/env python3
"""Test simple XGBoost predictor that trains on current cook only."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import xgboost as xgb
from collections import deque
import matplotlib.pyplot as plt

class SimpleXGBoostPredictor:
    """Simple XGBoost predictor that trains on current cook data only."""
    
    def __init__(self):
        self.data_history = deque(maxlen=1000)  # Keep last 1000 points
        self.model = None
        self.min_training_points = 20
        self.retrain_interval = 10
        
    def add_reading(self, probe_temp, grill_temp, grill_set, ambient_temp, target_temp):
        """Add a reading and potentially retrain model."""
        self.data_history.append({
            'timestamp': datetime.now(),
            'probe_temp': probe_temp,
            'grill_temp': grill_temp, 
            'grill_set': grill_set,
            'ambient_temp': ambient_temp,
            'target_temp': target_temp
        })
        
        # Train or retrain model
        n_points = len(self.data_history)
        if n_points >= self.min_training_points:
            if self.model is None or n_points % self.retrain_interval == 0:
                self._train_model()
                
    def _calculate_features(self, idx=None):
        """Calculate features for a given index (default: latest)."""
        if idx is None:
            idx = len(self.data_history) - 1
            
        data = list(self.data_history)
        current = data[idx]
        
        # Basic features
        features = {
            'probe_temp': current['probe_temp'],
            'grill_temp': current['grill_temp'],
            'grill_set': current['grill_set'],
            'ambient_temp': current['ambient_temp'],
            'grill_probe_diff': current['grill_temp'] - current['probe_temp'],
            'grill_set_diff': current['grill_set'] - current['grill_temp'],
            'probe_target_diff': current['target_temp'] - current['probe_temp']
        }
        
        # Time features
        start_time = data[0]['timestamp']
        features['minutes_elapsed'] = (current['timestamp'] - start_time).total_seconds() / 60
        
        # Rolling features (last 5 points)
        if idx >= 5:
            recent_temps = [data[i]['probe_temp'] for i in range(idx-4, idx+1)]
            features['probe_temp_mean_5'] = np.mean(recent_temps)
            features['probe_temp_std_5'] = np.std(recent_temps)
            features['probe_temp_change_5'] = current['probe_temp'] - data[idx-5]['probe_temp']
        else:
            features['probe_temp_mean_5'] = current['probe_temp']
            features['probe_temp_std_5'] = 0
            features['probe_temp_change_5'] = 0
            
        # Rate features
        if idx > 0:
            time_diff = (current['timestamp'] - data[idx-1]['timestamp']).total_seconds() / 60
            if time_diff > 0:
                features['probe_rate'] = (current['probe_temp'] - data[idx-1]['probe_temp']) / time_diff
            else:
                features['probe_rate'] = 0
        else:
            features['probe_rate'] = 0
            
        return features
    
    def _calculate_target(self, idx):
        """Calculate minutes to target for training."""
        data = list(self.data_history)
        current = data[idx]
        target_temp = current['target_temp']
        
        if current['probe_temp'] >= target_temp:
            return 0
            
        # Find when target was reached
        for future_idx in range(idx + 1, len(data)):
            if data[future_idx]['probe_temp'] >= target_temp:
                time_diff = (data[future_idx]['timestamp'] - current['timestamp']).total_seconds() / 60
                return time_diff
                
        # Target not reached yet - can't use this point for training
        return None
        
    def _train_model(self):
        """Train model on current cook data."""
        # Prepare training data
        X = []
        y = []
        
        # Only use points where we know the outcome
        for i in range(len(self.data_history) - 1):
            target = self._calculate_target(i)
            if target is not None:
                features = self._calculate_features(i)
                X.append(list(features.values()))
                y.append(target)
                
        if len(X) < 10:  # Need some training data
            return
            
        # Train XGBoost
        self.model = xgb.XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            objective='reg:squarederror'
        )
        
        # Convert to numpy arrays with feature names
        feature_names = list(self._calculate_features(0).keys())
        X = np.array(X)
        y = np.array(y)
        
        self.model.fit(X, y)
        print(f"Trained model with {len(X)} samples")
        
        # Show feature importance
        if hasattr(self.model, 'feature_importances_'):
            importance = sorted(zip(feature_names, self.model.feature_importances_), 
                              key=lambda x: x[1], reverse=True)
            print("Top features:", [(f, round(imp, 3)) for f, imp in importance[:5]])
        
    def predict(self, probe_temp, grill_temp, grill_set, ambient_temp, target_temp):
        """Predict time to target."""
        # Add current reading
        self.add_reading(probe_temp, grill_temp, grill_set, ambient_temp, target_temp)
        
        if self.model is None:
            # Simple linear fallback
            if len(self.data_history) >= 5:
                recent_rate = (probe_temp - list(self.data_history)[-5]['probe_temp']) / 5
                if recent_rate > 0:
                    return (target_temp - probe_temp) / recent_rate
            return None
            
        # Use XGBoost model
        features = self._calculate_features()
        X = [list(features.values())]
        prediction = self.model.predict(X)[0]
        return prediction


def test_on_todays_cook():
    """Test the simple predictor on today's cook data."""
    # Load today's cook
    df = pd.read_csv('analyzed_165_cook.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Initialize predictor
    predictor = SimpleXGBoostPredictor()
    
    # Simulate real-time predictions
    predictions = []
    actuals = []
    temps = []
    times = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Skip if already at target
        if row['temperature'] >= 165:
            continue
            
        # Predict
        pred = predictor.predict(
            probe_temp=row['temperature'],
            grill_temp=row['grill_temp'],
            grill_set=row['grill_set'],
            ambient_temp=row['ambient'],
            target_temp=165
        )
        
        if pred is not None and i % 2 == 0:  # Log every 2nd point
            # Calculate actual
            future = df[df.index > i]
            reached = future[future['temperature'] >= 165]
            if len(reached) > 0:
                actual_time = (reached.iloc[0]['timestamp'] - row['timestamp']).total_seconds() / 60
                
                predictions.append(pred)
                actuals.append(actual_time)
                temps.append(row['temperature'])
                times.append(row['minutes'])
                
                print(f"At {row['minutes']:.1f} min, {row['temperature']}°F: "
                      f"Predicted {pred:.1f} min, Actual {actual_time:.1f} min, "
                      f"Error {abs(pred - actual_time):.1f} min")
    
    # Calculate metrics
    if predictions:
        errors = [abs(p - a) for p, a in zip(predictions, actuals)]
        print(f"\nMean Absolute Error: {np.mean(errors):.2f} minutes")
        print(f"Max Error: {max(errors):.2f} minutes")
        print(f"Predictions made: {len(predictions)}")
        
        # Plot results
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        # Predictions vs Actuals
        ax1.scatter(times, predictions, label='Predicted', alpha=0.7)
        ax1.scatter(times, actuals, label='Actual', alpha=0.7)
        ax1.set_xlabel('Time (minutes)')
        ax1.set_ylabel('Minutes to Target')
        ax1.set_title('Simple XGBoost: Predictions vs Actual')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Errors over time
        ax2.plot(times, errors, 'o-')
        ax2.set_xlabel('Time (minutes)')
        ax2.set_ylabel('Prediction Error (minutes)')
        ax2.set_title('Prediction Error Over Time')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('simple_xgboost_test.png')
        print("\nSaved plot to simple_xgboost_test.png")


if __name__ == "__main__":
    test_on_todays_cook()