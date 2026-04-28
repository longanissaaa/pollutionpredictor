import pandas as pd
import joblib
import numpy as np
import matplotlib.pyplot as plt
import requests

# --- CONFIGURATION ---
API_KEY = "15859dce86f726da3cf21f07f2ac289b"  # Replace with your actual key
LAT, LON = 14.6416, 120.9762 # Caloocan
HOURS_TO_PREDICT = 24

print("Loading model...")
model = joblib.load('model.pkl')

# ==========================================
# STEP 1: Get Official PM2.5 Forecast (Green Line)
# ==========================================
print("Fetching Air Pollution Forecast...")
aqi_url = f"http://api.openweathermap.org/data/2.5/air_pollution/forecast?lat={LAT}&lon={LON}&appid={API_KEY}"
aqi_data = requests.get(aqi_url).json()

# Get the next 24 hours of PM2.5 predictions
api_pm25_forecast = [item['components']['pm2_5'] for item in aqi_data['list'][:HOURS_TO_PREDICT]]

# Setup our model's history buffer using the current actual PM2.5
current_pm25 = api_pm25_forecast[0]
rolling_buffer = [current_pm25] * 3
lag_24_value = current_pm25 

# ==========================================
# STEP 2: Get REAL Future Weather for your Model
# ==========================================
print("Fetching Real Weather Forecast...")
weather_url = f"http://api.openweathermap.org/data/2.5/forecast?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric"
weather_data = requests.get(weather_url).json()

# Extract the 3-hour weather data
weather_rows = []
for item in weather_data['list']:
    weather_rows.append({
        'timestamp': pd.to_datetime(item['dt'], unit='s'),
        'temp': item['main']['temp'],
        'humidity': item['main']['humidity'],
        'wind_speed': item['wind']['speed']
    })

weather_df = pd.DataFrame(weather_rows)
weather_df.set_index('timestamp', inplace=True)

# THE FIX: OpenWeather gives 3-hour steps. We interpolate to 1-hour steps!
hourly_weather = weather_df.resample('1h').interpolate(method='linear').reset_index()

# Take exactly the next 24 hours to match our prediction window
future_weather = hourly_weather.head(HOURS_TO_PREDICT)

# ==========================================
# STEP 3: Run Your Model (Red Line)
# ==========================================
print("Running recursive forecast with REAL weather...")
my_model_forecast = []

for i in range(HOURS_TO_PREDICT):
    weather_row = future_weather.iloc[i]
    current_rolling_mean = np.mean(rolling_buffer)
    
    # Prepare input EXACTLY as the model expects
    X_input = pd.DataFrame([{
        'temp': weather_row['temp'],
        'humidity': weather_row['humidity'],
        'wind_speed': weather_row['wind_speed'],
        'hour': weather_row['timestamp'].hour,
        'day_of_week': weather_row['timestamp'].dayofweek,
        'pm25_lag_24': lag_24_value,
        "pm25_rolling_3h" : current_rolling_mean
    }])
    
    # Predict
    predicted_change = model.predict(X_input)[0]
    
    # Calculate the actual predicted value: Previous Value + Predicted Change
    new_prediction = current_pm25 + predicted_change
    my_model_forecast.append(new_prediction)
    
    # Update for the next loop
    current_pm25 = new_prediction 
    rolling_buffer.pop(0)
    rolling_buffer.append(new_prediction)
# ==========================================
# STEP 4: Visualize
# ==========================================
print("Plotting showdown...")
plt.figure(figsize=(12, 6))

plt.plot(api_pm25_forecast, label='OpenWeather API (Official)', color='green', linestyle='-', linewidth=2, marker='o')
plt.plot(my_model_forecast, label='My Model Forecast', color='red', linestyle='--', linewidth=2, marker='x')

plt.title(f"TRUE LIVE TEST: My Model vs OpenWeather API (Caloocan)")
plt.xlabel("Hours from Right Now")
plt.ylabel("PM2.5 (µg/m³)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.show()