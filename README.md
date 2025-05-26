# Traeger Stream

## TODO
* Write a great readme & mesh it with [this one](traeger-stream/README.md)
* Incorporate the [streaming walkthrough](traeger-stream/TRAEGER_STREAMING_WALKTHROUGH.md)

### Temperature predictor design (MIW)
 Temperature Predictor Design

  Inputs

  1. Temperature readings: Array of (temperature, timestamp) pairs - minimum 3 points
  2. Target temperature: The desired final temperature

  Processing

  1. First derivative: Calculate rate of change using ALL input data points
  2. Second derivative: Calculate acceleration using ALL input data points
  3. Nonlinear extrapolation: Use a quadratic model that incorporates both derivatives to handle acceleration AND deceleration

  Extrapolation Method

  - Use kinematic-style equations that account for changing rates
  - Something like: position = initial_position + velocity*time + 0.5*acceleration*time²
  - Adapted for temperature: solve for time when temperature reaches target

  Output

  - Predicted time to reach target temperature

  What we're NOT handling (for now)

  - Decreasing temperatures (just calculate and report)
  - Stalls (just calculate and report)
  - No special filtering or smoothing
  - No confidence intervals
  - No physical constraints

  The key insight is that we need the second derivative because temperature changes are rarely linear - they typically accelerate early
  then decelerate as they approach the target.