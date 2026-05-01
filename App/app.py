import os
import time
import csv
import concurrent.futures
from datetime import datetime,timezone
import pandas as pd
from flask import Flask, render_template, request, jsonify 
import joblib
import numpy as np 
from dotenv import load_dotenv
from Service import AirService

# ==========================================
# 1. INITIALIZATION & GLOBALS
# ==========================================
load_dotenv()

model_sprinter = joblib.load('model_sprinter.pkl')
model_marathoner = joblib.load('model_marathoner.pkl')
instance = AirService() # <-- Defined here!

app = Flask(__name__)

app_cache = {
    "timestamp": 0,
    "data": []
}

HEALTH_RECS = { # <-- Defined here!
    1: {"color": "#28a745", "bg": "#eafaf1", "exercise": "Enjoy outdoor exercise", "window": "Open windows for fresh air", "mask": "No mask needed", "purifier": "Purifier not required", "status": "EXCELLENT", "desc": "Perfect conditions. Safe for all outdoor activities."},
    2: {"color": "#ffc107", "bg": "#fff9e6", "exercise": "Outdoor exercise is fine", "window": "Keep windows open", "mask": "Mask only if sensitive", "purifier": "Purifier optional", "status": "FAIR", "desc": "Generally acceptable. Sensitive groups should monitor symptoms."},
    3: {"color": "#fd7e14", "bg": "#fff2e6", "exercise": "Reduce intense outdoor exercise", "window": "Close windows near traffic", "mask": "Wear a mask if sensitive", "purifier": "Consider running a purifier", "status": "MODERATE", "desc": "Wear a mask near traffic. Sensitive groups should stay indoors."},
    4: {"color": "#dc3545", "bg": "#fdf2f2", "exercise": "Avoid outdoor exercise", "window": "Close windows to avoid dirty air", "mask": "Wear a mask outdoors", "purifier": "Run an air purifier", "status": "POOR", "desc": "Avoid prolonged outdoor exertion. Wear an N95 mask."},
    5: {"color": "#6f42c1", "bg": "#f5f0ff", "exercise": "Strictly avoid outdoors", "window": "Seal all windows tightly", "mask": "N95 mask mandatory", "purifier": "Run purifier on max", "status": "HAZARDOUS", "desc": "Emergency. Stay indoors with windows closed."}
}

NCR_COORDS = {
    "Caloocan": (14.6504, 120.9715), "Las Piñas": (14.4445, 120.9939),
    "Makati City": (14.5547, 121.0244), "Malabon City": (14.6628, 120.9573),
    "Mandaluyong City": (14.5794, 121.0359), "Manila": (14.5995, 120.9842),
    "Marikina City": (14.6507, 121.1029), "Muntinlupa City": (14.4081, 121.0415),
    "Navotas City": (14.6715, 120.9436), "Parañaque City": (14.4793, 121.0198),
    "Pasay City": (14.5378, 121.0014), "Pasig City": (14.5764, 121.0851),
    "Quezon City": (14.6760, 121.0437), "San Juan City": (14.6042, 121.0300),
    "Taguig City": (14.5176, 121.0509), "Valenzuela City": (14.7011, 120.9830)
}

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def precalculate_history_and_trends():
    empty_state = {p: ["--", "--"] for p in ['pm2_5', 'pm10', 'no2', 'o3']}
    result = {city: {"history": empty_state, "last_aqi": None} for city in NCR_COORDS.keys()}
    
    if not os.path.exists("pollution_data.csv"):
        return result

    try:
        df = pd.read_csv("pollution_data.csv")
        if df.empty: return result
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        now = datetime.now()
        week_ago = now - pd.Timedelta(days=7)
        month_ago = now - pd.Timedelta(days=30)
        
        for city_name in NCR_COORDS.keys():
            city_df = df[df['city'] == city_name]
            if city_df.empty: continue
            
            city_df_sorted = city_df.sort_values('timestamp', ascending=False)
            if not pd.isna(city_df_sorted.iloc[0]['aqi']):
                result[city_name]["last_aqi"] = int(city_df_sorted.iloc[0]['aqi'])

            history = {}
            for pol in ['pm2_5', 'pm10', 'no2', 'o3']:
                if pol in city_df.columns:
                    numeric_data = pd.to_numeric(city_df[pol], errors='coerce')
                    w_avg = numeric_data[city_df['timestamp'] > week_ago].mean()
                    m_avg = numeric_data[city_df['timestamp'] > month_ago].mean()
                    
                    history[pol] = [
                        round(float(w_avg), 1) if pd.notnull(w_avg) else "--",
                        round(float(m_avg), 1) if pd.notnull(m_avg) else "--"
                    ]
                else:
                    history[pol] = ["--", "--"]
            result[city_name]["history"] = history
            
    except Exception as e:
        print(f"History Precalc Error: {e}")
        
    return result

def bulk_log_to_csv(rows):
    file_path = "pollution_data.csv"
    file_exist = os.path.isfile(file_path)
    fieldnames = ['timestamp', 'city', 'aqi', 'pm2_5', 'pm10', 'temp', 'humidity', 'wind_speed', "no2", "o3"]
    
    try:
        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exist:
                writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print(f"Error bulk logging: {e}")

# ==========================================
# 3. ROUTES
# ==========================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/live-data", methods=["GET"])
def live_data():
    global app_cache
    
    if time.time() - app_cache["timestamp"] < 300 and len(app_cache["data"]) > 0:
        return jsonify(app_cache["data"])

    current_time_str = datetime.now().strftime("%I:%M %p")
    history_data_store = precalculate_history_and_trends()
    
    all_city_data = []
    rows_to_log = []

    def fetch_city_data(city_info):
        city_name, (lat, lon) = city_info
        
        raw_pollution = instance.get_data(lat, lon)
        weather_stats = instance.get_weather_stats(lat, lon)
        
        if not raw_pollution or 'list' not in raw_pollution:
            return None, None
            
        pollution_info = raw_pollution['list'][0]
        components = pollution_info['components']
        current_aqi = pollution_info['main']['aqi']
        
        thresholds = {'pm2_5': 25, 'pm10': 50, 'no2': 25, 'o3': 100}
        worst_key = max(['pm2_5', 'pm10', 'no2', 'o3'], key=lambda k: components.get(k, 0) / thresholds[k])
        names = {'pm2_5': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO₂', 'o3': 'O₃'}
        
        city_hist = history_data_store.get(city_name, {})
        last_aqi = city_hist.get("last_aqi")
        trend, trend_icon = "stable", "→"
        
        if last_aqi is not None:
            if current_aqi < last_aqi: trend, trend_icon = "improving", "↓"
            elif current_aqi > last_aqi: trend, trend_icon = "worsening", "↑"

        city_payload = {
            "name": city_name, "lat": lat, "lon": lon,
            "temp": weather_stats.get('temp', '--') if weather_stats else '--',
            "humidity": weather_stats.get('humidity', '--') if weather_stats else '--',
            "wind_speed": weather_stats.get('wind_speed', '--') if weather_stats else '--',
            "wind_direction": weather_stats.get('wind_direction', 0) if weather_stats else 0,
            "precipitation": weather_stats.get('precipitation', 0) if weather_stats else 0,
            "aqi": current_aqi,
            "pm25": components.get('pm2_5', 0), "pm10": components.get('pm10', 0),
            "no2": components.get('no2', 0), "o3": components.get('o3', 0),
            "primary_pollutant": names[worst_key],
            "trend": trend, "trend_icon": trend_icon,
            "timestamp": current_time_str,
            "health": HEALTH_RECS.get(current_aqi, HEALTH_RECS[4]),
            "history": city_hist.get("history", {p: ["--", "--"] for p in ['pm2_5', 'pm10', 'no2', 'o3']})
        }
        
        log_row = {
            'timestamp': datetime.fromtimestamp(pollution_info.get('dt')).strftime('%Y-%m-%d %H:%M:%S'),
            'city': city_name, 'aqi': current_aqi,
            'pm2_5': components.get('pm2_5'), 'pm10': components.get('pm10'),
            'temp': weather_stats.get('temp') if weather_stats else None,
            'humidity': weather_stats.get('humidity') if weather_stats else None,
            'wind_speed': weather_stats.get('wind_speed') if weather_stats else None,
            'no2': components.get('no2'), 'o3': components.get('o3'),
        }
        
        return city_payload, log_row

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(fetch_city_data, NCR_COORDS.items())
        
        for payload, log_row in results:
            if payload: all_city_data.append(payload)
            if log_row: rows_to_log.append(log_row)

    if rows_to_log:
        bulk_log_to_csv(rows_to_log)

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
    
    # 1. STABLE COORDINATE LOOKUP
    # We ignore the Geo API and use your hardcoded NCR_COORDS to prevent 400 errors
    if city in NCR_COORDS:
        lat, lon = NCR_COORDS[city]
        official_name = city
    else:
        return jsonify({"error": f"City '{city}' not recognized"}), 400
    
    # 2. DATA ANCHORING (Lag & Rolling Buffer)
    try:
        if not os.path.exists("pollution_data.csv"):
            # Fallback if no file exists yet
            lag_24_value, rolling_buffer = 10.0, [10.0]*3
        else:
            history_df = pd.read_csv("pollution_data.csv")
            city_history = history_df[history_df['city'] == official_name].copy()
            
            if not city_history.empty:
                city_history['timestamp'] = pd.to_datetime(city_history['timestamp'])
                city_history = city_history.sort_values('timestamp')
                
                # Find anchor exactly 24 hours ago
                most_recent_time = city_history['timestamp'].iloc[-1]
                target_time = most_recent_time - pd.Timedelta(hours=24)
                closest_idx = (city_history['timestamp'] - target_time).abs().idxmin()
                lag_24_value = float(city_history.loc[closest_idx]['pm2_5'])
                
                rolling_buffer = city_history.tail(3)['pm2_5'].astype(float).tolist()
                while len(rolling_buffer) < 3: 
                    rolling_buffer.insert(0, lag_24_value)
            else:
                lag_24_value, rolling_buffer = 10.0, [10.0]*3

    except Exception as e:
        print(f"Prediction Data Error: {e}")
        lag_24_value, rolling_buffer = 10.0, [10.0]*3
        
    # 3. WEATHER FORECAST
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

    # 4. DUAL-MODEL TELESCOPING LOOP
    for i in range(len(future_weather)):
        weather_row = future_weather.iloc[i]
        
        # Feature Engineering (Must match features.py exactly)
        rads = np.radians(weather_row['wind_direction'])
        w_x = weather_row['wind_speed'] * np.cos(rads)
        w_y = weather_row['wind_speed'] * np.sin(rads)
        stagnation = weather_row['temp'] / (weather_row['wind_speed'] + 0.5)
        
        prev_p = future_weather.iloc[i-1]['precipitation'] if i > 0 else weather_row['precipitation']
        washout = 1 if (weather_row['precipitation'] - prev_p) > 0 else 0

        # Model Selection
        if i < 6:
            # SPRINTER (Hours 1-6)
            X_input = pd.DataFrame([{
                'temp': weather_row['temp'], 'humidity': weather_row['humidity'],
                'wind_speed': weather_row['wind_speed'], 'precipitation': weather_row['precipitation'],
                'wind_x': w_x, 'wind_y': w_y, 'rain_washout': washout, 'stagnation_idx': stagnation,
                'month': weather_row['timestamp'].month, 'hour': weather_row['timestamp'].hour, 
                'day_of_week': weather_row['timestamp'].dayofweek,
                'pm25_lag_24': lag_24_value, 
                'pm25_rolling_3h': np.mean(rolling_buffer)
            }])
            pred = model_sprinter.predict(X_input)[0]
        else:
            # MARATHONER (Hours 7-24)
            X_input = pd.DataFrame([{
                'temp': weather_row['temp'], 'humidity': weather_row['humidity'],
                'wind_speed': weather_row['wind_speed'], 'precipitation': weather_row['precipitation'],
                'wind_x': w_x, 'wind_y': w_y, 'rain_washout': washout, 'stagnation_idx': stagnation,
                'month': weather_row['timestamp'].month, 'hour': weather_row['timestamp'].hour, 
                'day_of_week': weather_row['timestamp'].dayofweek,
                'pm25_lag_24': lag_24_value
            }])
            pred = model_marathoner.predict(X_input)[0]

        val = max(0, pred)
        my_model_forecast.append(round(float(val), 2))
        forecast_labels.append(int(weather_row['timestamp'].timestamp() * 1000))
        
        # Update rolling buffer
        rolling_buffer.pop(0)
        rolling_buffer.append(val)
        
   # 1. Capture the specific weather row for the predicted peak
    max_val = max(my_model_forecast)
    max_idx = my_model_forecast.index(max_val)

    peak_hour_data = future_weather.iloc[max_idx]
    peak_time = peak_hour_data['timestamp'].strftime('%I:%M %p')

    # 2. Explainable AI Logic: Identify the "Driver"
    # Re-calculating the stagnation formula used in your loop
    stagnation_val = peak_hour_data['temp'] / (peak_hour_data['wind_speed'] + 0.5)
    is_raining = peak_hour_data['precipitation'] > 0
    hr = peak_hour_data['timestamp'].hour

    if is_raining:
        driver_msg = "Rain Washout (Clearing Air)"
    elif stagnation_val > 15:
        driver_msg = "Stagnant Air (Low Wind/High Heat)"
    elif hr in [7, 8, 9, 17, 18, 19]:
        driver_msg = "Peak Traffic Volume"
    else:
        driver_msg = "Standard Urban Emissions"

    # 3. Determine Alert Level
    if max_val > 55: alert_lvl, status = 4, "POOR"
    elif max_val > 35: alert_lvl, status = 3, "MODERATE"
    elif max_val > 12: alert_lvl, status = 2, "FAIR"
    else: alert_lvl, status = 1, "EXCELLENT"

    # Generate the human-readable alert using the new peak_time[cite: 6]
    if alert_lvl >= 3:
        prediction_alert = f"⚠️ Warning: {status} levels expected around {peak_time}. Consider rescheduling outdoor tasks."
    else:
        prediction_alert = f"✅ Optimal: Air quality is expected to remain {status} for the next 24 hours."

    return jsonify({
        'prediction': my_model_forecast[0],
        'alert_msg': prediction_alert,
        'alert_color': HEALTH_RECS[alert_lvl]['color'],
        'reason': driver_msg, # <--- NEW: Send driver to frontend[cite: 6]
        'chart_data': {'labels': forecast_labels, 'pm25': my_model_forecast}
    })

if __name__ == "__main__":
    app.run(debug=True)