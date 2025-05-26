"""Machine learning model for predicting time to target temperature."""

import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import pandas as pd


class TemperaturePredictor:
    """Predicts time to reach target temperature for Traeger probes."""
    
    def __init__(self, model_path: Optional[Path] = None):
        """Initialize the temperature predictor.
        
        Args:
            model_path: Path to save/load trained models
        """
        self.model_path = model_path or Path("./models")
        self.model_path.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = [
            'current_temp', 'target_temp', 'temp_diff', 
            'grill_temp', 'grill_set_temp', 'ambient_temp',
            'time_elapsed', 'temp_rate', 'temp_rate_avg',
            'grill_temp_diff', 'temp_progress'
        ]
        
        # Try to load existing model
        self.load_model()
        
        # Temperature history for calculating rolling averages
        self.temp_history: Dict[str, List[Tuple[float, float, float]]] = {}
        
    def extract_features(self, 
                        current_temp: float,
                        target_temp: float,
                        grill_temp: float,
                        grill_set_temp: float,
                        ambient_temp: float,
                        probe_id: str,
                        time_elapsed: float = 0) -> np.ndarray:
        """Extract features from current state for prediction.
        
        Returns:
            Feature vector for prediction
        """
        # Update temperature history
        now = datetime.now().timestamp()
        if probe_id not in self.temp_history:
            self.temp_history[probe_id] = []
        
        self.temp_history[probe_id].append((now, current_temp, grill_temp))
        
        # Keep only last 5 minutes of history
        cutoff = now - 300
        self.temp_history[probe_id] = [
            (t, temp, grill) for t, temp, grill in self.temp_history[probe_id] 
            if t > cutoff
        ]
        
        # Calculate temperature rate
        temp_rate = 0
        temp_rate_avg = 0
        if len(self.temp_history[probe_id]) > 1:
            # Recent rate (last 30 seconds)
            recent = [(t, temp) for t, temp, _ in self.temp_history[probe_id] if t > now - 30]
            if len(recent) > 1:
                dt = recent[-1][0] - recent[0][0]
                if dt > 0:
                    temp_rate = (recent[-1][1] - recent[0][1]) / dt * 60  # °F/min
            
            # Average rate over full history
            dt_full = self.temp_history[probe_id][-1][0] - self.temp_history[probe_id][0][0]
            if dt_full > 0:
                temp_rate_avg = (self.temp_history[probe_id][-1][1] - self.temp_history[probe_id][0][1]) / dt_full * 60
        
        # Extract features
        features = {
            'current_temp': current_temp,
            'target_temp': target_temp,
            'temp_diff': target_temp - current_temp,
            'grill_temp': grill_temp,
            'grill_set_temp': grill_set_temp,
            'ambient_temp': ambient_temp,
            'time_elapsed': time_elapsed,
            'temp_rate': temp_rate,
            'temp_rate_avg': temp_rate_avg,
            'grill_temp_diff': grill_set_temp - grill_temp,
            'temp_progress': (current_temp - ambient_temp) / (target_temp - ambient_temp) if target_temp > ambient_temp else 0
        }
        
        return np.array([features[name] for name in self.feature_names]).reshape(1, -1)
    
    def predict(self, 
                current_temp: float,
                target_temp: float,
                grill_temp: float,
                grill_set_temp: float,
                ambient_temp: float,
                probe_id: str = "default") -> Optional[Tuple[float, float]]:
        """Predict time to reach target temperature.
        
        Returns:
            Tuple of (predicted_minutes, confidence) or None if cannot predict
        """
        if current_temp >= target_temp:
            return (0, 1.0)  # Already at target
            
        # Use physics-based model if ML model not available
        if self.model is None:
            return self._physics_based_prediction(
                current_temp, target_temp, grill_temp, 
                grill_set_temp, ambient_temp, probe_id
            )
            
        try:
            # Extract features
            features = self.extract_features(
                current_temp, target_temp, grill_temp,
                grill_set_temp, ambient_temp, probe_id
            )
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Make prediction
            prediction = self.model.predict(features_scaled)[0]
            
            # Convert from seconds to minutes
            predicted_minutes = max(0, prediction / 60)
            
            # Calculate confidence based on temperature rate and progress
            temp_progress = features[0][10]  # temp_progress feature
            temp_rate = features[0][7]  # temp_rate feature
            
            # Higher confidence if we have good temperature progress and positive rate
            if temp_rate > 0 and temp_progress > 0.1:
                confidence = min(0.9, 0.5 + temp_progress * 0.4)
            else:
                confidence = 0.3  # Low confidence at start
                
            return (predicted_minutes, confidence)
            
        except Exception as e:
            print(f"Prediction error: {e}")
            return None
    
    def train(self, features_df: pd.DataFrame) -> Dict[str, float]:
        """Train the model on historical data.
        
        Args:
            features_df: DataFrame with features and time_to_target label
            
        Returns:
            Dictionary with training metrics
        """
        # Prepare features and labels
        X = features_df[self.feature_names].values
        y = features_df['time_to_target'].values
        
        # Remove outliers (cook times > 2 hours)
        mask = y < 7200
        X = X[mask]
        y = y[mask]
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train multiple models and select best
        models = {
            'random_forest': RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42
            ),
            'gradient_boost': GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        }
        
        best_score = -float('inf')
        best_model = None
        best_name = None
        
        for name, model in models.items():
            model.fit(X_train_scaled, y_train)
            score = model.score(X_test_scaled, y_test)
            
            if score > best_score:
                best_score = score
                best_model = model
                best_name = name
        
        self.model = best_model
        
        # Calculate metrics
        y_pred = self.model.predict(X_test_scaled)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        # Save model
        self.save_model()
        
        return {
            'model_type': best_name,
            'mae_seconds': mae,
            'mae_minutes': mae / 60,
            'r2_score': r2,
            'samples_trained': len(X_train),
            'samples_tested': len(X_test)
        }
    
    def save_model(self):
        """Save the trained model and scaler."""
        if self.model is not None:
            model_file = self.model_path / 'temperature_model.pkl'
            scaler_file = self.model_path / 'temperature_scaler.pkl'
            
            with open(model_file, 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(scaler_file, 'wb') as f:
                pickle.dump(self.scaler, f)
                
            # Save metadata
            metadata = {
                'trained_at': datetime.now().isoformat(),
                'feature_names': self.feature_names,
                'model_type': type(self.model).__name__
            }
            
            with open(self.model_path / 'model_metadata.json', 'w') as f:
                json.dump(metadata, f, indent=2)
    
    def load_model(self) -> bool:
        """Load a previously trained model.
        
        Returns:
            True if model loaded successfully
        """
        model_file = self.model_path / 'temperature_model.pkl'
        scaler_file = self.model_path / 'temperature_scaler.pkl'
        
        if model_file.exists() and scaler_file.exists():
            try:
                with open(model_file, 'rb') as f:
                    self.model = pickle.load(f)
                
                with open(scaler_file, 'rb') as f:
                    self.scaler = pickle.load(f)
                    
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
                return False
        
        return False
    
    def format_prediction(self, prediction: Optional[Tuple[float, float]]) -> str:
        """Format prediction for display.
        
        Args:
            prediction: Tuple of (minutes, confidence) or None
            
        Returns:
            Formatted string for display
        """
        if prediction is None:
            return "Unable to predict"
            
        minutes, confidence = prediction
        
        if minutes < 1:
            return "Less than 1 minute"
        elif minutes > 120:
            hours = minutes / 60
            return f"~{hours:.1f} hours"
        else:
            # Round to reasonable precision based on confidence
            if confidence > 0.7:
                return f"~{int(minutes)} minutes"
            else:
                # Round to 5 minute intervals for lower confidence
                rounded = round(minutes / 5) * 5
                return f"~{int(rounded)} minutes (estimate)"
    
    def _physics_based_prediction(self,
                                  current_temp: float,
                                  target_temp: float,
                                  grill_temp: float,
                                  grill_set_temp: float,
                                  ambient_temp: float,
                                  probe_id: str) -> Optional[Tuple[float, float]]:
        """Physics-based prediction when ML model not available.
        
        Uses Newton's law of cooling and empirical adjustments.
        """
        # Update temperature history
        now = datetime.now().timestamp()
        if probe_id not in self.temp_history:
            self.temp_history[probe_id] = []
        
        self.temp_history[probe_id].append((now, current_temp, grill_temp))
        
        # Keep only last 5 minutes
        cutoff = now - 300
        self.temp_history[probe_id] = [
            (t, temp, grill) for t, temp, grill in self.temp_history[probe_id] 
            if t > cutoff
        ]
        
        # Calculate current heating rate
        heating_rate = 0  # degrees per minute
        if len(self.temp_history[probe_id]) >= 2:
            # Use last 60 seconds of data
            recent = [(t, temp) for t, temp, _ in self.temp_history[probe_id] if t > now - 60]
            if len(recent) >= 2:
                dt = (recent[-1][0] - recent[0][0]) / 60  # minutes
                if dt > 0:
                    heating_rate = (recent[-1][1] - recent[0][1]) / dt
        
        # If we have a good heating rate, use it
        if heating_rate > 0.5:  # At least 0.5°F/min
            remaining_temp = target_temp - current_temp
            estimated_minutes = remaining_temp / heating_rate
            
            # Adjust for non-linear heating (slows down as approaches target)
            progress = (current_temp - ambient_temp) / (target_temp - ambient_temp)
            if progress > 0.7:  # Final 30% takes longer
                estimated_minutes *= 1.3
            
            confidence = min(0.8, 0.3 + len(self.temp_history[probe_id]) * 0.05)
            return (estimated_minutes, confidence)
        
        # Fallback: Use typical heating curves
        # Assume roughly 2-4°F/min when grill is at temp
        if grill_temp >= grill_set_temp * 0.9:  # Grill is close to set temp
            base_rate = 3.0  # °F/min
            
            # Adjust based on temperature differential
            temp_diff_factor = (grill_temp - current_temp) / 100
            heating_rate = base_rate * (0.5 + temp_diff_factor * 0.5)
            
            remaining_temp = target_temp - current_temp
            estimated_minutes = remaining_temp / heating_rate
            
            return (estimated_minutes, 0.4)  # Low confidence for estimate
        else:
            # Grill still heating up
            return None  # Can't predict reliably