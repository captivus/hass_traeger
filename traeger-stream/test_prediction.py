"""Test temperature prediction functionality."""

from traeger_client.temperature_predictor import TemperaturePredictor


def test_physics_based_prediction():
    """Test the physics-based prediction model."""
    predictor = TemperaturePredictor()
    
    print("Testing Temperature Predictions\n" + "="*40)
    
    # Test case 1: Cold start
    print("\nTest 1: Cold start (no history)")
    prediction = predictor.predict(
        current_temp=70,
        target_temp=165,
        grill_temp=250,
        grill_set_temp=250,
        ambient_temp=70,
        probe_id="test1"
    )
    if prediction:
        print(f"Result: {predictor.format_prediction(prediction)}")
    else:
        print("Result: No prediction available")
    
    # Test case 2: With some heating history
    print("\nTest 2: Simulating temperature rise")
    # Simulate temperature readings over time with timestamps
    import time
    temps = [70, 75, 82, 90, 98, 107, 116, 125]
    for i, temp in enumerate(temps):
        prediction = predictor.predict(
            current_temp=temp,
            target_temp=165,
            grill_temp=250,
            grill_set_temp=250,
            ambient_temp=70,
            probe_id="test2"
        )
        if prediction:
            print(f"  {temp}°F: {predictor.format_prediction(prediction)}")
        # Small delay to simulate time passing
        time.sleep(0.1)
    
    # Test case 3: Near target
    print("\nTest 3: Near target temperature")
    prediction = predictor.predict(
        current_temp=160,
        target_temp=165,
        grill_temp=250,
        grill_set_temp=250,
        ambient_temp=70,
        probe_id="test3"
    )
    if prediction:
        print(f"Result: {predictor.format_prediction(prediction)}")
    
    # Test case 4: Already at target
    print("\nTest 4: Already at target")
    prediction = predictor.predict(
        current_temp=165,
        target_temp=165,
        grill_temp=250,
        grill_set_temp=250,
        ambient_temp=70,
        probe_id="test4"
    )
    if prediction:
        print(f"Result: {predictor.format_prediction(prediction)}")
    
    # Test case 5: Grill not at temperature
    print("\nTest 5: Grill still heating up")
    prediction = predictor.predict(
        current_temp=100,
        target_temp=165,
        grill_temp=180,
        grill_set_temp=250,
        ambient_temp=70,
        probe_id="test5"
    )
    if prediction:
        print(f"Result: {predictor.format_prediction(prediction)}")
    else:
        print("Result: No prediction available (grill not at temp)")


if __name__ == "__main__":
    test_physics_based_prediction()