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
        # Sort by timestamp to maintain chronological order
        self.temp_history[probe_id].sort(key=lambda x: x[0])
        if len(self.temp_history[probe_id]) % 10 == 0:  # Log every 10th reading
            print(f"DEBUG: Probe {probe_id} now has {len(self.temp_history[probe_id])} readings")
    
    def predict_time_to_target(self, probe_id: str, target_temperature: float) -> Tuple[Optional[float], Optional[str], Optional[float], Optional[float]]:
        """Predict time to reach target temperature.
        
        Args:
            probe_id: Unique identifier for the probe
            target_temperature: Target temperature in °F
            
        Returns:
            Tuple of (minutes_to_target, message, rate, acceleration)
            - minutes_to_target: Time in minutes or None if cannot predict
            - message: Explanation when prediction is not possible
            - rate: Temperature change rate in °F/minute (1st derivative)
            - acceleration: Temperature change acceleration in °F/minute² (2nd derivative)
        """
        if probe_id not in self.temp_history:
            print(f"DEBUG: No history for probe {probe_id}")
            return (None, "No temperature data available", None, None)
        
        if len(self.temp_history[probe_id]) < 3:
            print(f"DEBUG: Not enough data for probe {probe_id}. History: {len(self.temp_history[probe_id])}")
            return (None, "Insufficient data for prediction", None, None)
        
        history = self.temp_history[probe_id]
        current_temp = history[-1][1]
        
        # Already at or above target
        if current_temp >= target_temperature:
            print(f"DEBUG: Probe {probe_id} already at target. Current: {current_temp}, Target: {target_temperature}")
            return (None, "Already at target temperature", None, None)
        
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
            # Convert to °F/minute for return
            rate_per_minute = current_velocity * 60
            accel_per_minute = acceleration * 60
            if current_velocity < -0.01:  # Significantly decreasing
                return (None, "Temperature is decreasing", rate_per_minute, accel_per_minute)
            else:  # Stable temperature
                return (None, "Temperature is stable", rate_per_minute, accel_per_minute)
        
        # Solve quadratic equation: target = current + v*t + 0.5*a*t²
        # Rearranged: 0.5*a*t² + v*t + (current - target) = 0
        a = 0.5 * acceleration
        b = current_velocity
        c = current_temp - target_temperature
        
        # Handle different cases
        if abs(a) < 1e-6:  # Linear case (no acceleration)
            if abs(b) < 1e-6:  # No change
                return (None, "Temperature is not changing", 0.0, 0.0)
            time_to_target = -c / b
        else:  # Quadratic case
            discriminant = b**2 - 4*a*c
            if discriminant < 0:
                # Convert to °F/minute for return
                rate_per_minute = current_velocity * 60
                accel_per_minute = acceleration * 60
                return (None, "Temperature curve suggests target unreachable", rate_per_minute, accel_per_minute)
            
            # Use positive root
            t1 = (-b + np.sqrt(discriminant)) / (2*a)
            t2 = (-b - np.sqrt(discriminant)) / (2*a)
            
            # Choose the positive, smaller root
            valid_times = [t for t in [t1, t2] if t > 0]
            if not valid_times:
                print(f"DEBUG: Probe {probe_id} no valid positive roots. t1={t1:.2f}, t2={t2:.2f}")
                # Convert to °F/minute for return
                rate_per_minute = current_velocity * 60
                accel_per_minute = acceleration * 60
                return (None, "Invalid prediction model", rate_per_minute, accel_per_minute)
            
            time_to_target = min(valid_times)
        
        # Convert from seconds to minutes
        minutes_to_target = time_to_target / 60
        
        # Convert rates to °F/minute
        rate_per_minute = current_velocity * 60
        accel_per_minute = acceleration * 60
        
        print(f"DEBUG: Prediction for probe {probe_id}: {minutes_to_target:.1f} minutes")
        print(f"DEBUG: Rate: {rate_per_minute:.2f} °F/min, Acceleration: {accel_per_minute:.3f} °F/min²")
        return (minutes_to_target, None, rate_per_minute, accel_per_minute)
    
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
    
    def format_prediction(self, prediction: Tuple[Optional[float], Optional[str], Optional[float], Optional[float]]) -> str:
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