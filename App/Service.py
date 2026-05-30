import requests
from dotenv import load_dotenv
import os
from datetime import datetime
import csv
from datetime import timezone
import pymongo

load_dotenv()

class AirService:
    def __init__(self):
        self.owm_key = os.getenv("OPENAIR_API_KEY")
        self.mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
        self.collection = self.mongo_client["air_quality_db"]["pollution_data"]

    def get_coords(self, city_name): 
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name},PH&limit=1&appid={self.owm_key}"
        try:
            response = requests.get(geo_url)
            data = response.json()
            if data:
                return data[0]["lat"], data[0]["lon"], data[0]["name"]
        except Exception as e:
            print(f"Error fetching coordinates: {e}")
        return None, None, None

    def get_data(self, lat, lon):
        data_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={self.owm_key}"
        try:
            response = requests.get(data_url)
            return response.json()
        except Exception as e:
            print(f"Error fetching pollution data: {e}")
            return None
        
    def get_full_forecast(self, lat, lon):
        
        url = f"http://api.openweathermap.org/data/2.5/air_pollution/forecast?lat={lat}&lon={lon}&appid={self.owm_key}"
        try:
            response = requests.get(url)
            data = response.json()
            if data and 'list' in data:
                return data['list'] 
        except Exception as e:
            print(f"Error fetching forecast: {e}")
        return []
    
    def get_weather_stats(self, lat, lon):
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={self.owm_key}&units=metric"
        try:
            response = requests.get(url)
            w = response.json()
            return {
                "temp": w['main']['temp'],
                "humidity": w['main']['humidity'],
                "wind_speed": w['wind']['speed'],
                "dt": w['dt']
            }
        except Exception as e:
            print(f"Error fetching weather stats: {e}")
            return None
        
    def get_weather_forecast(self, lat, lon):
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,wind_direction_10m"
            "&timezone=GMT"
        )
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json().get('hourly', {})
            forecast_list = []
            times = data.get('time', [])
            for i in range(len(times)):
                forecast_list.append({
                    'dt': int(datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).timestamp()),
                    'temp': data['temperature_2m'][i],
                    'humidity': data['relative_humidity_2m'][i],
                    'wind_speed': data['wind_speed_10m'][i],
                    'precipitation': data['precipitation'][i],
                    'wind_direction': data['wind_direction_10m'][i]
                })
            return forecast_list
        except Exception as e:
            print(f"Error fetching Open-Meteo forecast: {e}")
            return []
    
    def log_to_csv(self, pollution_data, weather_stats, city_name):
        file_path = "pollution_data.csv"
        file_exist = os.path.isfile(file_path)
        
        fieldnames = ['timestamp',
                      'city',
                      'aqi',
                      'pm2_5',
                      'pm10',
                      'temp',
                      'humidity',
                      'wind_speed',
                      "no2",
                      "o3"
                      ]

        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exist:
                writer.writeheader()
            
            if 'list' in pollution_data and len(pollution_data['list']) > 0:
                p = pollution_data['list'][0]
                
            
                row = {
                    'timestamp': datetime.fromtimestamp(p.get('dt')).strftime('%Y-%m-%d %H:%M:%S'),
                    'city': city_name,
                    'aqi': p['main'].get('aqi'),
                    'pm2_5': p['components'].get('pm2_5'),
                    'pm10': p['components'].get('pm10'),
                    'temp': weather_stats.get('temp') if weather_stats else None,
                    'humidity': weather_stats.get('humidity') if weather_stats else None,
                    'wind_speed': weather_stats.get('wind_speed') if weather_stats else None,
                    'no2': p['components'].get('no2'),
                    'o3': p['components'].get('o3'),
                }
                self.collection.insert_one(row)
