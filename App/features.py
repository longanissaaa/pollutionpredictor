import pandas as pd
import numpy as np

def prepare_data(df, is_training=True, historical_values=None, mode="sprinter"):
    df = df.copy()
    
    # 1. Clean up timestamp logic (No longer relies on 'dt')
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    elif 'dt' in df.columns:
        df['timestamp'] = pd.to_datetime(df['dt'], unit='s')
        
    # 2. Prevent Cartesian Explosions from overlapping API data
    if is_training:
        df = df.drop_duplicates(subset=['city', 'timestamp'])
    
    # SHARED FEATURE ENGINEERING
    df['month'] = df['timestamp'].dt.month
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    
    rads = np.radians(df['wind_direction'])
    df['wind_x'] = df['wind_speed'] * np.cos(rads)
    df['wind_y'] = df['wind_speed'] * np.sin(rads)
    
    if is_training:
        df = df.sort_values(['city', 'timestamp'])
        df['rain_diff'] = df.groupby('city')['precipitation'].diff().fillna(0)
    else:
        df['rain_diff'] = df['precipitation']
        
    df['rain_washout'] = (df['rain_diff'] > 0).astype(int)
    df['stagnation_idx'] = df['temp'] / (df['wind_speed'] + 0.5)

    # TIME-AWARE ANCHORS
    if is_training:
        lag_df = df[['city', 'timestamp', 'pm2_5']].copy()
        lag_df['timestamp'] = lag_df['timestamp'] + pd.Timedelta(hours=24)
        lag_df.rename(columns={'pm2_5': 'pm25_lag_24'}, inplace=True)
        df = df.merge(lag_df, on=['city', 'timestamp'], how='left')
    else:
        df['pm25_lag_24'] = historical_values['lag_24']

    # MODE-SPECIFIC LOGIC
    if mode == "sprinter":
        if is_training:
            rolling_series = df.set_index('timestamp').groupby('city')['pm2_5'].rolling('3h', closed='left').mean()
            rolling_df = rolling_series.reset_index(name='pm25_rolling_3h')
            
            df = df.merge(rolling_df, on=['city', 'timestamp'], how='left')
            df = df.dropna(subset=['pm25_lag_24', 'pm25_rolling_3h'])
        else:
            df['pm25_rolling_3h'] = historical_values['rolling_3h']
            
        feature_cols = [
            'temp',
            'humidity',
            'wind_speed',
            'precipitation',
            'wind_x',
            'wind_y', 
            'rain_washout',
            'stagnation_idx',
            'month',
            'hour',
            'day_of_week', 
            'pm25_lag_24',
            'pm25_rolling_3h'
        ]
    else:
        if is_training:
            df = df.dropna(subset=['pm25_lag_24'])
            
        feature_cols = [
            'temp',
            'humidity',
            'wind_speed',
            'precipitation',
            'wind_x',
            'wind_y', 
            'rain_washout',
            'stagnation_idx',
            'month',
            'hour',
            'day_of_week', 
            'pm25_lag_24'
        ]

    if is_training:
        return df[feature_cols], df['pm2_5']
    return df[feature_cols]
