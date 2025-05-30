#!/usr/bin/env python3
"""Proper XGBoost evaluation with no data leakage - time series split."""

import pandas as pd
import numpy as np
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
    features = pd.DataFrame()
    features['probe_temp'] = df['temperature']
    features['grill_temp'] = df['grill_temp']
    features['grill_set'] = df['grill_set']
    features['ambient_temp'] = df['ambient']
    
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
    
    return np.array(targets)

def time_series_cv_evaluation(features, targets, n_splits=5):
    """Proper time series cross-validation with no look-ahead bias."""
    results = []
    
    # Remove NaN targets
    valid_mask = ~np.isnan(targets)
    features_valid = features[valid_mask]
    targets_valid = targets[valid_mask]
    n_samples = len(features_valid)
    
    # Time series split - always train on past, test on future
    min_train_size = int(n_samples * 0.2)  # At least 20% for training
    test_size = int(n_samples * 0.1)      # 10% for each test fold
    
    for split in range(n_splits):
        # Calculate split points
        train_end = min_train_size + (split * test_size)
        test_end = min(train_end + test_size, n_samples)
        
        if train_end >= n_samples - test_size:
            break
            
        # Split data
        X_train = features_valid.iloc[:train_end]
        y_train = targets_valid[:train_end]
        X_test = features_valid.iloc[train_end:test_end]
        y_test = targets_valid[train_end:test_end]
        
        # Train model
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        # Predict
        predictions = model.predict(X_test)
        
        # Calculate metrics
        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        
        results.append({
            'split': split + 1,
            'train_size': len(X_train),
            'test_size': len(X_test),
            'mae': mae,
            'rmse': rmse,
            'train_minutes': X_train['minutes_elapsed'].max(),
            'test_minutes_start': X_test['minutes_elapsed'].min(),
            'test_minutes_end': X_test['minutes_elapsed'].max()
        })
        
        print(f"Split {split + 1}: Train on 0-{X_train['minutes_elapsed'].max():.1f} min, "
              f"Test on {X_test['minutes_elapsed'].min():.1f}-{X_test['minutes_elapsed'].max():.1f} min, "
              f"MAE: {mae:.1f} min")
    
    return pd.DataFrame(results)

def simulate_realistic_prediction(df, features, targets):
    """Simulate what would happen in real-time - NO future data used."""
    predictions_log = []
    
    # Start predictions after 20 minutes (need some data)
    for current_minute in range(20, 60, 5):  # Every 5 minutes from 20 to 60
        # Find current index
        current_idx = (df['minutes'] - current_minute).abs().argmin()
        
        # Only use data up to current point
        train_features = features.iloc[:current_idx]
        train_targets = targets[:current_idx]
        
        # Remove NaN
        valid_mask = ~np.isnan(train_targets)
        if sum(valid_mask) < 10:
            continue
            
        X_train = train_features[valid_mask]
        y_train = train_targets[valid_mask]
        
        # Train model on historical data only
        model = xgb.XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            objective='reg:squarederror',
            random_state=42
        )
        model.fit(X_train, y_train)
        
        # Predict for current moment
        current_features = features.iloc[current_idx:current_idx+1]
        prediction = model.predict(current_features)[0]
        actual = targets[current_idx]
        
        predictions_log.append({
            'time': current_minute,
            'temp': df.iloc[current_idx]['temperature'],
            'grill_set': df.iloc[current_idx]['grill_set'],
            'prediction': prediction,
            'actual': actual,
            'error': abs(prediction - actual) if not np.isnan(actual) else np.nan
        })
    
    return pd.DataFrame(predictions_log)

def main():
    # Load data
    df = pd.read_csv('analyzed_165_cook.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print("=== PROPER XGBoost Evaluation - No Data Leakage ===\n")
    
    # Prepare features and targets
    features = prepare_features(df)
    targets = create_targets(df)
    
    # Time series cross-validation
    print("1. Time Series Cross-Validation (Train on Past, Test on Future):")
    print("-" * 70)
    cv_results = time_series_cv_evaluation(features, targets, n_splits=5)
    
    print(f"\nAverage MAE across all splits: {cv_results['mae'].mean():.2f} minutes")
    print(f"Std deviation: {cv_results['mae'].std():.2f} minutes")
    
    # Realistic simulation
    print("\n2. Realistic Real-Time Simulation (No Future Data):")
    print("-" * 70)
    realistic_predictions = simulate_realistic_prediction(df, features, targets)
    print(realistic_predictions)
    
    print(f"\nRealistic Average Error: {realistic_predictions['error'].mean():.2f} minutes")
    
    # Visualize results
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Plot 1: Cross-validation results
    ax1 = axes[0, 0]
    ax1.bar(cv_results['split'], cv_results['mae'])
    ax1.set_xlabel('CV Split')
    ax1.set_ylabel('Mean Absolute Error (minutes)')
    ax1.set_title('Time Series CV: MAE by Split (No Data Leakage)')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Realistic predictions
    ax2 = axes[0, 1]
    ax2.plot(realistic_predictions['time'], realistic_predictions['prediction'], 
             'go-', label='Predicted', markersize=8)
    ax2.plot(realistic_predictions['time'], realistic_predictions['actual'], 
             'ro-', label='Actual', markersize=8)
    ax2.set_xlabel('Time (minutes)')
    ax2.set_ylabel('Minutes to Target')
    ax2.set_title('Realistic Predictions vs Actual (No Future Data)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Error over time
    ax3 = axes[1, 0]
    ax3.plot(realistic_predictions['time'], realistic_predictions['error'], 
             'bo-', markersize=8)
    ax3.set_xlabel('Time (minutes)')
    ax3.set_ylabel('Prediction Error (minutes)')
    ax3.set_title('Prediction Error Over Time')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Feature importance from final model
    ax4 = axes[1, 1]
    # Train final model on all data for feature importance
    valid_mask = ~np.isnan(targets)
    final_model = xgb.XGBRegressor(n_estimators=100, max_depth=4, random_state=42)
    final_model.fit(features[valid_mask], targets[valid_mask])
    
    importance_df = pd.DataFrame({
        'feature': features.columns,
        'importance': final_model.feature_importances_
    }).sort_values('importance', ascending=False).head(10)
    
    ax4.barh(range(len(importance_df)), importance_df['importance'])
    ax4.set_yticks(range(len(importance_df)))
    ax4.set_yticklabels(importance_df['feature'])
    ax4.set_xlabel('Importance Score')
    ax4.set_title('Top 10 Feature Importance')
    
    plt.tight_layout()
    plt.savefig('xgboost_proper_evaluation.png', dpi=150)
    print("\nSaved proper evaluation to xgboost_proper_evaluation.png")
    
    # Compare with simple baseline
    print("\n3. Comparison with Simple Baseline:")
    print("-" * 70)
    
    # Simple baseline: linear extrapolation
    baseline_errors = []
    for _, row in realistic_predictions.iterrows():
        idx = (df['minutes'] - row['time']).abs().argmin()
        if idx >= 5:
            rate = (df.iloc[idx]['temperature'] - df.iloc[idx-5]['temperature']) / 5
            if rate > 0:
                simple_pred = (165 - df.iloc[idx]['temperature']) / rate
                baseline_errors.append(abs(simple_pred - row['actual']))
    
    if baseline_errors:
        print(f"Simple Linear Baseline MAE: {np.mean(baseline_errors):.2f} minutes")
        print(f"XGBoost MAE: {realistic_predictions['error'].mean():.2f} minutes")
        print(f"Improvement: {(1 - realistic_predictions['error'].mean() / np.mean(baseline_errors)) * 100:.1f}%")

if __name__ == "__main__":
    main()