#!/usr/bin/env python3
"""
High-accuracy temperature prediction model with physics-based features
and proper time-series validation methodology.
"""
import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.stats import pearsonr
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

# Configuration
HISTORICAL_DB = Path("../traeger-stream/data/traeger_data.db")
OUTPUT_DIR = Path("high_accuracy_results")
OUTPUT_DIR.mkdir(exist_ok=True)

class PhysicsBasedFeatureEngineer:
    """Advanced feature engineering based on heat transfer physics."""
    
    def __init__(self):
        self.epsilon = 1e-8  # Small value to prevent division by zero
    
    def calculate_thermal_features(self, temps, grill_temps, elapsed_minutes):
        """Calculate physics-based thermal features."""
        features = {}
        
        if len(temps) < 2:
            return self._empty_features()
        
        # Basic thermal properties
        features['current_temp'] = temps[-1]
        features['grill_temp'] = grill_temps[-1]
        features['temp_differential'] = grill_temps[-1] - temps[-1]
        features['elapsed_time'] = elapsed_minutes[-1]
        
        # Temperature rates with different time windows
        features.update(self._calculate_rates(temps, elapsed_minutes))
        
        # Thermal momentum and acceleration
        features.update(self._calculate_momentum(temps, elapsed_minutes))
        
        # Heat transfer efficiency metrics
        features.update(self._calculate_heat_transfer(temps, grill_temps, elapsed_minutes))
        
        # Cooking phase detection
        features.update(self._detect_cooking_phase(temps, grill_temps, elapsed_minutes))
        
        # Exponential curve fitting
        features.update(self._fit_exponential_model(temps, grill_temps, elapsed_minutes))
        
        return features
    
    def _calculate_rates(self, temps, elapsed_minutes):
        """Calculate temperature rates over multiple time windows."""
        rates = {}
        
        # Instantaneous rate (last 2 points)
        if len(temps) >= 2:
            dt = elapsed_minutes[-1] - elapsed_minutes[-2]
            rates['instantaneous_rate'] = (temps[-1] - temps[-2]) / (dt + self.epsilon)
        else:
            rates['instantaneous_rate'] = 0
        
        # Multi-window rates
        for window in [5, 10, 15, 20]:
            window_rate = self._calculate_window_rate(temps, elapsed_minutes, window)
            rates[f'rate_{window}min'] = window_rate
        
        # Rate stability (variance of recent rates)
        if len(temps) >= 5:
            recent_rates = []
            for i in range(max(1, len(temps) - 5), len(temps)):
                if i > 0:
                    dt = elapsed_minutes[i] - elapsed_minutes[i-1]
                    rate = (temps[i] - temps[i-1]) / (dt + self.epsilon)
                    recent_rates.append(rate)
            
            rates['rate_stability'] = np.std(recent_rates) if recent_rates else 0
        else:
            rates['rate_stability'] = 0
        
        return rates
    
    def _calculate_window_rate(self, temps, elapsed_minutes, window_minutes):
        """Calculate average rate over a time window using linear regression."""
        if len(temps) < 2:
            return 0
        
        # Find points within the time window
        current_time = elapsed_minutes[-1]
        start_time = current_time - window_minutes
        
        # Get indices for points within window
        indices = [i for i, t in enumerate(elapsed_minutes) if t >= start_time]
        
        if len(indices) < 2:
            indices = list(range(max(0, len(temps) - 3), len(temps)))
        
        if len(indices) < 2:
            return 0
        
        # Linear regression for stability
        x = [elapsed_minutes[i] for i in indices]
        y = [temps[i] for i in indices]
        
        if max(x) - min(x) < self.epsilon:
            return 0
        
        # Calculate slope
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        denominator = n * sum_x2 - sum_x ** 2
        if abs(denominator) < self.epsilon:
            return 0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope
    
    def _calculate_momentum(self, temps, elapsed_minutes):
        """Calculate thermal momentum (acceleration/deceleration)."""
        momentum = {}
        
        if len(temps) < 3:
            momentum['thermal_acceleration'] = 0
            momentum['heating_momentum'] = 0
            return momentum
        
        # Calculate acceleration (second derivative)
        rates = []
        for i in range(1, len(temps)):
            dt = elapsed_minutes[i] - elapsed_minutes[i-1]
            rate = (temps[i] - temps[i-1]) / (dt + self.epsilon)
            rates.append(rate)
        
        if len(rates) >= 2:
            # Acceleration is rate of change of rate
            recent_rates = rates[-min(5, len(rates)):]
            if len(recent_rates) >= 2:
                accel = (recent_rates[-1] - recent_rates[0]) / len(recent_rates)
                momentum['thermal_acceleration'] = accel
            else:
                momentum['thermal_acceleration'] = 0
            
            # Momentum indicator (rate * consistency)
            avg_rate = np.mean(recent_rates)
            rate_consistency = 1 / (1 + np.std(recent_rates))
            momentum['heating_momentum'] = avg_rate * rate_consistency
        else:
            momentum['thermal_acceleration'] = 0
            momentum['heating_momentum'] = 0
        
        return momentum
    
    def _calculate_heat_transfer(self, temps, grill_temps, elapsed_minutes):
        """Calculate heat transfer efficiency metrics."""
        ht = {}
        
        if len(temps) < 2:
            return {'heat_transfer_coeff': 0, 'thermal_efficiency': 0}
        
        # Heat transfer coefficient approximation
        # Rate is proportional to temperature difference (Newton's law)
        temp_diffs = [grill_temps[i] - temps[i] for i in range(len(temps))]
        
        # Calculate average efficiency over recent data
        if len(temps) >= 3:
            recent_indices = range(max(0, len(temps) - 5), len(temps))
            rates = []
            diffs = []
            
            for i in recent_indices:
                if i > 0:
                    dt = elapsed_minutes[i] - elapsed_minutes[i-1]
                    rate = (temps[i] - temps[i-1]) / (dt + self.epsilon)
                    rates.append(rate)
                    diffs.append(temp_diffs[i])
            
            # Heat transfer coefficient
            if rates and diffs:
                valid_pairs = [(r, d) for r, d in zip(rates, diffs) if d > 0]
                if valid_pairs:
                    coeffs = [r / d for r, d in valid_pairs]
                    ht['heat_transfer_coeff'] = np.mean(coeffs)
                    
                    # Thermal efficiency (how effectively heat is transferred)
                    avg_rate = np.mean([r for r, d in valid_pairs])
                    avg_diff = np.mean([d for r, d in valid_pairs])
                    ht['thermal_efficiency'] = avg_rate / (avg_diff + self.epsilon)
                else:
                    ht['heat_transfer_coeff'] = 0
                    ht['thermal_efficiency'] = 0
            else:
                ht['heat_transfer_coeff'] = 0
                ht['thermal_efficiency'] = 0
        else:
            ht['heat_transfer_coeff'] = 0
            ht['thermal_efficiency'] = 0
        
        return ht
    
    def _detect_cooking_phase(self, temps, grill_temps, elapsed_minutes):
        """Detect current cooking phase."""
        phase = {}
        
        if len(temps) < 5:
            phase['is_initial_heating'] = True
            phase['is_steady_state'] = False
            phase['is_stalled'] = False
            phase['stall_probability'] = 0
            return phase
        
        # Analyze recent temperature behavior
        recent_temps = temps[-min(10, len(temps)):]
        recent_rates = []
        
        for i in range(1, len(recent_temps)):
            idx = len(temps) - len(recent_temps) + i
            dt = elapsed_minutes[idx] - elapsed_minutes[idx-1]
            rate = (recent_temps[i] - recent_temps[i-1]) / (dt + self.epsilon)
            recent_rates.append(rate)
        
        if recent_rates:
            avg_rate = np.mean(recent_rates)
            rate_variance = np.var(recent_rates)
            temp_variance = np.var(recent_temps)
            
            # Phase detection thresholds
            phase['is_initial_heating'] = elapsed_minutes[-1] < 15 and avg_rate > 2.0
            phase['is_steady_state'] = 0.5 <= avg_rate <= 3.0 and rate_variance < 1.0
            phase['is_stalled'] = avg_rate < 0.5 and temp_variance < 4.0
            
            # Stall probability based on recent behavior
            if temp_variance < 2.0 and avg_rate < 1.0:
                phase['stall_probability'] = min(1.0, (2.0 - temp_variance) * (1.0 - avg_rate))
            else:
                phase['stall_probability'] = 0
        else:
            phase['is_initial_heating'] = True
            phase['is_steady_state'] = False
            phase['is_stalled'] = False
            phase['stall_probability'] = 0
        
        return phase
    
    def _fit_exponential_model(self, temps, grill_temps, elapsed_minutes):
        """Fit exponential heating model based on Newton's Law of Cooling."""
        model = {}
        
        if len(temps) < 5:
            return {'exp_fitted': False, 'exp_k': 0, 'exp_r_squared': 0, 'exp_prediction': 0}
        
        try:
            # Newton's law: T(t) = T_ambient + (T_grill - T_ambient) * (1 - exp(-k*t))
            def heating_curve(t, k, T_ambient, efficiency):
                T_grill_avg = np.mean(grill_temps)
                return T_ambient + efficiency * (T_grill_avg - T_ambient) * (1 - np.exp(-k * t / 60))
            
            # Fit the curve
            T_ambient_guess = temps[0]
            T_grill_avg = np.mean(grill_temps)
            
            popt, _ = curve_fit(
                heating_curve,
                elapsed_minutes,
                temps,
                p0=[0.02, T_ambient_guess, 0.7],
                bounds=([0.001, 50, 0.1], [1.0, 300, 2.0]),
                maxfev=500
            )
            
            k, T_ambient_fit, efficiency = popt
            
            # Calculate R²
            y_pred = heating_curve(elapsed_minutes, *popt)
            ss_res = np.sum((temps - y_pred) ** 2)
            ss_tot = np.sum((temps - np.mean(temps)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            model['exp_fitted'] = True
            model['exp_k'] = k
            model['exp_r_squared'] = r_squared
            
            # Use model for prediction extrapolation
            current_time = elapsed_minutes[-1]
            next_temp_1min = heating_curve(current_time + 1, *popt)
            next_temp_5min = heating_curve(current_time + 5, *popt)
            
            model['exp_prediction_1min'] = next_temp_1min - temps[-1]
            model['exp_prediction_5min'] = next_temp_5min - temps[-1]
            
        except:
            model['exp_fitted'] = False
            model['exp_k'] = 0
            model['exp_r_squared'] = 0
            model['exp_prediction_1min'] = 0
            model['exp_prediction_5min'] = 0
        
        return model
    
    def _empty_features(self):
        """Return empty feature set for insufficient data."""
        return {
            'current_temp': 0, 'grill_temp': 0, 'temp_differential': 0, 'elapsed_time': 0,
            'instantaneous_rate': 0, 'rate_5min': 0, 'rate_10min': 0, 'rate_15min': 0, 'rate_20min': 0,
            'rate_stability': 0, 'thermal_acceleration': 0, 'heating_momentum': 0,
            'heat_transfer_coeff': 0, 'thermal_efficiency': 0,
            'is_initial_heating': True, 'is_steady_state': False, 'is_stalled': False, 'stall_probability': 0,
            'exp_fitted': False, 'exp_k': 0, 'exp_r_squared': 0, 'exp_prediction_1min': 0, 'exp_prediction_5min': 0
        }

class HighAccuracyPredictor:
    """High-accuracy temperature prediction with ensemble methods."""
    
    def __init__(self):
        self.feature_engineer = PhysicsBasedFeatureEngineer()
        self.models = {}
        self.feature_names = []
        
    def extract_cook_data(self, cook_id):
        """Extract cook data with proper temporal structure."""
        with sqlite3.connect(HISTORICAL_DB) as conn:
            cursor = conn.execute("""
                SELECT timestamp, payload 
                FROM raw_messages 
                WHERE json_extract(payload, '$.status.cook_id') = ?
                ORDER BY timestamp ASC
            """, (cook_id,))
            
            data_points = []
            for timestamp, payload in cursor:
                try:
                    status = json.loads(payload).get('status', {})
                    dt = datetime.fromisoformat(timestamp)
                    
                    record = {
                        'timestamp': dt,
                        'grill_temp': status.get('grill', 0),
                        'grill_set': status.get('set', 0),
                        'cook_id': cook_id
                    }
                    
                    # Extract probe data
                    probes_found = []
                    for acc in status.get('acc', []):
                        if acc.get('con') == 1:
                            channel = acc.get('channel', 'unknown')
                            if acc.get('type') == 'probe':
                                probe_data = acc.get('probe', {})
                                temp = probe_data.get('get_temp')
                                target = probe_data.get('set_temp')
                                if temp is not None and target is not None and target > 0:
                                    record[f'{channel}_temp'] = temp
                                    record[f'{channel}_target'] = target
                                    probes_found.append(channel)
                    
                    # Legacy probe
                    if status.get('probe_con') == 1:
                        temp = status.get('probe')
                        target = status.get('probe_set')
                        if temp is not None and target is not None and target > 0:
                            record['legacy_temp'] = temp
                            record['legacy_target'] = target
                            probes_found.append('legacy')
                    
                    record['probes_active'] = probes_found
                    data_points.append(record)
                    
                except (json.JSONDecodeError, ValueError):
                    continue
        
        return pd.DataFrame(data_points)
    
    def prepare_training_data(self, cook_sessions):
        """Prepare training data with NO DATA LEAKAGE."""
        print("Preparing training data with strict temporal validation...")
        
        training_samples = []
        
        for cook_session in cook_sessions:
            cook_id = cook_session['cook_id']
            print(f"Processing {cook_id}...")
            
            df = self.extract_cook_data(cook_id)
            if df.empty:
                continue
            
            df = df.sort_values('timestamp')
            df['elapsed_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
            
            # Process each probe
            probe_columns = [col for col in df.columns if col.endswith('_temp')]
            for probe_temp_col in probe_columns:
                probe_name = probe_temp_col.replace('_temp', '')
                target_col = f'{probe_name}_target'
                
                if target_col not in df.columns:
                    continue
                
                probe_data = df.dropna(subset=[probe_temp_col, target_col, 'grill_temp'])
                if len(probe_data) < 10:
                    continue
                
                samples = self._create_temporal_samples(probe_data, probe_temp_col, target_col)
                training_samples.extend(samples)
        
        if not training_samples:
            print("No training samples created!")
            return pd.DataFrame()
        
        # Convert to DataFrame
        train_df = pd.DataFrame(training_samples)
        print(f"Created {len(train_df)} training samples")
        
        return train_df
    
    def _create_temporal_samples(self, probe_data, temp_col, target_col):
        """Create training samples with proper temporal splits."""
        samples = []
        
        temps = probe_data[temp_col].values
        targets = probe_data[target_col].values
        grill_temps = probe_data['grill_temp'].values
        elapsed = probe_data['elapsed_minutes'].values
        
        target_temp = targets[0]  # Assume target is constant
        
        # Create samples at different time points during the cook
        min_history = 5  # Minimum points needed for prediction
        sample_interval = max(1, len(temps) // 20)  # Sample up to 20 points per cook
        
        for i in range(min_history, len(temps), sample_interval):
            # Only use data up to point i (NO FUTURE INFORMATION)
            historical_temps = temps[:i+1]
            historical_grill_temps = grill_temps[:i+1]
            historical_elapsed = elapsed[:i+1]
            
            # Calculate features using only historical data
            features = self.feature_engineer.calculate_thermal_features(
                historical_temps, historical_grill_temps, historical_elapsed
            )
            
            # Calculate target: time remaining to reach target temperature
            # This is tricky - we need to find when target was ACTUALLY reached
            # But we can only look forward from current point
            
            current_temp = temps[i]
            if current_temp >= target_temp:
                continue  # Already at target, skip this sample
            
            # Look forward to find when target was reached
            time_to_target = None
            for j in range(i + 1, len(temps)):
                if temps[j] >= target_temp:
                    time_to_target = elapsed[j] - elapsed[i]
                    break
            
            # Only include samples where target was eventually reached
            # and time to target is reasonable (5-300 minutes)
            if time_to_target is not None and 5 <= time_to_target <= 300:
                features['target_temp'] = target_temp
                features['time_to_target'] = time_to_target
                features['temp_remaining'] = target_temp - current_temp
                
                # Add cook context
                features['cook_id'] = probe_data['cook_id'].iloc[0]
                features['probe_name'] = temp_col.replace('_temp', '')
                
                samples.append(features)
        
        return samples
    
    def train_models(self, train_df):
        """Train ensemble of prediction models."""
        print("Training prediction models...")
        
        if train_df.empty:
            print("No training data available!")
            return
        
        # Prepare feature matrix
        feature_columns = [col for col in train_df.columns 
                          if col not in ['time_to_target', 'cook_id', 'probe_name', 'target_temp']]
        
        X = train_df[feature_columns].values
        y = train_df['time_to_target'].values
        
        self.feature_names = feature_columns
        
        # Train multiple models
        self.models['random_forest'] = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        if XGBOOST_AVAILABLE:
            self.models['xgboost'] = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                gamma=0.1,
                random_state=42
            )
        
        # Train all models
        for name, model in self.models.items():
            print(f"Training {name}...")
            model.fit(X, y)
        
        print(f"Trained {len(self.models)} models on {len(X)} samples")
    
    def predict(self, temps, grill_temps, elapsed_minutes, target_temp):
        """Make ensemble prediction."""
        if not self.models:
            return None, "Models not trained"
        
        # Calculate features
        features = self.feature_engineer.calculate_thermal_features(
            temps, grill_temps, elapsed_minutes
        )
        
        # Create feature vector
        feature_vector = []
        for col in self.feature_names:
            feature_vector.append(features.get(col, 0))
        
        X_pred = np.array([feature_vector])
        
        # Get predictions from all models
        predictions = {}
        for name, model in self.models.items():
            try:
                pred = model.predict(X_pred)[0]
                predictions[name] = max(0, pred)  # Ensure non-negative
            except:
                predictions[name] = None
        
        # Ensemble prediction (weighted average)
        valid_predictions = [p for p in predictions.values() if p is not None]
        if valid_predictions:
            ensemble_pred = np.mean(valid_predictions)
            
            # Apply physics-based bounds
            current_temp = temps[-1]
            temp_remaining = target_temp - current_temp
            
            if temp_remaining <= 0:
                return 0, "Target reached"
            
            # Minimum time based on maximum reasonable heating rate (3°F/min)
            min_time = temp_remaining / 3.0
            
            # Maximum time based on minimum reasonable heating rate (0.1°F/min)
            max_time = temp_remaining / 0.1
            
            # Bound the prediction
            bounded_pred = np.clip(ensemble_pred, min_time, min(max_time, 300))
            
            return round(bounded_pred), f"Ensemble ({len(valid_predictions)} models)"
        
        return None, "No valid predictions"
    
    def validate_with_proper_time_series(self, cook_sessions):
        """Validate using proper time series methodology."""
        print("\nValidating with proper time series cross-validation...")
        
        all_predictions = []
        all_actuals = []
        prediction_details = []
        
        # Use walk-forward validation on each cook session
        for cook_session in cook_sessions:
            cook_id = cook_session['cook_id']
            print(f"\nValidating on {cook_id}...")
            
            df = self.extract_cook_data(cook_id)
            if df.empty:
                continue
            
            df = df.sort_values('timestamp')
            df['elapsed_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
            
            # Test on each probe
            probe_columns = [col for col in df.columns if col.endswith('_temp')]
            for probe_temp_col in probe_columns:
                probe_name = probe_temp_col.replace('_temp', '')
                target_col = f'{probe_name}_target'
                
                if target_col not in df.columns:
                    continue
                
                probe_data = df.dropna(subset=[probe_temp_col, target_col, 'grill_temp'])
                if len(probe_data) < 15:
                    continue
                
                validation_results = self._validate_single_probe(
                    probe_data, probe_temp_col, target_col, cook_id, probe_name
                )
                
                for result in validation_results:
                    all_predictions.append(result['predicted'])
                    all_actuals.append(result['actual'])
                    prediction_details.append(result)
        
        # Calculate metrics
        if all_predictions:
            mae = mean_absolute_error(all_actuals, all_predictions)
            rmse = np.sqrt(mean_squared_error(all_actuals, all_predictions))
            r2 = r2_score(all_actuals, all_predictions)
            
            print(f"\nVALIDATION RESULTS:")
            print(f"Samples: {len(all_predictions)}")
            print(f"MAE: {mae:.2f} minutes")
            print(f"RMSE: {rmse:.2f} minutes")
            print(f"R²: {r2:.3f}")
            
            # Analyze by prediction horizon
            short_term = [p for p in prediction_details if p['actual'] <= 30]
            medium_term = [p for p in prediction_details if 30 < p['actual'] <= 60]
            long_term = [p for p in prediction_details if p['actual'] > 60]
            
            for term_name, term_data in [('Short (<30min)', short_term), 
                                       ('Medium (30-60min)', medium_term),
                                       ('Long (>60min)', long_term)]:
                if term_data:
                    term_mae = mean_absolute_error([p['actual'] for p in term_data],
                                                 [p['predicted'] for p in term_data])
                    print(f"{term_name}: {len(term_data)} samples, MAE: {term_mae:.2f} min")
            
            # Create validation visualization
            self._create_validation_plots(all_actuals, all_predictions, prediction_details)
            
            return {
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'n_samples': len(all_predictions),
                'details': prediction_details
            }
        
        return None
    
    def _validate_single_probe(self, probe_data, temp_col, target_col, cook_id, probe_name):
        """Validate predictions for a single probe using walk-forward validation."""
        results = []
        
        temps = probe_data[temp_col].values
        targets = probe_data[target_col].values
        grill_temps = probe_data['grill_temp'].values
        elapsed = probe_data['elapsed_minutes'].values
        
        target_temp = targets[0]
        
        # Find when target was actually reached
        target_reached_idx = None
        for i, temp in enumerate(temps):
            if temp >= target_temp:
                target_reached_idx = i
                break
        
        if target_reached_idx is None or target_reached_idx < 10:
            return results
        
        # Test predictions at multiple points before target reached
        test_points = []
        for pct in [0.2, 0.4, 0.6, 0.8]:  # 20%, 40%, 60%, 80% of way to target
            idx = int(target_reached_idx * pct)
            if idx >= 5:  # Need minimum history
                test_points.append(idx)
        
        for test_idx in test_points:
            # Use only data up to test point
            historical_temps = temps[:test_idx+1]
            historical_grill_temps = grill_temps[:test_idx+1]
            historical_elapsed = elapsed[:test_idx+1]
            
            # Make prediction
            predicted_time, method = self.predict(
                historical_temps, historical_grill_temps, historical_elapsed, target_temp
            )
            
            if predicted_time is not None:
                # Calculate actual remaining time
                actual_time = elapsed[target_reached_idx] - elapsed[test_idx]
                
                results.append({
                    'cook_id': cook_id,
                    'probe_name': probe_name,
                    'test_point': test_idx,
                    'elapsed_time': elapsed[test_idx],
                    'current_temp': temps[test_idx],
                    'target_temp': target_temp,
                    'predicted': predicted_time,
                    'actual': actual_time,
                    'error': abs(predicted_time - actual_time),
                    'method': method,
                    'data_points': len(historical_temps)
                })
        
        return results
    
    def _create_validation_plots(self, actuals, predictions, details):
        """Create comprehensive validation plots."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # Actual vs Predicted
        axes[0, 0].scatter(actuals, predictions, alpha=0.6, s=50)
        max_val = max(max(actuals), max(predictions))
        axes[0, 0].plot([0, max_val], [0, max_val], 'r--', label='Perfect prediction')
        axes[0, 0].fill_between([0, max_val], [0, max_val-10], [0, max_val+10], 
                               alpha=0.2, color='green', label='±10 min')
        axes[0, 0].set_xlabel('Actual Time (minutes)')
        axes[0, 0].set_ylabel('Predicted Time (minutes)')
        axes[0, 0].set_title('Actual vs Predicted')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # Error distribution
        errors = [abs(p - a) for p, a in zip(predictions, actuals)]
        axes[0, 1].hist(errors, bins=20, edgecolor='black', alpha=0.7)
        axes[0, 1].axvline(np.mean(errors), color='red', linestyle='--', 
                          label=f'Mean: {np.mean(errors):.1f} min')
        axes[0, 1].set_xlabel('Absolute Error (minutes)')
        axes[0, 1].set_ylabel('Frequency')
        axes[0, 1].set_title('Error Distribution')
        axes[0, 1].legend()
        
        # Error vs Elapsed Time
        elapsed_times = [d['elapsed_time'] for d in details]
        axes[1, 0].scatter(elapsed_times, errors, alpha=0.6)
        axes[1, 0].set_xlabel('Elapsed Time (minutes)')
        axes[1, 0].set_ylabel('Prediction Error (minutes)')
        axes[1, 0].set_title('Error vs Elapsed Time')
        axes[1, 0].grid(True, alpha=0.3)
        
        # Error vs Remaining Time
        remaining_times = [d['actual'] for d in details]
        axes[1, 1].scatter(remaining_times, errors, alpha=0.6)
        axes[1, 1].set_xlabel('Actual Remaining Time (minutes)')
        axes[1, 1].set_ylabel('Prediction Error (minutes)')
        axes[1, 1].set_title('Error vs Remaining Time')
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / 'high_accuracy_validation.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Validation plots saved to {OUTPUT_DIR / 'high_accuracy_validation.png'}")

def main():
    """Main function to build and validate high-accuracy prediction model."""
    print("High-Accuracy Temperature Prediction Model")
    print("=" * 60)
    
    # Initialize predictor
    predictor = HighAccuracyPredictor()
    
    # Get cook sessions (use first 4 for training, last 1 for testing)
    cook_sessions = [
        {'cook_id': 'E8EB1B4C15021748231230'},
        {'cook_id': 'E8EB1B4C15021750610370'},
        {'cook_id': 'E8EB1B4C15021748715282'},
        {'cook_id': 'E8EB1B4C15021749139580'},
        {'cook_id': 'E8EB1B4C15021748620109'},
    ]
    
    # Split into train/test
    train_sessions = cook_sessions[:4]
    test_sessions = cook_sessions[-1:]
    
    print(f"Training on {len(train_sessions)} cook sessions")
    print(f"Testing on {len(test_sessions)} cook sessions")
    
    # Prepare training data
    train_df = predictor.prepare_training_data(train_sessions)
    if train_df.empty:
        print("Failed to prepare training data!")
        return
    
    # Train models
    predictor.train_models(train_df)
    
    # Validate on test set
    validation_results = predictor.validate_with_proper_time_series(test_sessions)
    
    if validation_results:
        print(f"\nFINAL RESULTS:")
        print(f"Mean Absolute Error: {validation_results['mae']:.2f} minutes")
        print(f"Root Mean Square Error: {validation_results['rmse']:.2f} minutes")
        print(f"R² Score: {validation_results['r2']:.3f}")
        print(f"Number of test samples: {validation_results['n_samples']}")
        
        # Compare with target
        target_mae = 5.0  # Target MAE
        improvement = 25.1 - validation_results['mae']  # vs current model
        
        print(f"\nTarget MAE: {target_mae:.1f} minutes")
        print(f"Achieved MAE: {validation_results['mae']:.2f} minutes")
        if validation_results['mae'] <= target_mae:
            print("✓ TARGET ACHIEVED!")
        else:
            print(f"Target missed by {validation_results['mae'] - target_mae:.2f} minutes")
        
        print(f"Improvement over current model: {improvement:.2f} minutes")

if __name__ == "__main__":
    main()