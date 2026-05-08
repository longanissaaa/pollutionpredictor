import pandas as pd
import numpy as np

def prepare_data(df, is_training=True, historical_values=None, mode="sprinter"):
    df = df.copy()
    
    # 1. SHARED FEATURE ENGINEERING
    df['timestamp'] = pd.to_datetime(df['dt'], unit='s')
    df['month'] = df['timestamp'].dt.month
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    
    rads = np.radians(df['wind_direction'])
    df['wind_x'] = df['wind_speed'] * np.cos(rads)
    df['wind_y'] = df['wind_speed'] * np.sin(rads)
    
    if is_training:
        df['rain_diff'] = df.groupby('city')['precipitation'].diff().fillna(0)
    else:
        df['rain_diff'] = df['precipitation']
    df['rain_washout'] = (df['rain_diff'] > 0).astype(int)
    df['stagnation_idx'] = df['temp'] / (df['wind_speed'] + 0.5)

    # 2. THE ANCHOR (pm25_lag_24) - Calculated for BOTH models
    if is_training:
        df = df.sort_values(['city', 'dt'])
        df['pm25_lag_24'] = df.groupby('city')['pm2_5'].shift(24)
    else:
        df['pm25_lag_24'] = historical_values['lag_24']

    # 3. MODE-SPECIFIC LOGIC
    if mode == "sprinter":
        # Sprinter also needs the 3h rolling average
        if is_training:
            df['pm25_rolling_3h'] = df.groupby('city')['pm2_5'].transform(
                lambda x: x.shift(1).rolling(window=3).mean()
            )
            # Remove rows where we couldn't calculate lags/rolling
            df = df.dropna(subset=['pm25_lag_24', 'pm25_rolling_3h'])
        else:
            df['pm25_rolling_3h'] = historical_values['rolling_3h']
            
        feature_cols = [
            'temp', 'humidity', 'wind_speed', 'precipitation', 'wind_x', 'wind_y', 
            'rain_washout', 'stagnation_idx', 'month', 'hour', 'day_of_week', 
            'pm25_lag_24', 'pm25_rolling_3h'
        ]
    else:
        # Marathoner ONLY uses the 24h lag (No rolling average to prevent drift)
        if is_training:
            df = df.dropna(subset=['pm25_lag_24'])
            
        feature_cols = [
            'temp', 'humidity', 'wind_speed', 'precipitation', 'wind_x', 'wind_y', 
            'rain_washout', 'stagnation_idx', 'month', 'hour', 'day_of_week', 
            'pm25_lag_24'
        ]

    if is_training:
        return df[feature_cols], df['pm2_5']
    return df[feature_cols]