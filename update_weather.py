"""Independent ingestion job. Streamlit never calls CWA directly."""
from fetch_weather import fetch_weather
from database import import_raw

if __name__ == "__main__":
    fetch_weather()
    frame = import_raw()
    print(f"Updated data.db and weather_data.csv: {len(frame)} rows")
