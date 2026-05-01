import os
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



# ==========================================
# ROUTE 1: The Dashboard (Current Data)
# ==========================================
@app.route("/", methods=["GET", "POST"])
def home():
    current_time = datetime.now().strftime("%I:%M %p")
    ncr_cities = [
        "Caloocan", "Las Piñas", "Makati City", "Malabon City", "Mandaluyong City", 
        "Manila", "Marikina City", "Muntinlupa City", "Navotas City", "Parañaque City", 
        "Pasay City", "Pasig City", "Quezon City", "San Juan City", "Taguig City", "Valenzuela City"
    ]
    
    current_weather = None
    selected_city = None
    
    if request.method == "POST":
        selected_city = request.form.get("city_selection")
        lat, lon, official_name = instance.get_coords(selected_city)
        
        if lat:
            raw_pollution = instance.get_data(lat, lon) 
            weather_stats = instance.get_weather_stats(lat, lon) 
            
            if raw_pollution and 'list' in raw_pollution:
                pollution_info = raw_pollution['list'][0]
                weather_stats['aqi'] = pollution_info['main']['aqi']
                weather_stats['components'] = pollution_info['components'] 
                components = pollution_info['components']
                current_aqi = pollution_info['main']['aqi']
                
                thresholds = {'pm2_5': 25, 'pm10': 50, 'no2': 25, 'o3': 100}
                
                worst_key = max(['pm2_5', 'pm10', 'no2', 'o3'], 
                                key=lambda k: components.get(k, 0) / thresholds[k])
                
                names = {'pm2_5': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO₂', 'o3': 'O₃'}
                weather_stats['primary_pollutant'] = names[worst_key]
                
                trend = "stable"
                trend_icon = "→"
                try:
                    df = pd.read_csv("pollution_data.csv")
                    city_history = df[df['city'] == official_name].sort_values('timestamp', ascending=False)
                    
                    if not city_history.empty:
                        last_hour_aqi = int(city_history.iloc[0]['aqi'])
                        
                        if current_aqi < last_hour_aqi:
                            trend = "improving"
                            trend_icon = "↓"
                        elif current_aqi > last_hour_aqi:
                            trend = "worsening"
                            trend_icon = "↑"
                except Exception as e:
                    print(f"Trend error: {e}")
                
                weather_stats['trend'] = trend
                weather_stats['trend_icon'] = trend_icon
                
            current_weather = weather_stats
            weather_stats['timestamp'] = current_time
            current_weather['city'] = official_name

            if raw_pollution and 'list' in raw_pollution:
                instance.log_to_csv(raw_pollution, weather_stats, official_name)

    return render_template("index.html", 
                           cities=ncr_cities, 
                           current=current_weather, 
                           selected_city=selected_city,current_time = current_time)

# ==========================================
# ROUTE 2: The Prediction (Historical Data)
# ==========================================

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    city = data.get("city")
    
    lat, lon, official_name = instance.get_coords(city)
    if not lat:
        return jsonify({"error": "City not found"}), 400
    
    try:
        history_df = pd.read_csv("pollution_data.csv")
        city_history = history_df[history_df['city'] == official_name].sort_values('timestamp')
        
        if len(city_history) >= 24:
            lag_24_value = float(city_history.iloc[-24]['pm2_5'])
        else:
            lag_24_value = float(city_history.iloc[0]['pm2_5'])
            
        rolling_buffer = city_history.tail(3)['pm2_5'].astype(float).tolist()
        while len(rolling_buffer) < 3:
            rolling_buffer.insert(0, 10.0) 
        current_pm25 = rolling_buffer[-1]
        
    except Exception as e:
        print(f"Warning: Could not load history for {official_name}: {e}")
        lag_24_value = 10.0 
        rolling_buffer = [10.0] * 3
        current_pm25 = 10.0

    # 2. Get Future Weather
    raw_future_weather = instance.get_weather_forecast(lat, lon)
    if not raw_future_weather:
        return jsonify({"error": "Error fetching future weather"}), 500

    weather_rows = []
    current_time_utc = int(datetime.now(timezone.utc).timestamp())
    
    for item in raw_future_weather:
        if item['dt'] >= current_time_utc:
            local_time = pd.to_datetime(item['dt'], unit='s') + pd.Timedelta(hours=8)
            weather_rows.append({
                'timestamp': local_time,
                'temp': item['temp'],              
                'humidity': item['humidity'],      
                'wind_speed': item['wind_speed'],
                'precipitation': item.get('precipitation', 0),
                'wind_direction': item.get('wind_direction', 0)   
            })
            if len(weather_rows) == 24: 
                break
                
    future_weather = pd.DataFrame(weather_rows)

    my_model_forecast = []
    forecast_labels = []

    for i in range(len(future_weather)):
        weather_row = future_weather.iloc[i]
        current_rolling_mean = np.mean(rolling_buffer)
        
        X_input = pd.DataFrame([{
            'temp': weather_row['temp'],
            'humidity': weather_row['humidity'],
            'wind_speed': weather_row['wind_speed'],
            'precipitation': weather_row['precipitation'],
            "wind_direction" : weather_row["wind_direction"],
            'month': weather_row['timestamp'].month,
            'hour': weather_row['timestamp'].hour,
            'day_of_week': weather_row['timestamp'].dayofweek,
            'pm25_lag_24': lag_24_value,
            'pm25_rolling_3h': current_rolling_mean
        }])
        
        predicted_change = model.predict(X_input)[0]
        new_pm25 = max(0, current_pm25 + predicted_change) 
        
        my_model_forecast.append(round(float(new_pm25), 2))
        forecast_labels.append(int(weather_row['timestamp'].timestamp() * 1000))
        
        current_pm25 = new_pm25
        rolling_buffer.pop(0)
        rolling_buffer.append(new_pm25)

    return jsonify({
        'prediction': my_model_forecast[0],
        'chart_data': {
            'labels': forecast_labels,
            'pm25': my_model_forecast
        }
    })

if __name__ == "__main__":
    app.run(debug=True)