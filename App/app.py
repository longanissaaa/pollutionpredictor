import os
import time
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify 
from datetime import datetime, timezone
import json
import joblib
import pandas as pd
import numpy as np 
from Service import AirService

load_dotenv()

model = joblib.load('model.pkl')
instance = AirService()

app = Flask(__name__)

app_cache = {
    "timestamp": 0,
    "data": []
}

HEALTH_RECS = {
    1: {"color": "#28a745", "bg": "#eafaf1", "exercise": "Enjoy outdoor exercise", "window": "Open windows for fresh air", "mask": "No mask needed", "purifier": "Purifier not required", "status": "EXCELLENT", "desc": "Perfect conditions. Safe for all outdoor activities."},
    2: {"color": "#ffc107", "bg": "#fff9e6", "exercise": "Outdoor exercise is fine", "window": "Keep windows open", "mask": "Mask only if sensitive", "purifier": "Purifier optional", "status": "FAIR", "desc": "Generally acceptable. Sensitive groups should monitor symptoms."},
    3: {"color": "#fd7e14", "bg": "#fff2e6", "exercise": "Reduce intense outdoor exercise", "window": "Close windows near traffic", "mask": "Wear a mask if sensitive", "purifier": "Consider running a purifier", "status": "MODERATE", "desc": "Wear a mask near traffic. Sensitive groups should stay indoors."},
    4: {"color": "#dc3545", "bg": "#fdf2f2", "exercise": "Avoid outdoor exercise", "window": "Close windows to avoid dirty air", "mask": "Wear a mask outdoors", "purifier": "Run an air purifier", "status": "POOR", "desc": "Avoid prolonged outdoor exertion. Wear an N95 mask."},
    5: {"color": "#6f42c1", "bg": "#f5f0ff", "exercise": "Strictly avoid outdoors", "window": "Seal all windows tightly", "mask": "N95 mask mandatory", "purifier": "Run purifier on max", "status": "HAZARDOUS", "desc": "Emergency. Stay indoors with windows closed."}
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/live-data", methods=["GET"])
def live_data():
    global app_cache
    
    # If we fetched data less than 5 minutes ago, return the cached data to save API calls
    if time.time() - app_cache["timestamp"] < 300 and len(app_cache["data"]) > 0:
        return jsonify(app_cache["data"])

    # THE FIX: Hardcoded GPS coordinates for all 16 cities. 
    # They will never fail to load now.
    NCR_COORDS = {
        "Caloocan": (14.6504, 120.9715),
        "Las Piñas": (14.4445, 120.9939),
        "Makati City": (14.5547, 121.0244),
        "Malabon City": (14.6628, 120.9573),
        "Mandaluyong City": (14.5794, 121.0359),
        "Manila": (14.5995, 120.9842),
        "Marikina City": (14.6507, 121.1029),
        "Muntinlupa City": (14.4081, 121.0415),
        "Navotas City": (14.6715, 120.9436),
        "Parañaque City": (14.4793, 121.0198),
        "Pasay City": (14.5378, 121.0014),
        "Pasig City": (14.5764, 121.0851),
        "Quezon City": (14.6760, 121.0437),
        "San Juan City": (14.6042, 121.0300),
        "Taguig City": (14.5176, 121.0509),
        "Valenzuela City": (14.7011, 120.9830)
    }
    
    all_city_data = []
    current_time_str = datetime.now().strftime("%I:%M %p")
    
    # Loop through our dictionary instead of asking the API for coordinates
    for city_name, (lat, lon) in NCR_COORDS.items():
        
        # We skip get_coords() entirely and go straight to getting the weather!
        raw_pollution = instance.get_data(lat, lon)
        weather_stats = instance.get_weather_stats(lat, lon)
        
        if raw_pollution and 'list' in raw_pollution:
            pollution_info = raw_pollution['list'][0]
            components = pollution_info['components']
            current_aqi = pollution_info['main']['aqi']
            
            # Primary Pollutant
            thresholds = {'pm2_5': 25, 'pm10': 50, 'no2': 25, 'o3': 100}
            worst_key = max(['pm2_5', 'pm10', 'no2', 'o3'], key=lambda k: components.get(k, 0) / thresholds[k])
            names = {'pm2_5': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO₂', 'o3': 'O₃'}
            
            # Trend Calculation
            trend, trend_icon = "stable", "→"
            try:
                if os.path.exists("pollution_data.csv"):
                    df = pd.read_csv("pollution_data.csv")
                    city_history = df[df['city'] == city_name].sort_values('timestamp', ascending=False)
                    if not city_history.empty:
                        last_aqi = int(city_history.iloc[0]['aqi'])
                        if current_aqi < last_aqi: trend, trend_icon = "improving", "↓"
                        elif current_aqi > last_aqi: trend, trend_icon = "worsening", "↑"
            except: pass

            # Save to CSV
            instance.log_to_csv(raw_pollution, weather_stats, city_name)

            city_payload = {
                "name": city_name,
                "lat": lat, "lon": lon,
                "temp": weather_stats.get('temp', '--'),
                "humidity": weather_stats.get('humidity', '--'),
                "wind_speed": weather_stats.get('wind_speed', '--'),
                "wind_direction": weather_stats.get('wind_direction', 0),
                "precipitation": weather_stats.get('precipitation', 0),
                "aqi": current_aqi,
                "pm25": components.get('pm2_5', 0),
                "pm10": components.get('pm10', 0),
                "no2": components.get('no2', 0),
                "o3": components.get('o3', 0),
                "primary_pollutant": names[worst_key],
                "trend": trend,
                "trend_icon": trend_icon,
                "timestamp": current_time_str,
                "health": HEALTH_RECS.get(current_aqi, HEALTH_RECS[4])
            }
            all_city_data.append(city_payload)

    # Update cache
    app_cache["timestamp"] = time.time()
    app_cache["data"] = all_city_data
    
    return jsonify(all_city_data)

# ==========================================
# ROUTE 2: The Prediction (Unchanged)
# ==========================================
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    city = data.get("city")
    lat, lon, official_name = instance.get_coords(city)
    if not lat: return jsonify({"error": "City not found"}), 400
    
    try:
        history_df = pd.read_csv("pollution_data.csv")
        city_history = history_df[history_df['city'] == official_name].sort_values('timestamp')
        lag_24_value = float(city_history.iloc[-24]['pm2_5']) if len(city_history) >= 24 else float(city_history.iloc[0]['pm2_5'])
        rolling_buffer = city_history.tail(3)['pm2_5'].astype(float).tolist()
        while len(rolling_buffer) < 3: rolling_buffer.insert(0, 10.0)
        current_pm25 = rolling_buffer[-1]
    except:
        lag_24_value, rolling_buffer, current_pm25 = 10.0, [10.0]*3, 10.0

    raw_future_weather = instance.get_weather_forecast(lat, lon)
    weather_rows = []
    current_time_utc = int(datetime.now(timezone.utc).timestamp())
    
    for item in raw_future_weather:
        if item['dt'] >= current_time_utc:
            local_time = pd.to_datetime(item['dt'], unit='s') + pd.Timedelta(hours=8)
            weather_rows.append({
                'timestamp': local_time, 'temp': item['temp'], 'humidity': item['humidity'],      
                'wind_speed': item['wind_speed'], 'precipitation': item.get('precipitation', 0),
                'wind_direction': item.get('wind_direction', 0)   
            })
            if len(weather_rows) == 24: break
                
    future_weather = pd.DataFrame(weather_rows)
    my_model_forecast, forecast_labels = [], []

    for i in range(len(future_weather)):
        weather_row = future_weather.iloc[i]
        current_rolling_mean = np.mean(rolling_buffer)
        
        X_input = pd.DataFrame([{
            'temp': weather_row['temp'], 'humidity': weather_row['humidity'],
            'wind_speed': weather_row['wind_speed'], 'precipitation': weather_row['precipitation'],
            "wind_direction" : weather_row["wind_direction"], 'month': weather_row['timestamp'].month,
            'hour': weather_row['timestamp'].hour, 'day_of_week': weather_row['timestamp'].dayofweek,
            'pm25_lag_24': lag_24_value, 'pm25_rolling_3h': current_rolling_mean
        }])
        
        predicted_change = model.predict(X_input)[0]
        new_pm25 = max(0, current_pm25 + predicted_change) 
        
        my_model_forecast.append(round(float(new_pm25), 2))
        forecast_labels.append(int(weather_row['timestamp'].timestamp() * 1000))
        
        current_pm25 = new_pm25
        rolling_buffer.pop(0)
        rolling_buffer.append(new_pm25)

    return jsonify({'prediction': my_model_forecast[0], 'chart_data': {'labels': forecast_labels, 'pm25': my_model_forecast}})

if __name__ == "__main__":
    app.run(debug=True)