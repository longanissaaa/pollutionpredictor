import pandas as pd
import pymongo
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to MongoDB
print("Connecting to MongoDB...")
client = pymongo.MongoClient(os.getenv("MONGO_URI"))
db = client["air_quality_db"]
collection = db["pollution_data"]

# Read your local CSV
print("Reading local pollution_data.csv...")
df = pd.read_csv("pollution_data.csv")

# Convert the pandas dataframe into a list of dictionaries
records = df.to_dict('records')

# Upload the data
print(f"Uploading {len(records)} records. This might take a minute...")
collection.insert_many(records)

print("✅ Success! Your 2 years of historical data are now in the cloud.")