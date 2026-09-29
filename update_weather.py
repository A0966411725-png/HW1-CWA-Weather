"""Independent ingestion job. Streamlit never calls CWA directly."""
import sys

from fetch_weather import fetch_towns, fetch_weather
from database import import_raw, import_towns

if __name__ == "__main__":
    fetch_weather()
    frame = import_raw()
    print(f"Updated data.db and weather_data.csv: {len(frame)} rows")
    # The town map layer is optional: a failure keeps the previous town data and the region update.
    try:
        fetch_towns()
        towns = import_towns()
        print(f"Updated town map data: {len(towns.groupby(['countyName', 'townName']))} towns")
    except (RuntimeError, ValueError, KeyError) as error:
        print(f"Warning: town forecast not updated ({error}); keeping previous map data.", file=sys.stderr)
