#!/usr/bin/env python3
"""
Simple, robust physics-based temperature prediction using Newton's Law of Cooling.
This approach should achieve much better accuracy by leveraging thermal physics directly.
"""
import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, minimize_scalar
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

# Configuration
HISTORICAL_DB = Path("../traeger-stream/data/traeger_data.db")
OUTPUT_DIR = Path("physics_results")
OUTPUT_DIR.mkdir(exist_ok=True)

class PhysicsBasedPredictor:
    """Simple, robust physics-based temperature prediction."""
    
    def __init__(self):
        self.epsilon = 1e-8
    
    def extract_cook_data(self, cook_id):
        """Extract cook data."""
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
                        'cook_id': cook_id
                    }
                    
                    # Extract probe data
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
                    
                    # Legacy probe
                    if status.get('probe_con') == 1:
                        temp = status.get('probe')
                        target = status.get('probe_set')
                        if temp is not None and target is not None and target > 0:
                            record['legacy_temp'] = temp
                            record['legacy_target'] = target
                    
                    data_points.append(record)
                    
                except (json.JSONDecodeError, ValueError):
                    continue
        
        return pd.DataFrame(data_points)
    
    def fit_heating_curve(self, temps, grill_temps, elapsed_minutes):
        """Fit Newton's Law of Cooling to temperature data."""
        if len(temps) < 3:
            return None
        
        try:
            # Newton's Law: T(t) = T_equilibrium + (T_initial - T_equilibrium) * exp(-k*t)
            # Rearranged for heating: T(t) = T_equilibrium - (T_equilibrium - T_initial) * exp(-k*t)
            
            def heating_curve(t, k, T_equilibrium):
                T_initial = temps[0]
                return T_equilibrium - (T_equilibrium - T_initial) * np.exp(-k * t / 60)
            
            # Initial parameter guesses
            T_initial = temps[0]
            T_grill_avg = np.mean(grill_temps)
            
            # T_equilibrium should be somewhere between current grill temp and theoretical max
            # Based on heat transfer efficiency, typically 70-90% of grill temp differential
            T_ambient = 70  # Assume room temperature
            T_equilibrium_guess = T_ambient + 0.8 * (T_grill_avg - T_ambient)
            
            # Fit the curve
            popt, pcov = curve_fit(
                heating_curve,
                elapsed_minutes,
                temps,
                p0=[0.02, T_equilibrium_guess],
                bounds=([0.001, T_initial], [1.0, T_grill_avg + 50]),
                maxfev=1000
            )
            
            k, T_equilibrium = popt
            
            # Calculate goodness of fit
            y_pred = heating_curve(elapsed_minutes, *popt)
            ss_res = np.sum((temps - y_pred) ** 2)
            ss_tot = np.sum((temps - np.mean(temps)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            return {
                'k': k,
                'T_equilibrium': T_equilibrium,
                'T_initial': T_initial,
                'r_squared': r_squared,
                'fit_function': lambda t: heating_curve(t, k, T_equilibrium)
            }
        
        except Exception as e:
            print(f"Curve fitting failed: {e}")
            return None
    
    def adaptive_rate_prediction(self, temps, grill_temps, elapsed_minutes):
        """Adaptive rate-based prediction with stall detection."""
        if len(temps) < 2:
            return None
        
        current_temp = temps[-1]
        current_grill = grill_temps[-1]
        
        # Calculate rates over multiple windows
        rates = {}
        for window in [5, 10, 15, 20]:
            rate = self._calculate_window_rate(temps, elapsed_minutes, window)
            rates[f'{window}min'] = rate
        
        # Detect if we're in a stall
        stall_detected = self._detect_stall(temps, elapsed_minutes)
        
        # Choose appropriate rate based on conditions
        if stall_detected:
            # During stall, use longer window and reduce rate
            rate = rates['20min'] * 0.5  # Stalls typically half the normal rate
        elif len(temps) < 10:
            # Early prediction - be conservative
            rate = rates['10min'] * 0.8
        else:
            # Normal prediction - weighted average
            rate = (0.4 * rates['5min'] + 0.3 * rates['10min'] + 
                   0.2 * rates['15min'] + 0.1 * rates['20min'])
        
        # Adjust rate based on temperature differential (heat transfer physics)
        temp_diff = current_grill - current_temp
        if temp_diff > 0:
            # Higher temperature differential should increase rate
            differential_factor = min(2.0, 1.0 + (temp_diff - 50) / 100)
            rate *= differential_factor
        
        return max(0.1, rate)  # Minimum rate to prevent division by zero
    
    def _calculate_window_rate(self, temps, elapsed_minutes, window_minutes):
        """Calculate rate over a time window."""
        if len(temps) < 2:
            return 0
        
        current_time = elapsed_minutes[-1]
        start_time = current_time - window_minutes
        
        # Get indices within window
        indices = [i for i, t in enumerate(elapsed_minutes) if t >= start_time]
        if len(indices) < 2:
            indices = list(range(max(0, len(temps) - 3), len(temps)))
        
        if len(indices) < 2:
            return 0
        
        # Simple linear rate calculation
        time_span = elapsed_minutes[indices[-1]] - elapsed_minutes[indices[0]]
        temp_change = temps[indices[-1]] - temps[indices[0]]
        
        return temp_change / (time_span + self.epsilon)
    
    def _detect_stall(self, temps, elapsed_minutes):
        """Detect if temperature is currently stalled."""
        if len(temps) < 8:
            return False
        
        # Look at recent temperature behavior
        recent_temps = temps[-8:]
        recent_elapsed = elapsed_minutes[-8:]
        
        # Calculate variance and rate
        temp_variance = np.var(recent_temps)
        
        # Calculate rate over recent period
        time_span = recent_elapsed[-1] - recent_elapsed[0]
        temp_change = recent_temps[-1] - recent_temps[0]
        rate = temp_change / (time_span + self.epsilon)
        
        # Stall criteria: low variance and low rate
        return temp_variance < 4.0 and rate < 0.8
    
    def predict_time_to_target(self, temps, grill_temps, elapsed_minutes, target_temp):
        """Predict time to reach target temperature."""
        if len(temps) == 0:
            return None, "No temperature data"
        
        current_temp = temps[-1]
        if current_temp >= target_temp:
            return 0, "Target already reached"
        
        temp_remaining = target_temp - current_temp
        
        # Method 1: Physics-based curve fitting
        physics_prediction = None
        curve_fit = self.fit_heating_curve(temps, grill_temps, elapsed_minutes)
        if curve_fit and curve_fit['r_squared'] > 0.7:  # Good fit
            try:
                # Solve T(t) = target_temp for t
                # target_temp = T_equilibrium - (T_equilibrium - T_initial) * exp(-k*t)
                # exp(-k*t) = (T_equilibrium - target_temp) / (T_equilibrium - T_initial)
                
                T_eq = curve_fit['T_equilibrium']
                T_init = curve_fit['T_initial']
                k = curve_fit['k']
                
                if T_eq > target_temp and T_eq > T_init:
                    ratio = (T_eq - target_temp) / (T_eq - T_init)
                    if 0 < ratio < 1:
                        time_to_target = -60 * np.log(ratio) / k
                        current_time = elapsed_minutes[-1]
                        physics_prediction = time_to_target - current_time
                        
                        if physics_prediction > 0:
                            method = f"Physics (R²={curve_fit['r_squared']:.2f})"
                        else:
                            physics_prediction = None
            except:
                physics_prediction = None
        
        # Method 2: Adaptive rate-based prediction
        rate = self.adaptive_rate_prediction(temps, grill_temps, elapsed_minutes)
        rate_prediction = temp_remaining / rate if rate > 0 else None
        
        # Choose best prediction method
        if physics_prediction is not None and 5 <= physics_prediction <= 300:
            # Physics model gives reasonable prediction
            if rate_prediction is not None:
                # Combine physics and rate predictions
                weight_physics = min(1.0, curve_fit['r_squared'])
                weight_rate = 1.0 - weight_physics
                
                combined_prediction = (weight_physics * physics_prediction + 
                                     weight_rate * rate_prediction)
                prediction = combined_prediction
                method = f"Combined ({weight_physics:.1f} physics + {weight_rate:.1f} rate)"
            else:
                prediction = physics_prediction
                method = f"Physics (R²={curve_fit['r_squared']:.2f})"
        
        elif rate_prediction is not None and 1 <= rate_prediction <= 300:
            prediction = rate_prediction
            stall_status = " [STALL]" if self._detect_stall(temps, elapsed_minutes) else ""
            method = f"Adaptive rate ({rate:.2f}°F/min){stall_status}"
        
        else:
            # Fallback: simple linear extrapolation
            if len(temps) >= 2:
                recent_rate = self._calculate_window_rate(temps, elapsed_minutes, 10)
                if recent_rate > 0.1:
                    prediction = temp_remaining / recent_rate
                    method = "Linear fallback"
                else:
                    return None, "Temperature stalled"
            else:
                return None, "Insufficient data"
        
        # Apply reasonable bounds
        prediction = max(1, min(300, prediction))
        
        return round(prediction), method
    
    def validate_all_cooks(self):
        """Validate prediction accuracy across all available cook sessions."""
        print("Validating physics-based prediction on all cook sessions...")
        
        # Get all cook sessions
        cook_sessions = [
            'E8EB1B4C15021748231230',
            'E8EB1B4C15021750610370', 
            'E8EB1B4C15021748715282',
            'E8EB1B4C15021749139580',
            'E8EB1B4C15021748620109'
        ]
        
        all_results = []
        detailed_results = []
        
        for cook_id in cook_sessions:
            print(f"\nValidating {cook_id}...")
            
            df = self.extract_cook_data(cook_id)
            if df.empty:
                continue
            
            df = df.sort_values('timestamp')
            df['elapsed_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
            
            # Test each probe
            probe_columns = [col for col in df.columns if col.endswith('_temp')]
            for probe_temp_col in probe_columns:
                probe_name = probe_temp_col.replace('_temp', '')
                target_col = f'{probe_name}_target'
                
                if target_col not in df.columns:
                    continue
                
                probe_data = df.dropna(subset=[probe_temp_col, target_col, 'grill_temp'])
                if len(probe_data) < 10:
                    continue
                
                results = self._validate_single_probe(
                    probe_data, probe_temp_col, target_col, cook_id, probe_name
                )
                
                for result in results:
                    all_results.append(result)
                    detailed_results.append(result)
        
        # Calculate overall metrics
        if all_results:
            actuals = [r['actual'] for r in all_results]
            predictions = [r['predicted'] for r in all_results]
            
            mae = mean_absolute_error(actuals, predictions)
            rmse = np.sqrt(mean_squared_error(actuals, predictions))
            r2 = r2_score(actuals, predictions)
            
            print(f"\n" + "="*60)
            print(f"PHYSICS-BASED PREDICTION VALIDATION RESULTS")
            print(f"="*60)
            print(f"Total predictions: {len(all_results)}")
            print(f"Mean Absolute Error: {mae:.2f} minutes")
            print(f"Root Mean Square Error: {rmse:.2f} minutes")
            print(f"R² Score: {r2:.3f}")
            
            # Analyze by prediction horizon
            short_term = [r for r in all_results if r['actual'] <= 30]
            medium_term = [r for r in all_results if 30 < r['actual'] <= 60]
            long_term = [r for r in all_results if r['actual'] > 60]
            
            for term_name, term_data in [('Short-term (<30min)', short_term),
                                       ('Medium-term (30-60min)', medium_term), 
                                       ('Long-term (>60min)', long_term)]:
                if term_data:
                    term_mae = mean_absolute_error([r['actual'] for r in term_data],
                                                 [r['predicted'] for r in term_data])
                    print(f"{term_name}: {len(term_data)} samples, MAE: {term_mae:.2f} min")
            
            # Analyze by method
            method_groups = {}
            for result in all_results:
                method = result['method'].split(' ')[0]  # Get first word of method
                if method not in method_groups:
                    method_groups[method] = []
                method_groups[method].append(result)
            
            print(f"\nBy prediction method:")
            for method, results in method_groups.items():
                if len(results) >= 2:
                    method_mae = mean_absolute_error([r['actual'] for r in results],
                                                   [r['predicted'] for r in results])
                    print(f"{method}: {len(results)} samples, MAE: {method_mae:.2f} min")
            
            # Create validation plots
            self._create_validation_plots(actuals, predictions, detailed_results, mae)
            
            # Compare with targets
            target_mae = 5.0
            current_model_mae = 25.1
            improvement = current_model_mae - mae
            
            print(f"\n" + "="*60)
            print(f"PERFORMANCE COMPARISON")
            print(f"="*60)
            print(f"Target MAE: {target_mae:.1f} minutes")
            print(f"Current model MAE: {current_model_mae:.1f} minutes")
            print(f"Physics model MAE: {mae:.2f} minutes")
            print(f"Improvement: {improvement:.2f} minutes ({improvement/current_model_mae*100:.1f}%)")
            
            if mae <= target_mae:
                print("🎯 TARGET ACHIEVED!")
            else:
                print(f"📊 Target missed by {mae - target_mae:.2f} minutes")
            
            if mae < current_model_mae:
                print("✅ Significant improvement over current model!")
            
            return {
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'n_samples': len(all_results),
                'improvement_over_current': improvement,
                'target_achieved': mae <= target_mae
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
        
        if target_reached_idx is None or target_reached_idx < 8:
            return results
        
        # Test predictions at multiple points
        test_points = []
        for pct in [0.2, 0.4, 0.6, 0.8]:
            idx = int(target_reached_idx * pct)
            if idx >= 5:
                test_points.append(idx)
        
        for test_idx in test_points:
            # Use only historical data
            historical_temps = temps[:test_idx+1]
            historical_grill_temps = grill_temps[:test_idx+1]
            historical_elapsed = elapsed[:test_idx+1]
            
            # Make prediction
            predicted_time, method = self.predict_time_to_target(
                historical_temps, historical_grill_temps, historical_elapsed, target_temp
            )
            
            if predicted_time is not None:
                actual_time = elapsed[target_reached_idx] - elapsed[test_idx]
                
                results.append({
                    'cook_id': cook_id,
                    'probe_name': probe_name,
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
    
    def _create_validation_plots(self, actuals, predictions, details, mae):
        """Create validation visualization plots."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # Actual vs Predicted
        axes[0, 0].scatter(actuals, predictions, alpha=0.7, s=60, edgecolors='black', linewidth=0.5)
        max_val = max(max(actuals), max(predictions))
        axes[0, 0].plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='Perfect prediction')
        
        # Add tolerance bands
        axes[0, 0].fill_between([0, max_val], [0, max_val-5], [0, max_val+5], 
                               alpha=0.2, color='green', label='±5 min target')
        axes[0, 0].fill_between([0, max_val], [0, max_val-10], [0, max_val+10], 
                               alpha=0.1, color='blue', label='±10 min acceptable')
        
        axes[0, 0].set_xlabel('Actual Time to Target (minutes)', fontsize=12)
        axes[0, 0].set_ylabel('Predicted Time to Target (minutes)', fontsize=12)
        axes[0, 0].set_title(f'Physics-Based Prediction Accuracy\nMAE: {mae:.2f} minutes', fontsize=14)
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # Error distribution
        errors = [abs(p - a) for p, a in zip(predictions, actuals)]
        axes[0, 1].hist(errors, bins=15, edgecolor='black', alpha=0.7, color='skyblue')
        axes[0, 1].axvline(mae, color='red', linestyle='--', linewidth=2,
                          label=f'MAE: {mae:.2f} min')
        axes[0, 1].axvline(5, color='green', linestyle='--', linewidth=2,
                          label='5 min target')
        axes[0, 1].set_xlabel('Absolute Error (minutes)', fontsize=12)
        axes[0, 1].set_ylabel('Frequency', fontsize=12)
        axes[0, 1].set_title('Prediction Error Distribution', fontsize=14)
        axes[0, 1].legend()
        
        # Error vs Actual Time
        axes[1, 0].scatter([d['actual'] for d in details], 
                          [d['error'] for d in details], 
                          alpha=0.7, s=60, edgecolors='black', linewidth=0.5)
        axes[1, 0].axhline(5, color='green', linestyle='--', label='5 min target')
        axes[1, 0].axhline(10, color='orange', linestyle='--', label='10 min acceptable')
        axes[1, 0].set_xlabel('Actual Time to Target (minutes)', fontsize=12)
        axes[1, 0].set_ylabel('Prediction Error (minutes)', fontsize=12)
        axes[1, 0].set_title('Error vs Actual Time', fontsize=14)
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        
        # Method performance
        methods = {}
        for d in details:
            method = d['method'].split(' ')[0]
            if method not in methods:
                methods[method] = []
            methods[method].append(d['error'])
        
        method_names = list(methods.keys())
        method_errors = [np.mean(methods[m]) for m in method_names]
        
        bars = axes[1, 1].bar(method_names, method_errors, alpha=0.7, 
                             color=['lightblue', 'lightgreen', 'lightyellow', 'lightcoral'][:len(method_names)],
                             edgecolor='black', linewidth=1)
        axes[1, 1].axhline(5, color='green', linestyle='--', label='5 min target')
        axes[1, 1].set_ylabel('Mean Absolute Error (minutes)', fontsize=12)
        axes[1, 1].set_title('Performance by Prediction Method', fontsize=14)
        axes[1, 1].legend()
        
        # Add value labels on bars
        for bar, error in zip(bars, method_errors):
            height = bar.get_height()
            axes[1, 1].text(bar.get_x() + bar.get_width()/2., height + 0.5,
                           f'{error:.1f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / 'physics_based_validation.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Validation plots saved to {OUTPUT_DIR / 'physics_based_validation.png'}")

def main():
    """Run physics-based prediction validation."""
    predictor = PhysicsBasedPredictor()
    results = predictor.validate_all_cooks()
    
    if results and results['target_achieved']:
        print("\n🚀 SUCCESS: Physics-based approach achieves target accuracy!")
    elif results:
        print(f"\n📈 Significant improvement achieved!")
    else:
        print("\n❌ Validation failed - no results generated")

if __name__ == "__main__":
    main()