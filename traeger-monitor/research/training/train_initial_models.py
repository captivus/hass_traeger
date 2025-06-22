#!/usr/bin/env python3
"""Train initial models from historical cook data for better early predictions."""
import sqlite3
import json
import pickle
from datetime import datetime
from pathlib import Path
import logging
import numpy as np
import xgboost as xgb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Historical cook IDs from analysis
HISTORICAL_COOKS = [
    ('E8EB1B4C15021750610370', 2.2, 95.8),  # 2.2 hrs, 95.8% probe coverage
    ('E8EB1B4C15021749139580', 1.6, 100.0),  # 1.6 hrs, 100% probe coverage  
    ('E8EB1B4C15021748715282', 2.2, 98.1),  # 2.2 hrs, 98.1% probe coverage (most comprehensive)
    ('E8EB1B4C15021748620109', 1.6, 88.4),  # 1.6 hrs, 88.4% probe coverage
    ('E8EB1B4C15021748231230', 4.5, 100.0),  # 4.5 hrs, 100% probe coverage (longest)
]

# DB paths
HISTORICAL_DB = Path(__file__).parent.parent / "traeger-stream" / "data" / "traeger_data.db"
MODEL_DIR = Path(__file__).parent / "models"

def extract_cook_data(cook_id: str):
    """Extract all probe data from a historical cook."""
    logger.info(f"Extracting data for cook {cook_id}")
    
    with sqlite3.connect(HISTORICAL_DB) as conn:
        rows = conn.execute("""
            SELECT timestamp, payload FROM raw_messages 
            WHERE payload LIKE ? ORDER BY timestamp
        """, (f'%"cook_id":"{cook_id}"%',))
        
        # Organize by probe channel
        probe_data = {}
        
        for timestamp, payload in rows:
            try:
                data = json.loads(payload)
                status = data.get('status', {})
                
                if status.get('cook_id') != cook_id:
                    continue
                
                t = datetime.fromisoformat(timestamp.replace(' ', 'T'))
                grill_temp = status.get('grill', 0)
                
                # Check legacy probe
                if status.get('probe_con') == 1 and status.get('probe'):
                    temp = status.get('probe')
                    target = status.get('probe_set')
                    if temp and target and target > 0:
                        if 'legacy' not in probe_data:
                            probe_data['legacy'] = {'times': [], 'temps': [], 'targets': [], 'grill_temps': []}
                        probe_data['legacy']['times'].append(t)
                        probe_data['legacy']['temps'].append(temp)
                        probe_data['legacy']['targets'].append(target)
                        probe_data['legacy']['grill_temps'].append(grill_temp)
                
                # Check acc array probes
                for acc in status.get('acc', []):
                    if acc.get('con') != 1:
                        continue
                    
                    channel = acc.get('channel', 'unknown')
                    
                    if acc['type'] == 'probe':
                        temp = acc.get('probe', {}).get('get_temp')
                        target = acc.get('probe', {}).get('set_temp')
                    elif acc['type'] == 'btprobe':
                        temp = acc.get('btprobe', {}).get('get_temp')
                        target = acc.get('btprobe', {}).get('set_temp')
                    else:
                        continue
                    
                    if temp and target and target > 0:
                        if channel not in probe_data:
                            probe_data[channel] = {'times': [], 'temps': [], 'targets': [], 'grill_temps': []}
                        probe_data[channel]['times'].append(t)
                        probe_data[channel]['temps'].append(temp)
                        probe_data[channel]['targets'].append(target)
                        probe_data[channel]['grill_temps'].append(grill_temp)
            
            except json.JSONDecodeError:
                continue
    
    return probe_data

def extract_features_for_training(times, temps, targets, grill_temps):
    """Extract features and labels for training."""
    if len(temps) < 10:
        return [], []
    
    features = []
    labels = []
    start_time = times[0]
    
    # Generate training samples at various points in the cook
    for i in range(5, len(temps) - 1):
        # Basic features
        minutes_elapsed = (times[i] - start_time).total_seconds() / 60
        probe_temp = temps[i]
        temp_to_target = targets[i] - probe_temp
        grill_temp = grill_temps[i]
        
        # Skip if already at target
        if temp_to_target <= 0:
            continue
        
        # Calculate rates
        rate_1 = temps[i] - temps[i-1] if i > 0 else 0
        rate_5 = np.mean([temps[j] - temps[j-1] for j in range(max(1, i-4), i+1)])
        rate_10 = np.mean([temps[j] - temps[j-1] for j in range(max(1, i-9), i+1)])
        
        # Temperature variance (stall detection)
        recent_5 = temps[max(0, i-4):i+1]
        temp_variance = np.var(recent_5)
        
        # Grill relationship
        grill_to_probe = grill_temp - probe_temp
        
        # Progress
        start_temp = temps[0]
        progress_ratio = (probe_temp - start_temp) / (targets[i] - start_temp) if targets[i] > start_temp else 0
        
        # Find actual time to target
        time_to_target = None
        for j in range(i + 1, len(temps)):
            if temps[j] >= targets[i]:
                time_to_target = (times[j] - times[i]).total_seconds() / 60
                break
        
        # Only use samples where we reached target
        if time_to_target is not None and 0 < time_to_target < 300:
            features.append([
                probe_temp,
                minutes_elapsed,
                temp_to_target,
                grill_temp,
                grill_to_probe,
                rate_1,
                rate_5,
                rate_10,
                temp_variance,
                progress_ratio
            ])
            labels.append(time_to_target)
    
    return features, labels

def train_global_model(all_features, all_labels, probe_type):
    """Train a global model on all data for a probe type."""
    if not all_features:
        logger.warning(f"No training data for {probe_type}")
        return None
    
    X = np.array(all_features)
    y = np.array(all_labels)
    
    logger.info(f"Training {probe_type} model with {len(X)} samples")
    
    # Train XGBoost model
    model = xgb.XGBRegressor(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        random_state=42
    )
    
    model.fit(X, y)
    
    # Calculate training performance
    predictions = model.predict(X)
    mae = np.mean(np.abs(predictions - y))
    rmse = np.sqrt(np.mean((predictions - y) ** 2))
    
    logger.info(f"{probe_type} model - MAE: {mae:.1f} min, RMSE: {rmse:.1f} min")
    
    return model

def main():
    """Train and save models from historical data."""
    MODEL_DIR.mkdir(exist_ok=True)
    
    # Collect all training data by probe type
    probe_type_data = {
        'wired': {'features': [], 'labels': []},
        'bluetooth': {'features': [], 'labels': []},
        'legacy': {'features': [], 'labels': []}
    }
    
    for cook_id, hours, coverage in HISTORICAL_COOKS:
        logger.info(f"\nProcessing {cook_id} ({hours} hrs, {coverage}% coverage)")
        
        probe_data = extract_cook_data(cook_id)
        
        for channel, data in probe_data.items():
            features, labels = extract_features_for_training(
                data['times'], data['temps'], data['targets'], data['grill_temps']
            )
            
            if not features:
                continue
            
            # Categorize by probe type
            if channel == 'legacy':
                probe_type = 'legacy'
            elif channel.startswith('BT'):
                probe_type = 'bluetooth'
            else:
                probe_type = 'wired'
            
            probe_type_data[probe_type]['features'].extend(features)
            probe_type_data[probe_type]['labels'].extend(labels)
            
            logger.info(f"  {channel} ({probe_type}): {len(features)} training samples")
    
    # Train and save models
    models = {}
    for probe_type, data in probe_type_data.items():
        if data['features']:
            model = train_global_model(data['features'], data['labels'], probe_type)
            if model:
                models[probe_type] = model
                
                # Save model
                model_path = MODEL_DIR / f"{probe_type}_model.pkl"
                with open(model_path, 'wb') as f:
                    pickle.dump(model, f)
                logger.info(f"Saved {probe_type} model to {model_path}")
    
    # Save model metadata
    metadata = {
        'created': datetime.now().isoformat(),
        'probe_types': list(models.keys()),
        'training_cooks': [c[0] for c in HISTORICAL_COOKS],
        'total_hours': sum(c[1] for c in HISTORICAL_COOKS),
        'feature_names': [
            'probe_temp', 'minutes_elapsed', 'temp_to_target', 'grill_temp',
            'grill_to_probe', 'rate_1', 'rate_5', 'rate_10', 
            'temp_variance', 'progress_ratio'
        ]
    }
    
    with open(MODEL_DIR / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"\nTraining complete! Models saved to {MODEL_DIR}")
    logger.info(f"Trained models for: {', '.join(models.keys())}")

if __name__ == "__main__":
    main()