import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from Service import AirService
from dotenv import load_dotenv


load_dotenv()
OWM_KEY = os.getenv("OPENAIR_API_KEY")
instance = AirService()

DAYS_TO_HARVEST = 10
CHUNK_SIZE_DAYS = 30

NCR_COORDS = {
    "Caloocan":         (14.6504, 120.9715),
    "Las Piñas":        (14.4445, 120.9939),
    "Makati City":      (14.5547, 121.0244),
    "Malabon City":     (14.6628, 120.9573),
    "Mandaluyong City": (14.5794, 121.0359),
    "Manila":           (14.5995, 120.9842),
    "Marikina City":    (14.6507, 121.1029),
    "Muntinlupa City":  (14.4081, 121.0415),
    "Navotas City":     (14.6715, 120.9436),
    "Parañaque City":   (14.4793, 121.0198),
    "Pasay City":       (14.5378, 121.0014),
    "Pasig City":       (14.5764, 121.0851),
    "Quezon City":      (14.6760, 121.0437),
    "San Juan City":    (14.6042, 121.0300),
    "Taguig City":      (14.5176, 121.0509),
    "Valenzuela City":  (14.7011, 120.9830), 
    "Pateros" :         (14.5484, 121.0708)
}

def get_pollution_history(lat, lon, start, end):
    url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={lat}&lon={lon}&start={start}&end={end}&appid={OWM_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('list', [])
    except Exception as e:
        print(f"Pollution API Error: {e}")
        return []

def get_weather_history(lat, lon, start_date, end_date):
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,wind_direction_10m&timezone=GMT"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get('hourly', {})
        
        weather_list = []
        for i in range(len(data.get('time', []))):
            weather_list.append({
                'dt': int(datetime.fromisoformat(data['time'][i]).replace(tzinfo=timezone.utc).timestamp()),
                'temp': data['temperature_2m'][i],
                'humidity': data['relative_humidity_2m'][i],
                'wind_speed': data['wind_speed_10m'][i],
                'precipitation': data['precipitation'][i],
                'wind_direction': data['wind_direction_10m'][i]
            })
        return weather_list
    except Exception as e:
        print(f"Weather API Error: {e}")
        return []
    
# def seed_pollution_data():
    
#     if not os.path.exists("training_data.csv"):
#         return

#     print("Seeding into pollution_data.csv...")
#     df = pd.read_csv("training_data.csv") 

#     df['timestamp'] = df['dt'].apply(
#         lambda x: datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S')
#     )

#     app_columns = ['timestamp', 'city', 'aqi', 'pm2_5', 'pm10']
    
#     existing_cols = [c for c in app_columns if c in df.columns]
#     final_df = df[existing_cols]
    
#     final_df.to_csv("pollution_data.csv", index=False)
#     print(f"pollution_data.csv updated")
        
def harvest():
    final_data = []
    end_ts = int(time.time())
    start_ts = end_ts - (DAYS_TO_HARVEST * 24 * 3600) 

    for city, (lat, lon) in NCR_COORDS.items():
        print(f"📡 Harvesting {city}...", end=" ", flush=True)
        
        
        city_count = 0
        
        for chunk_start in range(start_ts, end_ts, CHUNK_SIZE_DAYS * 24 * 3600):
            chunk_end = min(chunk_start + (CHUNK_SIZE_DAYS * 24 * 3600), end_ts)
            
            start_date_str = datetime.fromtimestamp(chunk_start, tz=timezone.utc).strftime('%Y-%m-%d')
            end_date_str = datetime.fromtimestamp(chunk_end, tz=timezone.utc).strftime('%Y-%m-%d')
            
            print(f" -> Pulling {start_date_str} to {end_date_str}...", end=" ", flush=True)
            
            pollution = get_pollution_history(lat, lon, chunk_start, chunk_end)
            weather = get_weather_history(lat, lon, start_date_str, end_date_str)
            
            weather_dict = {w['dt']: w for w in weather}
            chunk_count = 0
            
            for p in pollution:
                ts = p['dt']
                closest_hour = (ts // 3600) * 3600 
                w_info = weather_dict.get(closest_hour)
                
                if w_info:
                    final_data.append({
                        'timestamp': datetime.fromtimestamp(p.get('dt')).strftime('%Y-%m-%d %H:%M:%S'),
                        'city': city,
                        'aqi': p['main'].get('aqi'),
                        'pm2_5': p['components'].get('pm2_5'),
                        'pm10': p['components'].get('pm10'),
                        'no2': p['components'].get('no2'), 
                        'o3': p['components'].get('o3'),    
                        'temp': w_info['temp'],
                        'humidity': w_info['humidity'],
                        'wind_speed': w_info['wind_speed'],
                        'precipitation': w_info['precipitation'],
                        'wind_direction' : w_info["wind_direction"]
                    })
                    
                    chunk_count += 1
                    city_count += 1
            
            print(f"Got {chunk_count} rows.")
            time.sleep(1.5)
            
        print(f"✅ Finished {city}: {city_count} total records.")

    if final_data:
        df = pd.DataFrame(final_data)
        df = df.drop_duplicates(subset=['city', 'timestamp'])
        
        df = df.sort_values(['city', 'timestamp'])
        df.to_csv("pollution_data.csv", index=False)
        print(f"\n✨ Success! {len(df)} total unique records saved to pollution_data.csv")
    else:
        print("\nNo data collected.")

if __name__ == "__main__":
    harvest()
