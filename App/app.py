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
from flask_caching import Cache
import pymongo

# ==========================================
# 1. INITIALIZATION & GLOBALS
# ==========================================
load_dotenv()

mongo_uri = os.getenv("MONGO_URI")
mongo_client = pymongo.MongoClient(mongo_uri)
db = mongo_client["air_quality_db"]
collection = db["pollution_data"]


def get_db_dataframe():
    cursor = collection.find({}, {'_id': 0}) 
    data = list(cursor)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

df = get_db_dataframe()
if not df.empty:
    print(df.groupby('city')['timestamp'].max())

model_sprinter = joblib.load('model_sprinter.pkl')
model_marathoner = joblib.load('model_marathoner.pkl')
instance = AirService()

app = Flask(__name__)

cache = Cache(app, config={'CACHE_TYPE': 'FileSystemCache', 'CACHE_DIR': '/tmp'})

HEALTH_RECS = { 
    1: {"color": "#28a745", "bg": "#eafaf1", "status": "GOOD", "desc": "Perfect conditions. Safe for all outdoor activities.", 
        "exercise": "Enjoy outdoor exercise", "window": "Open windows for fresh air", "mask": "No mask needed", "purifier": "Not required"},
    
    2: {"color": "#ffc107", "bg": "#fff9e6", "status": "MODERATE", "desc": "Generally acceptable. Sensitive groups should monitor symptoms.", 
        "exercise": "Outdoor exercise is fine", "window": "Keep windows open", "mask": "Mask only if sensitive", "purifier": "Optional"},
    
    3: {"color": "#fd7e14", "bg": "#fff2e6", "status": "SENSITIVE", "desc": "Sensitive groups should reduce outdoor time.", 
        "exercise": "Reduce intense outdoor exercise", "window": "Close windows near traffic", "mask": "Wear mask if sensitive", "purifier": "Consider a purifier"},
    
    4: {"color": "#dc3545", "bg": "#fdf2e6", "status": "UNHEALTHY", "desc": "Everyone may begin to feel health effects.", 
        "exercise": "Avoid outdoor exercise", "window": "Keep windows closed", "mask": "Wear a mask outdoors", "purifier": "Run a purifier"},
    
    5: {"color": "#6f42c1", "bg": "#f5f0ff", "status": "VERY UNHEALTHY", "desc": "Health warnings for the entire population.", 
        "exercise": "Strictly avoid outdoors", "window": "Seal windows tightly", "mask": "N95 mask mandatory", "purifier": "Run on maximum"},
    
    6: {"color": "#800000", "bg": "#f2d9d9", "status": "HAZARDOUS", "desc": "Emergency condition. Stay indoors and seal all air gaps.", 
        "exercise": "DANGER: Stay inside", "window": "DO NOT open windows", "mask": "N95 mask critical", "purifier": "Run on maximum"}
}

NCR_COORDS = {
    "Caloocan": (14.6504, 120.9715), "Las Piñas": (14.4445, 120.9939),
    "Makati City": (14.5547, 121.0244), "Malabon City": (14.6628, 120.9573),
    "Mandaluyong City": (14.5794, 121.0359), "Manila": (14.5995, 120.9842),
    "Marikina City": (14.6507, 121.1029), "Muntinlupa City": (14.4081, 121.0415),
    "Navotas City": (14.6715, 120.9436), "Parañaque City": (14.4793, 121.0198),
    "Pasay City": (14.5378, 121.0014), "Pasig City": (14.5764, 121.0851),
    "Quezon City": (14.6760, 121.0437), "San Juan City": (14.6042, 121.0300),
    "Taguig City": (14.5176, 121.0509), "Valenzuela City": (14.7011, 120.9830), "Pateros" : (14.5484,121.0708)
}

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def precalculate_history_and_trends():
    empty_state = {p: ["--", "--"] for p in ['pm2_5', 'pm10', 'no2', 'o3']}
    result = {city: {"history": empty_state, "last_aqi": None} for city in NCR_COORDS.keys()}
    
    df = get_db_dataframe()
    if df.empty:
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

def get_historical_baselines(city_name, future_weather_df):
    """
    Safely retrieves PM2.5 data from exactly 24 hours ago and 365 days ago.
    If the data doesn't exist yet, it returns None (null) so the chart doesn't break.
    """
    yesterday_data = [None] * len(future_weather_df)
    last_year_data = [None] * len(future_weather_df)
    
    try:
        history_df = pd.read_csv("pollution_data.csv")
        history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
        
        # 1. ADD THIS PRINT: See what city Python is looking for
        print(f"\n[DEBUG] Searching CSV for exactly: '{city_name}'")
        
        
        city_history = history_df[history_df['city'] == city_name]
        
        if city_history.empty:
            # 2. ADD THIS PRINT: Warn us if it's missing!
            print(f"[DEBUG] WARNING: 0 rows found in CSV for '{city_name}'!")
            return yesterday_data, last_year_data
            
        for i in range(len(future_weather_df)):
            target_time = future_weather_df.iloc[i]['timestamp']
            
            # 1. Calculate the exact target times
            time_yesterday = target_time - pd.Timedelta(hours=24)
            time_last_year = target_time - pd.Timedelta(days=365)
            
            # 2. Find Yesterday's Match
            diff_yest = (city_history['timestamp'] - time_yesterday).abs()
            idx_yest = diff_yest.idxmin()
            if diff_yest[idx_yest] <= pd.Timedelta(hours=2): # Allow a 2-hour window
                yesterday_data[i] = float(city_history.loc[idx_yest]['pm2_5'])
                
            # 3. Find Last Year's Match
            diff_year = (city_history['timestamp'] - time_last_year).abs()
            idx_year = diff_year.idxmin()
            if diff_year[idx_year] <= pd.Timedelta(hours=2):
                last_year_data[i] = float(city_history.loc[idx_year]['pm2_5'])
                
        return yesterday_data, last_year_data

    except Exception as e:
        print(f"Baseline Extraction Error: {e}")
        return yesterday_data, last_year_data

def bulk_log_to_csv(rows):
    try:
        if rows:
            collection.insert_many(rows)
            print(f"Successfully logged {len(rows)} records to MongoDB.")
    except Exception as e:
        print(f"Error bulk logging to MongoDB: {e}")


    

# ==========================================
# 3. ROUTES
# ==========================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/live-data", methods=["GET"])
@cache.cached(timeout=300)
def live_data():
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
        forecast_labels.append(int((weather_row['timestamp'] - pd.Timedelta(hours=8)).timestamp() * 1000))
        
        # Update rolling buffer
        rolling_buffer.pop(0)
        rolling_buffer.append(val)
        
   # 1. Capture the specific weather row for the predicted peak
    max_val = max(my_model_forecast)
    max_idx = my_model_forecast.index(max_val)

    peak_hour_data = future_weather.iloc[max_idx]
    peak_time = peak_hour_data['timestamp'].strftime('%I:%M %p')

    # 2. Explainable AI Logic: Identify the "Driver"
    # Re-calculating the stagnation formula used in your loop``
    stagnation_val = peak_hour_data['temp'] / (peak_hour_data['wind_speed'] + 0.5)
    is_raining = peak_hour_data['precipitation'] > 0
    hr = peak_hour_data['timestamp'].hour
    day_of_week = peak_hour_data['timestamp'].dayofweek # 0 is Monday, 6 is Sunday
    wind_s = peak_hour_data['wind_speed']
    temp = peak_hour_data['temp']
    humidity = peak_hour_data['humidity']

    if is_raining:
        driver_msg = "Rain Washout (Clearing Particulates)"
        
    elif max_val > 40 and wind_s < 1.0 and temp > 33:
        driver_msg = "Extreme Heat Stagnation (Smog Dome Effect)"
        
    elif max_val > 35 and wind_s < 2.0:
        driver_msg = "Severe Stagnation (Zero Wind Dispersion)"
        
    elif stagnation_val > 15 and humidity > 85:
        # High humidity causes PM2.5 to swell and trap closer to the ground
        driver_msg = "Heavy Humid Air (Trapping Particulates)"
        
    elif stagnation_val > 15:
        driver_msg = "Trapped Heat & Low Wind"
        
    elif hr in [7, 8, 9] and day_of_week < 5:
        # Weekday Morning
        driver_msg = "Weekday Morning Commute Exhaust"
        
    elif hr in [17, 18, 19, 20] and day_of_week < 5:
        # Weekday Evening (extended to 8 PM for Manila traffic)
        driver_msg = "Evening Rush Hour & Gridlock Build-up"
        
    elif day_of_week >= 5 and hr in [11, 12, 13, 14, 15]:
        # Weekend Midday
        driver_msg = "Weekend Commercial & Leisure Traffic"
        
    elif hr >= 22 or hr <= 4:
        # Late night / Early morning
        driver_msg = "Nighttime Temperature Inversion (Trapped Surface Air)"
        
    else:
        driver_msg = "Standard Urban Emissions"

    # 3. Determine Alert Level
    if max_val > 55: alert_lvl, status = 4, "POOR"
    elif max_val > 35: alert_lvl, status = 3, "MODERATE"
    elif max_val > 12: alert_lvl, status = 2, "FAIR"
    else: alert_lvl, status = 1, "EXCELLENT"

    # Generate the human-readable alert using the new peak_time[cite: 6]
    if alert_lvl >= 3:
        prediction_alert = f"Warning: {status} levels expected around {peak_time}. Consider rescheduling outdoor tasks."
    else:
        prediction_alert = f"Optimal: Air quality is expected to remain {status} for the next 24 hours."

    yesterday_pm25, last_year_pm25 = get_historical_baselines(official_name, future_weather)
    
    
    return jsonify({
        'prediction': my_model_forecast[0],
        'alert_msg': prediction_alert,
        'alert_color': HEALTH_RECS[alert_lvl]['color'],
        'reason': driver_msg, 
        'chart_data': {'labels': forecast_labels, 'pm25': my_model_forecast,'yesterday': yesterday_pm25,   
        'last_year': last_year_pm25}
    })

if __name__ == "__main__":
    app.run(debug=True)