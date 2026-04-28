import pandas as pd

def prepare_data(df, is_training=True, historical_values=None):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['dt'], unit='s')
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    
    if is_training:
        df = df.sort_values(['city', 'dt'])
        df['pm25_lag_24'] = df.groupby('city')['pm2_5'].shift(24)
        
        df['pm25_rolling_3h'] = df.groupby('city')['pm2_5'].transform(
            lambda x: x.shift(1).rolling(window=3).mean()
        )
        
        df['pm25_change'] = df.groupby('city')['pm2_5'].diff()
        
        df = df.dropna(subset=['pm25_lag_24', 'pm25_rolling_3h', 'pm25_change'])
    else:
        df['pm25_lag_24'] = historical_values['lag_24']
        df['pm25_rolling_3h'] = historical_values['rolling_3h']
    
    feature_cols = ['temp', 'humidity', 'wind_speed', 'hour', 'day_of_week', 
                    'pm25_lag_24', 'pm25_rolling_3h']
    
    if is_training:
        # We return pm25_change instead of pm2_5
        return df[feature_cols], df['pm25_change'] 
    
    return df[feature_cols]