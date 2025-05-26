"""Train the temperature prediction model on historical data."""

import asyncio
from pathlib import Path
import pandas as pd
from analyze_temperature_data import extract_probe_data, extract_features_for_ml
from traeger_client.temperature_predictor import TemperaturePredictor


async def main():
    """Train the temperature prediction model."""
    db_path = Path("./data/traeger_data.db")
    
    print("Step 1: Extracting probe data from database...")
    df = extract_probe_data(db_path)
    print(f"Found {len(df)} raw data points")
    
    if len(df) == 0:
        print("No data found in database. Cannot train model.")
        return
    
    print("\nStep 2: Extracting features for ML training...")
    features_df = extract_features_for_ml(df)
    print(f"Extracted {len(features_df)} training samples")
    
    if len(features_df) < 50:
        print(f"Warning: Only {len(features_df)} samples available. Model may not be accurate.")
        print("Collect more data by running the Traeger for longer periods.")
    
    if len(features_df) > 0:
        print("\nStep 3: Training temperature prediction model...")
        predictor = TemperaturePredictor()
        
        # Add engineered features that aren't in the raw data
        features_df['temp_rate_avg'] = features_df['temp_rate']  # Will be calculated dynamically in production
        features_df['grill_temp_diff'] = features_df['grill_set_temp'] - features_df['grill_temp']
        features_df['temp_progress'] = (
            (features_df['current_temp'] - features_df['ambient_temp']) / 
            (features_df['target_temp'] - features_df['ambient_temp'])
        ).fillna(0)
        
        metrics = predictor.train(features_df)
        
        print("\nTraining Results:")
        print(f"Model Type: {metrics['model_type']}")
        print(f"Samples: {metrics['samples_trained']} training, {metrics['samples_tested']} testing")
        print(f"Mean Absolute Error: {metrics['mae_minutes']:.1f} minutes")
        print(f"R² Score: {metrics['r2_score']:.3f}")
        
        if metrics['r2_score'] < 0.5:
            print("\nWarning: Model accuracy is low. This could be due to:")
            print("- Insufficient training data")
            print("- High variability in cooking conditions")
            print("- Missing important features")
        else:
            print("\nModel trained successfully!")
            
        # Test the model with a sample prediction
        print("\nTesting model with sample data:")
        prediction = predictor.predict(
            current_temp=150,
            target_temp=205,
            grill_temp=250,
            grill_set_temp=250,
            ambient_temp=70,
            probe_id="test"
        )
        
        if prediction:
            print(f"Sample prediction: {predictor.format_prediction(prediction)}")
        else:
            print("Could not generate sample prediction")
    else:
        print("No valid training samples extracted. Check your data.")


if __name__ == "__main__":
    asyncio.run(main())