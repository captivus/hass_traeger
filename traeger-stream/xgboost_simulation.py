#!/usr/bin/env python3
"""Simulate XGBoost performance on today's cook."""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
import xgboost as xgb
import matplotlib.pyplot as plt
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def prepare_features(df):
    """Prepare features for XGBoost model."""
    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Basic features
    features = df[['temperature', 'grill_temp', 'grill_set', 'ambient']].copy()
    features.columns = ['probe_temp', 'grill_temp', 'grill_set', 'ambient_temp']
    
    # Temperature differentials
    features['grill_probe_diff'] = df['grill_temp'] - df['temperature']
    features['grill_set_diff'] = df['grill_set'] - df['grill_temp']
    features['probe_target_diff'] = df['target'] - df['temperature']
    
    # Time-based features
    features['minutes_elapsed'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
    
    # Rolling statistics (with min_periods to handle start of cook)
    features['probe_temp_rolling_mean_5'] = df['temperature'].rolling(5, min_periods=1).mean()
    features['probe_temp_rolling_std_5'] = df['temperature'].rolling(5, min_periods=1).std().fillna(0)
    
    # Rate of change
    features['probe_temp_change_1'] = df['temperature'].diff().fillna(0)
    features['probe_temp_change_5'] = df['temperature'].diff(5).fillna(0)
    
    # Lag features
    features['probe_temp_lag_5'] = df['temperature'].shift(5).fillna(df['temperature'].iloc[0])
    features['grill_temp_lag_5'] = df['grill_temp'].shift(5).fillna(df['grill_temp'].iloc[0])
    
    # Interaction features
    features['grill_probe_diff_squared'] = features['grill_probe_diff'] ** 2
    features['temp_momentum'] = features['grill_probe_diff'] * features['probe_temp_change_1']
    
    # Binary features
    features['high_grill_temp'] = (df['grill_set'] > 300).astype(int)
    features['large_temp_diff'] = (features['grill_probe_diff'] > 100).astype(int)
    
    return features

def create_targets(df):
    """Create target variable: minutes to reach target temperature."""
    targets = []
    target_temp = 165  # Today's target
    
    for i in range(len(df)):
        current_temp = df.iloc[i]['temperature']
        current_time = df.iloc[i]['timestamp']
        
        if current_temp >= target_temp:
            targets.append(0)
        else:
            # Find when target was reached
            future_data = df[i+1:]
            reached = future_data[future_data['temperature'] >= target_temp]
            
            if len(reached) > 0:
                target_time = reached.iloc[0]['timestamp']
                minutes_to_target = (target_time - current_time).total_seconds() / 60
                targets.append(minutes_to_target)
            else:
                # Never reached target in our data
                targets.append(np.nan)
    
    return targets

def train_and_evaluate_model(features, targets, test_indices):
    """Train XGBoost model and evaluate on test indices."""
    # Remove rows with NaN targets
    valid_mask = ~np.isnan(targets)
    features_valid = features[valid_mask]
    targets_valid = np.array(targets)[valid_mask]
    indices_valid = np.arange(len(targets))[valid_mask]
    
    # Create train/test split ensuring test indices are in test set
    test_mask = np.isin(indices_valid, test_indices)
    train_mask = ~test_mask
    
    X_train = features_valid[train_mask]
    y_train = targets_valid[train_mask]
    X_test = features_valid[test_mask]
    y_test = targets_valid[test_mask]
    
    if len(X_train) == 0 or len(X_test) == 0:
        return None, None, None
    
    # Train XGBoost model
    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        objective='reg:squarederror',
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Make predictions
    predictions = model.predict(X_test)
    
    # Calculate metrics
    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    
    # Get feature importance
    feature_importance = pd.DataFrame({
        'feature': features.columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    return model, predictions, feature_importance

def simulate_realtime_predictions(df, features, targets):
    """Simulate real-time predictions throughout the cook."""
    results = []
    
    # We'll make predictions at these checkpoints
    checkpoints = [10, 20, 30, 40, 50, 55, 60]  # minutes into cook
    
    for checkpoint in checkpoints:
        # Find the index closest to this time
        checkpoint_idx = (df['minutes'] - checkpoint).abs().argmin()
        
        if checkpoint_idx < 20:  # Need some data to train
            continue
            
        # Train on data up to this point
        train_features = features.iloc[:checkpoint_idx]
        train_targets = targets[:checkpoint_idx]
        
        # Remove NaN targets
        valid_mask = ~np.isnan(train_targets)
        if sum(valid_mask) < 10:  # Need enough training data
            continue
            
        train_features_valid = train_features[valid_mask]
        train_targets_valid = np.array(train_targets)[valid_mask]
        
        # Train model
        model = xgb.XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42
        )
        
        model.fit(train_features_valid, train_targets_valid)
        
        # Make prediction for current point
        current_features = features.iloc[checkpoint_idx:checkpoint_idx+1]
        prediction = model.predict(current_features)[0]
        actual = targets[checkpoint_idx]
        
        results.append({
            'checkpoint_minutes': checkpoint,
            'probe_temp': df.iloc[checkpoint_idx]['temperature'],
            'grill_temp': df.iloc[checkpoint_idx]['grill_temp'],
            'grill_set': df.iloc[checkpoint_idx]['grill_set'],
            'predicted_minutes': prediction,
            'actual_minutes': actual,
            'error': abs(prediction - actual) if not np.isnan(actual) else np.nan
        })
    
    return pd.DataFrame(results)

def main():
    # Load the analyzed cook data
    df = pd.read_csv('analyzed_165_cook.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print("=== XGBoost Simulation on Today's Cook ===\n")
    
    # Prepare features
    features = prepare_features(df)
    targets = create_targets(df)
    
    print(f"Total data points: {len(df)}")
    print(f"Valid targets: {sum(~np.isnan(targets))}")
    
    # Simulate real-time predictions
    print("\n=== Real-time Prediction Simulation ===")
    realtime_results = simulate_realtime_predictions(df, features, targets)
    
    print("\nPredictions at various checkpoints:")
    print(realtime_results.to_string(index=False))
    
    # Calculate overall metrics
    valid_errors = realtime_results['error'].dropna()
    if len(valid_errors) > 0:
        print(f"\nOverall Performance:")
        print(f"Mean Absolute Error: {valid_errors.mean():.1f} minutes")
        print(f"Max Error: {valid_errors.max():.1f} minutes")
        print(f"Min Error: {valid_errors.min():.1f} minutes")
    
    # Train on full dataset and show feature importance
    print("\n=== Feature Importance (Full Dataset) ===")
    
    # Split data 80/20 for final evaluation
    test_size = int(0.2 * len(df))
    test_indices = np.random.choice(len(df), size=test_size, replace=False)
    
    model, predictions, feature_importance = train_and_evaluate_model(
        features, targets, test_indices
    )
    
    if feature_importance is not None:
        print("\nTop 10 Most Important Features:")
        print(feature_importance.head(10).to_string(index=False))
    
    # Create visualization
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Plot 1: Temperature curves with prediction points
    ax1 = axes[0, 0]
    ax1.plot(df['minutes'], df['temperature'], 'b-', label='Probe Temp', linewidth=2)
    ax1.plot(df['minutes'], df['grill_temp'], 'r-', label='Grill Temp', alpha=0.7)
    ax1.axhline(y=165, color='g', linestyle='--', label='Target (165°F)')
    
    # Add prediction points
    for _, row in realtime_results.iterrows():
        ax1.scatter(row['checkpoint_minutes'], row['probe_temp'], 
                   s=100, c='red', marker='o', zorder=5)
        ax1.annotate(f"{row['predicted_minutes']:.0f}m", 
                    (row['checkpoint_minutes'], row['probe_temp']),
                    xytext=(5, 5), textcoords='offset points', fontsize=8)
    
    ax1.set_xlabel('Time (minutes)')
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title('Temperature Curves with XGBoost Predictions')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Prediction Error Over Time
    ax2 = axes[0, 1]
    valid_results = realtime_results.dropna(subset=['error'])
    ax2.plot(valid_results['checkpoint_minutes'], valid_results['error'], 
             'go-', linewidth=2, markersize=8)
    ax2.set_xlabel('Time (minutes)')
    ax2.set_ylabel('Prediction Error (minutes)')
    ax2.set_title('XGBoost Prediction Error Throughout Cook')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Feature Importance
    ax3 = axes[1, 0]
    if feature_importance is not None:
        top_features = feature_importance.head(10)
        ax3.barh(range(len(top_features)), top_features['importance'])
        ax3.set_yticks(range(len(top_features)))
        ax3.set_yticklabels(top_features['feature'])
        ax3.set_xlabel('Importance Score')
        ax3.set_title('Top 10 Feature Importance')
    
    # Plot 4: Predicted vs Actual
    ax4 = axes[1, 1]
    ax4.scatter(realtime_results['actual_minutes'], 
                realtime_results['predicted_minutes'], s=100)
    
    # Add perfect prediction line
    min_val = min(realtime_results['actual_minutes'].min(), 
                  realtime_results['predicted_minutes'].min())
    max_val = max(realtime_results['actual_minutes'].max(), 
                  realtime_results['predicted_minutes'].max())
    ax4.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.5)
    
    ax4.set_xlabel('Actual Minutes to Target')
    ax4.set_ylabel('Predicted Minutes to Target')
    ax4.set_title('XGBoost: Predicted vs Actual Time to Target')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('xgboost_performance.png', dpi=150)
    print("\nSaved performance visualization to xgboost_performance.png")
    
    # Compare with simple linear prediction
    print("\n=== Comparison with Simple Linear Prediction ===")
    
    # Calculate simple linear predictions
    simple_predictions = []
    for i in range(len(df)):
        if df.iloc[i]['temperature'] >= 165:
            simple_predictions.append(0)
        else:
            # Simple linear: assume constant rate based on last 5 minutes
            if i >= 5:
                recent_rate = (df.iloc[i]['temperature'] - df.iloc[i-5]['temperature']) / 5
                if recent_rate > 0:
                    simple_pred = (165 - df.iloc[i]['temperature']) / recent_rate
                else:
                    simple_pred = np.inf
            else:
                simple_pred = np.inf
            simple_predictions.append(simple_pred)
    
    # Calculate errors for checkpoints
    for _, row in realtime_results.iterrows():
        checkpoint_idx = (df['minutes'] - row['checkpoint_minutes']).abs().argmin()
        simple_pred = simple_predictions[checkpoint_idx]
        if simple_pred != np.inf and not np.isnan(row['actual_minutes']):
            simple_error = abs(simple_pred - row['actual_minutes'])
            print(f"At {row['checkpoint_minutes']} min: XGBoost error: {row['error']:.1f} min, "
                  f"Simple linear error: {simple_error:.1f} min")

if __name__ == "__main__":
    main()