#!/usr/bin/env python3
"""Validate that simple features work well for temperature prediction."""

import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import matplotlib.pyplot as plt
import seaborn as sns

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    print("XGBoost not available. Install with: pip install xgboost")
    exit(1)

# Use the existing database with historical cook data
DB_PATH = Path("../traeger-stream/data/traeger_data.db")  # Path to historical data

def load_historical_cooks(min_duration_hours=2):
    """Load all historical cook sessions from database."""
    with sqlite3.connect(DB_PATH) as conn:
        # Find all unique cook IDs with sufficient data
        cursor = conn.execute("""
            SELECT 
                json_extract(payload, '$.status.cook_id') as cook_id,
                COUNT(*) as message_count,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time
            FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') != ''
            GROUP BY cook_id
            HAVING message_count > 100
        """)
        
        cooks = []
        for row in cursor:
            cook_id, count, start, end = row
            duration = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
            if duration >= min_duration_hours:
                cooks.append({
                    'cook_id': cook_id,
                    'message_count': count,
                    'duration_hours': duration,
                    'start': start,
                    'end': end
                })
        
        print(f"Found {len(cooks)} cook sessions with > {min_duration_hours} hours duration")
        return cooks

def extract_cook_data(cook_id: str):
    """Extract all temperature data for a specific cook."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT timestamp, payload 
            FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') = ?
            ORDER BY timestamp ASC
        """, (cook_id,))
        
        data = []
        for row in cursor:
            timestamp, payload = row
            status = json.loads(payload).get('status', {})
            
            # Extract all temperatures
            record = {
                'timestamp': datetime.fromisoformat(timestamp),
                'grill_temp': status.get('grill'),
                'grill_set': status.get('set'),
                'ambient': status.get('ambient', 70)
            }
            
            # Extract probe temperatures from acc array
            for acc in status.get('acc', []):
                if acc.get('type') == 'probe' and acc.get('con') == 1:
                    probe_data = acc.get('probe', {})
                    channel = acc.get('channel', 'p0')
                    record[f'{channel}_temp'] = probe_data.get('get_temp')
                    record[f'{channel}_target'] = probe_data.get('set_temp')
                elif acc.get('type') == 'btprobe' and acc.get('con') == 1:
                    probe_data = acc.get('btprobe', {})
                    channel = acc.get('channel', 'bt')
                    record[f'{channel}_temp'] = probe_data.get('get_temp')
                    record[f'{channel}_target'] = probe_data.get('set_temp')
            
            # Also check legacy probe format
            if status.get('probe_con') == 1:
                record['legacy_probe_temp'] = status.get('probe')
                record['legacy_probe_target'] = status.get('probe_set')
                
            data.append(record)
            
    return pd.DataFrame(data)

def prepare_features_and_target(df: pd.DataFrame, probe_col: str, target_col: str):
    """Prepare ML features and target variable with NO data leakage."""
    
    # Sort by timestamp
    df = df.sort_values('timestamp').copy()
    
    # Calculate elapsed time
    df['minutes_elapsed'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
    
    # Current state features (no future information)
    df['probe_temp'] = df[probe_col]
    df['probe_target'] = df[target_col]
    df['probe_to_target'] = df['probe_target'] - df['probe_temp']
    df['grill_to_probe'] = df['grill_temp'] - df['probe_temp']
    df['grill_to_set'] = df['grill_set'] - df['grill_temp']
    
    # Historical features (only using past data)
    # Use shift(1) to ensure we only use previous values
    df['probe_rate'] = (df['probe_temp'] - df['probe_temp'].shift(1)) / (df['minutes_elapsed'] - df['minutes_elapsed'].shift(1))
    df['grill_rate'] = (df['grill_temp'] - df['grill_temp'].shift(1)) / (df['minutes_elapsed'] - df['minutes_elapsed'].shift(1))
    
    # Rolling features - using only past data
    window = 5
    df['probe_rate_avg'] = df['probe_rate'].rolling(window, min_periods=1).mean()
    df['probe_rate_std'] = df['probe_rate'].rolling(window, min_periods=1).std()
    df['grill_rate_avg'] = df['grill_rate'].rolling(window, min_periods=1).mean()
    
    # Acceleration (second derivative)
    df['probe_accel'] = (df['probe_rate'] - df['probe_rate'].shift(1)) / (df['minutes_elapsed'] - df['minutes_elapsed'].shift(1))
    
    # Target: Time to reach target temperature
    # This is the tricky part - we need to calculate this WITHOUT using future temperature data
    target_times = []
    for i in range(len(df)):
        current_temp = df.iloc[i]['probe_temp']
        target_temp = df.iloc[i]['probe_target']
        
        if current_temp >= target_temp:
            target_times.append(0)  # Already at target
        else:
            # Find when target is reached in the future
            future_data = df.iloc[i+1:]
            reached = future_data[future_data['probe_temp'] >= target_temp]
            
            if len(reached) > 0:
                time_to_target = reached.iloc[0]['minutes_elapsed'] - df.iloc[i]['minutes_elapsed']
                target_times.append(time_to_target)
            else:
                target_times.append(np.nan)  # Never reached target
    
    df['time_to_target'] = target_times
    
    # Feature columns
    feature_cols = [
        'probe_temp', 'probe_to_target', 'grill_temp', 'grill_to_probe',
        'grill_to_set', 'ambient', 'minutes_elapsed', 'probe_rate_avg',
        'probe_rate_std', 'grill_rate_avg', 'probe_accel'
    ]
    
    # Remove rows with NaN values
    df_clean = df.dropna(subset=feature_cols + ['time_to_target'])
    
    # Only keep reasonable targets (0-180 minutes)
    df_clean = df_clean[(df_clean['time_to_target'] >= 0) & (df_clean['time_to_target'] <= 180)]
    
    return df_clean, feature_cols

def validate_model_no_leakage(df_clean: pd.DataFrame, feature_cols: list):
    """Validate model using proper time series cross-validation."""
    
    X = df_clean[feature_cols].values
    y = df_clean['time_to_target'].values
    
    # Time series split - ensures we only train on past data
    tscv = TimeSeriesSplit(n_splits=5)
    
    # Model parameters
    params = {
        'objective': 'reg:squarederror',
        'max_depth': 4,
        'learning_rate': 0.1,
        'n_estimators': 100,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 3,
        'random_state': 42
    }
    
    model = xgb.XGBRegressor(**params)
    
    # Cross validation scores
    mae_scores = []
    rmse_scores = []
    r2_scores = []
    
    print("\nTime Series Cross-Validation Results:")
    print("-" * 50)
    
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # Train model
        model.fit(X_train, y_train)
        
        # Predict
        y_pred = model.predict(X_test)
        
        # Calculate metrics
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        
        mae_scores.append(mae)
        rmse_scores.append(rmse)
        r2_scores.append(r2)
        
        print(f"Fold {fold + 1}: MAE={mae:.2f} min, RMSE={rmse:.2f} min, R²={r2:.3f}")
    
    print("-" * 50)
    print(f"Average: MAE={np.mean(mae_scores):.2f} ± {np.std(mae_scores):.2f} min")
    print(f"         RMSE={np.mean(rmse_scores):.2f} ± {np.std(rmse_scores):.2f} min")
    print(f"         R²={np.mean(r2_scores):.3f} ± {np.std(r2_scores):.3f}")
    
    return model, mae_scores, rmse_scores, r2_scores

def plot_validation_results(df_clean: pd.DataFrame, model, feature_cols: list):
    """Plot actual vs predicted times for visualization."""
    
    # Use last 20% of data for final visualization
    split_point = int(0.8 * len(df_clean))
    X_train = df_clean[feature_cols].iloc[:split_point].values
    y_train = df_clean['time_to_target'].iloc[:split_point].values
    X_test = df_clean[feature_cols].iloc[split_point:].values
    y_test = df_clean['time_to_target'].iloc[split_point:].values
    
    # Train final model
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    
    # Create plots
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. Actual vs Predicted
    ax = axes[0, 0]
    ax.scatter(y_test, y_pred, alpha=0.5)
    ax.plot([0, 180], [0, 180], 'r--', label='Perfect prediction')
    ax.set_xlabel('Actual Time to Target (min)')
    ax.set_ylabel('Predicted Time to Target (min)')
    ax.set_title('Actual vs Predicted')
    ax.legend()
    
    # 2. Residual plot
    ax = axes[0, 1]
    residuals = y_test - y_pred
    ax.scatter(y_pred, residuals, alpha=0.5)
    ax.axhline(y=0, color='r', linestyle='--')
    ax.set_xlabel('Predicted Time (min)')
    ax.set_ylabel('Residual (min)')
    ax.set_title('Residual Plot')
    
    # 3. Feature importance
    ax = axes[1, 0]
    importance = model.feature_importances_
    indices = np.argsort(importance)[::-1]
    ax.bar(range(len(importance)), importance[indices])
    ax.set_xticks(range(len(importance)))
    ax.set_xticklabels([feature_cols[i] for i in indices], rotation=45)
    ax.set_title('Feature Importance')
    
    # 4. Error distribution
    ax = axes[1, 1]
    ax.hist(residuals, bins=30, edgecolor='black')
    ax.set_xlabel('Prediction Error (min)')
    ax.set_ylabel('Frequency')
    ax.set_title('Error Distribution')
    
    plt.tight_layout()
    plt.savefig('model_validation_results.png')
    print("\nValidation plots saved to model_validation_results.png")

def main():
    """Run complete model validation."""
    print("XGBoost Model Validation for Traeger Temperature Prediction")
    print("=" * 60)
    
    # Load historical cooks
    cooks = load_historical_cooks(min_duration_hours=2)
    
    if len(cooks) < 1:
        print("Error: Need at least 1 cook session for validation")
        return
    
    # Validate on multiple cooks
    all_mae = []
    all_rmse = []
    all_r2 = []
    
    for i, cook in enumerate(cooks[:5]):  # Test on up to 5 cooks
        print(f"\n\nValidating on cook {i+1}/{min(5, len(cooks))}: {cook['cook_id']}")
        print(f"Duration: {cook['duration_hours']:.1f} hours, Messages: {cook['message_count']}")
        
        # Load cook data
        df = extract_cook_data(cook['cook_id'])
        
        # Find which probe columns have data
        probe_cols = [col for col in df.columns if col.endswith('_temp') and not col.startswith('grill')]
        target_cols = [col for col in df.columns if col.endswith('_target')]
        
        for probe_col in probe_cols:
            # Find corresponding target column
            target_col = probe_col.replace('_temp', '_target')
            if target_col not in target_cols:
                continue
                
            # Check if probe has data
            if df[probe_col].notna().sum() < 50:
                continue
                
            print(f"\nValidating probe: {probe_col}")
            
            # Prepare features
            df_clean, feature_cols = prepare_features_and_target(df, probe_col, target_col)
            
            if len(df_clean) < 50:
                print(f"Insufficient data for {probe_col} (only {len(df_clean)} valid points)")
                continue
            
            # Validate model
            model, mae, rmse, r2 = validate_model_no_leakage(df_clean, feature_cols)
            
            all_mae.extend(mae)
            all_rmse.extend(rmse)
            all_r2.extend(r2)
            
            # Plot results for first cook only
            if i == 0:
                plot_validation_results(df_clean, model, feature_cols)
    
    # Overall summary
    print("\n\nOVERALL VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total folds evaluated: {len(all_mae)}")
    print(f"Mean Absolute Error: {np.mean(all_mae):.2f} ± {np.std(all_mae):.2f} minutes")
    print(f"Root Mean Squared Error: {np.mean(all_rmse):.2f} ± {np.std(all_rmse):.2f} minutes")
    print(f"R² Score: {np.mean(all_r2):.3f} ± {np.std(all_r2):.3f}")
    
    # Check for data leakage indicators
    print("\nData Leakage Check:")
    if np.mean(all_r2) > 0.95:
        print("⚠️  WARNING: R² > 0.95 may indicate data leakage!")
    else:
        print("✓ R² values look reasonable (no obvious data leakage)")
    
    if np.mean(all_mae) < 1.0:
        print("⚠️  WARNING: MAE < 1 minute may indicate data leakage!")
    else:
        print("✓ MAE values look reasonable")

if __name__ == "__main__":
    main()