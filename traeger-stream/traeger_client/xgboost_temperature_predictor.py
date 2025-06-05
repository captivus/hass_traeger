"""XGBoost-based temperature predictor that trains on current cook data."""

from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
import logging
from collections import defaultdict

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available. Temperature predictions will not be available until 20 data points are collected.")

from .storage import DataStorage

logger = logging.getLogger(__name__)


class XGBoostTemperaturePredictor:
    """Predicts time to reach target temperature using XGBoost trained on current cook."""
    
    def __init__(self, storage: Optional[DataStorage] = None):
        """Initialize the XGBoost temperature predictor.
        
        Args:
            storage: Optional storage instance for persisting ML data
        """
        self.storage = storage
        self.models = {}  # (cook_id, probe_id) -> model
        self.cook_start_times = {}  # (cook_id, probe_id) -> datetime
        self.last_cook_ids = {}  # grill_id -> last_cook_id
        self.min_training_points = 20
        self.retrain_interval = 10
        self.model_version = "1.0"
        
        if not XGBOOST_AVAILABLE:
            logger.error("XGBoost not available. Install with: pip install xgboost")
    
    def add_reading(self, grill_id: str, cook_id: str, probe_id: str, 
                   probe_temp: float, probe_target: float,
                   grill_temp: float, grill_set: float, 
                   ambient_temp: float) -> None:
        """Add a temperature reading and potentially train/retrain model.
        
        Args:
            grill_id: Grill identifier
            cook_id: Current cook session ID
            probe_id: Probe identifier
            probe_temp: Current probe temperature
            probe_target: Target probe temperature
            grill_temp: Current grill temperature
            grill_set: Grill set temperature
            ambient_temp: Ambient temperature
        """
        # Check for new cook session
        if self._is_new_cook(grill_id, cook_id, probe_id):
            self._reset_cook_session(grill_id, cook_id, probe_id)
        
        # Get cook start time
        key = (cook_id, probe_id)
        if key not in self.cook_start_times:
            self.cook_start_times[key] = datetime.now(timezone.utc)
        
        # Calculate features
        minutes_elapsed = (datetime.now(timezone.utc) - self.cook_start_times[key]).total_seconds() / 60
        
        # Prepare data point
        data_point = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'grill_id': grill_id,
            'cook_id': cook_id,
            'probe_id': probe_id,
            'probe_temp': probe_temp,
            'probe_target': probe_target,
            'grill_temp': grill_temp,
            'grill_set': grill_set,
            'ambient_temp': ambient_temp,
            'minutes_elapsed': minutes_elapsed,
            'grill_probe_diff': grill_temp - probe_temp,
            'probe_target_diff': probe_target - probe_temp,
            'probe_rate': 0  # Will be calculated from historical data
        }
        
        # Save to database if storage available
        if self.storage:
            import asyncio
            try:
                # Try to get the current event loop
                loop = asyncio.get_running_loop()
                # Schedule the coroutine to run
                asyncio.create_task(self.storage.save_ml_data_point(data_point))
            except RuntimeError:
                # Not in async context, save synchronously
                self.storage._save_ml_data_point_sync(data_point)
        
        # Check if target reached for ground truth update
        if probe_temp >= probe_target:
            self._update_ground_truth(cook_id, probe_id)
    
    def predict_time_to_target(self, grill_id: str, cook_id: str, probe_id: str,
                             current_temp: float, target_temp: float,
                             grill_temp: float, grill_set: float,
                             ambient_temp: float) -> Tuple[Optional[float], Optional[str], Optional[float], Optional[float]]:
        """Predict time to reach target temperature.
        
        Returns:
            Tuple of (minutes_to_target, message, rate, acceleration)
        """
        if not XGBOOST_AVAILABLE:
            return None, "XGBoost not installed", None, None
        
        # Add current reading
        self.add_reading(grill_id, cook_id, probe_id, current_temp, target_temp,
                        grill_temp, grill_set, ambient_temp)
        
        # Already at target
        if current_temp >= target_temp:
            return 0, None, None, None
        
        # Get training data from database
        if not self.storage:
            return None, "Storage not available", None, None
        
        # Get data for current cook
        try:
            import asyncio
            try:
                # Try async first
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context but can't await
                    # Use sync method instead
                    ml_data = self.storage._get_ml_data_for_cook_sync(cook_id, probe_id)
                else:
                    # Run async method
                    ml_data = loop.run_until_complete(
                        self.storage.get_ml_data_for_cook(cook_id, probe_id)
                    )
            except RuntimeError:
                # No event loop, use sync
                ml_data = self.storage._get_ml_data_for_cook_sync(cook_id, probe_id)
        except Exception as e:
            logger.error(f"Failed to get ML data: {e}")
            return None, "Failed to load data", None, None
        
        if len(ml_data) < self.min_training_points:
            return None, f"Collecting data... ({len(ml_data)}/{self.min_training_points} points)", None, None
        
        # Check if we need to train/retrain
        key = (cook_id, probe_id)
        needs_training = (
            key not in self.models or 
            len(ml_data) % self.retrain_interval == 0
        )
        
        if needs_training:
            success = self._train_model(cook_id, probe_id, ml_data)
            if not success:
                return None, "Model training failed", None, None
        
        # Calculate features for prediction
        features = self._calculate_features(ml_data, current_temp, grill_temp, 
                                          grill_set, ambient_temp, target_temp)
        
        # Make prediction
        try:
            model = self.models[key]
            X = pd.DataFrame([features])
            prediction = model.predict(X)[0]
            
            # Calculate rate (last 5 points)
            recent_data = ml_data[-5:]
            if len(recent_data) >= 2:
                time_diff = (pd.Timestamp(recent_data[-1]['timestamp']) - 
                           pd.Timestamp(recent_data[0]['timestamp'])).total_seconds() / 60
                temp_diff = recent_data[-1]['probe_temp'] - recent_data[0]['probe_temp']
                rate = temp_diff / time_diff if time_diff > 0 else 0
            else:
                rate = 0
            
            # Save prediction
            if self.storage:
                prediction_data = features.copy()
                prediction_data.update({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'grill_id': grill_id,
                    'cook_id': cook_id,
                    'probe_id': probe_id,
                    'probe_temp': current_temp,
                    'probe_target': target_temp,
                    'predicted_minutes': prediction,
                    'prediction_timestamp': datetime.now(timezone.utc).isoformat(),
                    'model_version': self.model_version
                })
                try:
                    import asyncio
                    asyncio.create_task(self.storage.save_ml_data_point(prediction_data))
                except RuntimeError:
                    self.storage._save_ml_data_point_sync(prediction_data)
            
            return prediction, None, rate, 0  # No acceleration for now
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return None, "Prediction error", None, None
    
    def _is_new_cook(self, grill_id: str, cook_id: str, probe_id: str) -> bool:
        """Check if this is a new cook session."""
        # New cook if cook_id changed
        if grill_id in self.last_cook_ids:
            if self.last_cook_ids[grill_id] != cook_id:
                return True
        
        # Or if we haven't seen this cook/probe combination
        return (cook_id, probe_id) not in self.cook_start_times
    
    def _reset_cook_session(self, grill_id: str, cook_id: str, probe_id: str) -> None:
        """Reset for a new cook session."""
        logger.info(f"New cook session detected: {cook_id} for grill {grill_id}, probe {probe_id}")
        
        # Remove old model if exists
        old_key = None
        if grill_id in self.last_cook_ids:
            old_cook_id = self.last_cook_ids[grill_id]
            old_key = (old_cook_id, probe_id)
            if old_key in self.models:
                del self.models[old_key]
                logger.info(f"Removed model for previous cook: {old_cook_id}")
        
        # Update tracking
        self.last_cook_ids[grill_id] = cook_id
        self.cook_start_times[(cook_id, probe_id)] = datetime.now(timezone.utc)
    
    def _train_model(self, cook_id: str, probe_id: str, ml_data: List[Dict]) -> bool:
        """Train XGBoost model on cook data."""
        try:
            # Prepare training data
            X = []
            y = []
            
            for i in range(len(ml_data)):
                if ml_data[i]['probe_temp'] >= ml_data[i]['probe_target']:
                    continue
                
                # Find when target was reached
                target_time = None
                for j in range(i + 1, len(ml_data)):
                    if ml_data[j]['probe_temp'] >= ml_data[j]['probe_target']:
                        target_time = (pd.Timestamp(ml_data[j]['timestamp']) - 
                                     pd.Timestamp(ml_data[i]['timestamp'])).total_seconds() / 60
                        break
                
                if target_time is not None:
                    features = self._extract_features_from_data(ml_data, i)
                    X.append(features)
                    y.append(target_time)
            
            if len(X) < 10:
                logger.warning(f"Not enough training data: {len(X)} samples")
                return False
            
            # Train model
            X_df = pd.DataFrame(X)
            model = xgb.XGBRegressor(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.1,
                objective='reg:squarederror',
                random_state=42
            )
            model.fit(X_df, y)
            
            self.models[(cook_id, probe_id)] = model
            logger.info(f"Trained model for {cook_id}/{probe_id} with {len(X)} samples")
            
            return True
            
        except Exception as e:
            logger.error(f"Model training failed: {e}")
            return False
    
    def _calculate_features(self, ml_data: List[Dict], current_temp: float,
                          grill_temp: float, grill_set: float, 
                          ambient_temp: float, target_temp: float) -> Dict[str, float]:
        """Calculate features for prediction."""
        features = {
            'probe_temp': current_temp,
            'grill_temp': grill_temp,
            'grill_set': grill_set,
            'ambient_temp': ambient_temp,
            'grill_probe_diff': grill_temp - current_temp,
            'probe_target_diff': target_temp - current_temp,
            'minutes_elapsed': ml_data[-1]['minutes_elapsed'] if ml_data else 0
        }
        
        # Add rolling features
        if len(ml_data) >= 5:
            recent_temps = [d['probe_temp'] for d in ml_data[-5:]]
            features['probe_temp_mean_5'] = np.mean(recent_temps)
            features['probe_temp_std_5'] = np.std(recent_temps)
            features['probe_temp_change_5'] = current_temp - ml_data[-5]['probe_temp']
        else:
            features['probe_temp_mean_5'] = current_temp
            features['probe_temp_std_5'] = 0
            features['probe_temp_change_5'] = 0
        
        # Binary features
        features['high_grill_temp'] = int(grill_set > 300)
        features['large_temp_diff'] = int(features['grill_probe_diff'] > 100)
        
        return features
    
    def _extract_features_from_data(self, ml_data: List[Dict], index: int) -> Dict[str, float]:
        """Extract features from historical data point."""
        point = ml_data[index]
        features = {
            'probe_temp': point['probe_temp'],
            'grill_temp': point['grill_temp'],
            'grill_set': point['grill_set'],
            'ambient_temp': point['ambient_temp'],
            'grill_probe_diff': point['grill_probe_diff'],
            'probe_target_diff': point['probe_target_diff'],
            'minutes_elapsed': point['minutes_elapsed']
        }
        
        # Rolling features
        if index >= 5:
            recent_temps = [ml_data[i]['probe_temp'] for i in range(index-4, index+1)]
            features['probe_temp_mean_5'] = np.mean(recent_temps)
            features['probe_temp_std_5'] = np.std(recent_temps)
            features['probe_temp_change_5'] = point['probe_temp'] - ml_data[index-5]['probe_temp']
        else:
            features['probe_temp_mean_5'] = point['probe_temp']
            features['probe_temp_std_5'] = 0
            features['probe_temp_change_5'] = 0
        
        # Binary features
        features['high_grill_temp'] = int(point['grill_set'] > 300)
        features['large_temp_diff'] = int(point['grill_probe_diff'] > 100)
        
        return features
    
    def _update_ground_truth(self, cook_id: str, probe_id: str) -> None:
        """Update ground truth when target is reached."""
        if not self.storage:
            return
        
        try:
            # Get all data points for this cook
            ml_data = self.storage._get_ml_data_for_cook_sync(cook_id, probe_id)
            
            if not ml_data:
                return
            
            # Find when target was first reached
            target_reached_time = None
            for point in ml_data:
                if point['probe_temp'] >= point['probe_target']:
                    target_reached_time = point['timestamp']
                    break
            
            if target_reached_time:
                # Update all predictions with actual time
                import asyncio
                try:
                    asyncio.create_task(
                        self.storage.update_ml_ground_truth(
                            cook_id, probe_id, 0, target_reached_time
                        )
                    )
                except RuntimeError:
                    self.storage._update_ml_ground_truth_sync(
                        cook_id, probe_id, 0, target_reached_time
                    )
                
                logger.info(f"Updated ground truth for {cook_id}/{probe_id}")
                
        except Exception as e:
            logger.error(f"Failed to update ground truth: {e}")
    
    def clear_history(self):
        """Clear all models and history for new grill selection."""
        self.models.clear()
        self.cook_start_times.clear()
        self.last_cook_ids.clear()
        logger.info("Cleared XGBoost predictor history")
    
    def format_prediction(self, prediction: Tuple[Optional[float], Optional[str], 
                                                 Optional[float], Optional[float]]) -> str:
        """Format prediction for display.
        
        Args:
            prediction: Tuple of (minutes, message, rate, acceleration)
            
        Returns:
            Formatted string for display
        """
        minutes, message, rate, acceleration = prediction
        
        if minutes is None:
            return message or "Cannot predict"
        
        if message:  # Should not happen when minutes is not None
            return message
        
        if minutes < 1:
            return "Less than 1 minute"
        elif minutes > 180:  # More than 3 hours
            return "More than 3 hours"
        elif minutes < 60:
            return f"~{int(minutes)} minutes"
        else:
            hours = minutes / 60
            return f"~{hours:.1f} hours"