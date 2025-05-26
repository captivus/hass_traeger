"""Simple temperature predictor using quadratic extrapolation."""

from datetime import datetime
from typing import List, Tuple, Optional
import numpy as np


class SimpleTemperaturePredictor:
    """Predicts time to reach target temperature using quadratic model."""
    
    def __init__(self):
        """Initialize the temperature predictor."""
        self.temp_history: dict[str, List[Tuple[float, float]]] = {}
    
    def clear_history(self):
        """Clear all temperature history."""
        self.temp_history.clear()
        print("DEBUG: Cleared all temperature history")
    
    def add_reading(self, probe_id: str, temperature: float, timestamp: Optional[float] = None) -> None:
        """Add a temperature reading for a probe.
        
        Args:
            probe_id: Unique identifier for the probe
            temperature: Current temperature in °F
            timestamp: Unix timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        if probe_id not in self.temp_history:
            self.temp_history[probe_id] = []
            print(f"DEBUG: Created new history for probe {probe_id}")
        
        self.temp_history[probe_id].append((timestamp, temperature))
        if len(self.temp_history[probe_id]) % 10 == 0:  # Log every 10th reading
            print(f"DEBUG: Probe {probe_id} now has {len(self.temp_history[probe_id])} readings")
    
    def predict_time_to_target(self, probe_id: str, target_temperature: float) -> Optional[Tuple[float, float]]:
        """Predict time to reach target temperature.
        
        Args:
            probe_id: Unique identifier for the probe
            target_temperature: Target temperature in °F
            
        Returns:
            Tuple of (minutes_to_target, confidence) or None if cannot predict
        """
        if probe_id not in self.temp_history or len(self.temp_history[probe_id]) < 3:
            print(f"DEBUG: Not enough data for probe {probe_id}. History: {len(self.temp_history.get(probe_id, []))}")
            return None
        
        history = self.temp_history[probe_id]
        current_temp = history[-1][1]
        
        # Already at or above target
        if current_temp >= target_temperature:
            print(f"DEBUG: Probe {probe_id} already at target. Current: {current_temp}, Target: {target_temperature}")
            return (0.0, 1.0)
        
        # Extract time and temperature arrays
        times = np.array([t for t, _ in history])
        temps = np.array([temp for _, temp in history])
        
        # Normalize time to start at 0
        t0 = times[0]
        times_normalized = times - t0
        
        # Calculate first derivative (velocity) using all points
        velocity = self._calculate_derivative(times_normalized, temps)
        
        # Calculate second derivative (acceleration) using all points
        acceleration = self._calculate_second_derivative(times_normalized, temps)
        
        # Current values (at last data point)
        current_time = times_normalized[-1]
        current_velocity = velocity
        
        # Check for decreasing temperature
        if current_velocity <= 0:
            print(f"DEBUG: Probe {probe_id} velocity <= 0: {current_velocity:.4f}")
            return None  # Temperature is not increasing
        
        # Solve quadratic equation: target = current + v*t + 0.5*a*t²
        # Rearranged: 0.5*a*t² + v*t + (current - target) = 0
        a = 0.5 * acceleration
        b = current_velocity
        c = current_temp - target_temperature
        
        # Handle different cases
        if abs(a) < 1e-6:  # Linear case (no acceleration)
            if abs(b) < 1e-6:  # No change
                return None
            time_to_target = -c / b
        else:  # Quadratic case
            discriminant = b**2 - 4*a*c
            if discriminant < 0:
                return None  # No real solution
            
            # Use positive root
            t1 = (-b + np.sqrt(discriminant)) / (2*a)
            t2 = (-b - np.sqrt(discriminant)) / (2*a)
            
            # Choose the positive, smaller root
            valid_times = [t for t in [t1, t2] if t > 0]
            if not valid_times:
                print(f"DEBUG: Probe {probe_id} no valid positive roots. t1={t1:.2f}, t2={t2:.2f}")
                return None
            
            time_to_target = min(valid_times)
        
        # Convert from seconds to minutes
        minutes_to_target = time_to_target / 60
        
        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(history, current_velocity, acceleration)
        
        print(f"DEBUG: Prediction for probe {probe_id}: {minutes_to_target:.1f} minutes (confidence: {confidence:.2f})")
        return (minutes_to_target, confidence)
    
    def _calculate_derivative(self, times: np.ndarray, values: np.ndarray) -> float:
        """Calculate the first derivative using linear regression."""
        if len(times) < 2:
            return 0.0
        
        # Fit linear model to get slope (first derivative)
        coeffs = np.polyfit(times, values, 1)
        return coeffs[0]  # Slope = velocity
    
    def _calculate_second_derivative(self, times: np.ndarray, values: np.ndarray) -> float:
        """Calculate the second derivative using quadratic regression."""
        if len(times) < 3:
            return 0.0
        
        # Fit quadratic model
        coeffs = np.polyfit(times, values, 2)
        # For y = at² + bt + c, acceleration = 2a
        return 2 * coeffs[0]
    
    def _calculate_confidence(self, history: List[Tuple[float, float]], 
                            velocity: float, acceleration: float) -> float:
        """Calculate prediction confidence based on data quality."""
        # Base confidence on number of data points
        n_points = len(history)
        point_confidence = min(1.0, n_points / 10.0)  # Max confidence at 10+ points
        
        # Reduce confidence for very low velocity
        if velocity < 0.1:  # Less than 0.1°F/second
            velocity_confidence = 0.3
        else:
            velocity_confidence = 0.8
        
        # Check for consistent heating (low variance in recent derivatives)
        if n_points >= 5:
            recent_times = np.array([t for t, _ in history[-5:]])
            recent_temps = np.array([temp for _, temp in history[-5:]])
            recent_times_norm = recent_times - recent_times[0]
            
            # Calculate instantaneous rates
            rates = []
            for i in range(1, len(recent_times_norm)):
                dt = recent_times_norm[i] - recent_times_norm[i-1]
                if dt > 0:
                    rate = (recent_temps[i] - recent_temps[i-1]) / dt
                    rates.append(rate)
            
            if rates:
                rate_variance = np.var(rates)
                # Lower variance = higher confidence
                consistency_confidence = np.exp(-rate_variance / 0.1)  # Decay factor
            else:
                consistency_confidence = 0.5
        else:
            consistency_confidence = 0.5
        
        # Combine confidence factors
        confidence = point_confidence * velocity_confidence * consistency_confidence
        
        return min(0.95, confidence)  # Cap at 95%
    
    def format_prediction(self, prediction: Optional[Tuple[float, float]]) -> str:
        """Format prediction for display.
        
        Args:
            prediction: Tuple of (minutes, confidence) or None
            
        Returns:
            Formatted string for display
        """
        if prediction is None:
            return "Temperature not increasing"
        
        minutes, confidence = prediction
        
        if minutes < 1:
            return "Less than 1 minute"
        elif minutes > 180:  # More than 3 hours
            return "More than 3 hours"
        elif confidence > 0.7:
            # High confidence - show precise time
            if minutes < 60:
                return f"~{int(minutes)} minutes"
            else:
                hours = minutes / 60
                return f"~{hours:.1f} hours"
        else:
            # Low confidence - round to intervals
            if minutes < 60:
                rounded = round(minutes / 5) * 5
                return f"~{int(rounded)} minutes (estimate)"
            else:
                hours = round(minutes / 60 * 2) / 2  # Round to 0.5 hours
                return f"~{hours:.1f} hours (estimate)"