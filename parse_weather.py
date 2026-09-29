"""Normalize real CWA JSON into region and town daily temperature ranges."""
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
REGIONS = ("北部地區", "中部地區", "南部地區", "東北部地區", "東部地區", "東南部地區")
COUNTY_COUNT = 22
TEMPERATURES = (("MinTemperature", "mint", min), ("MaxTemperature", "maxt", max))


def _temperature(raw):
    value = float(raw)
    if not math.isfinite(value) or not -30 <= value <= 55:
        raise ValueError("Invalid forecast temperature")
    return value


def _check_ranges(rows):
    for row in rows:
        if "mint" not in row or "maxt" not in row or row["mint"] > row["maxt"]:
            raise ValueError("Incomplete or inverted temperature range")


def parse_weather(payload):
    dataset = payload["cwaopendata"]["Dataset"]
    locations = dataset["Locations"]["Location"]
    rows = []
    for location in locations:
        region = location["LocationName"]
        if region not in REGIONS:
            continue
        by_date = {}
        for element in location["WeatherElement"]:
            for period in element["Time"]:
                day = datetime.fromisoformat(period["StartTime"]).date().isoformat()
                values = period["ElementValue"]
                for upstream, column, aggregate in TEMPERATURES:
                    if upstream not in values:
                        continue
                    value = _temperature(values[upstream])
                    row = by_date.setdefault(day, {"regionName": region, "dataDate": day})
                    row[column] = aggregate(row.get(column, value), value)
        _check_ranges(by_date.values())
        rows += [by_date[day] for day in sorted(by_date)]
    frame = pd.DataFrame(rows, columns=["regionName", "dataDate", "mint", "maxt"])
    if frame.empty or set(frame.regionName) != set(REGIONS):
        raise ValueError("Forecast must include all six regions")
    if frame.duplicated(["regionName", "dataDate"]).any():
        raise ValueError("Duplicate region/date in forecast")
    dates = set(frame.dataDate)
    if len(dates) != 7 or any(set(group.dataDate) != dates for _, group in frame.groupby("regionName")):
        raise ValueError("Each region must have the same seven forecast dates")
    return frame.sort_values(["regionName", "dataDate"]).reset_index(drop=True)


def parse_towns(payload):
    """One row per town and date: lowest MinT and highest MaxT of that date's 12-hour periods."""
    rows = {}
    counties = set()
    for county in payload["Locations"]:
        county_name = county["LocationsName"]
        counties.add(county_name)
        for town in county["Location"]:
            lat, lon = float(town["Latitude"]), float(town["Longitude"])
            if not (21 <= lat <= 27 and 118 <= lon <= 123):
                raise ValueError("Town coordinates outside Taiwan")
            for element in town["WeatherElement"]:
                for period in element["Time"]:
                    day = datetime.fromisoformat(period["StartTime"]).date().isoformat()
                    values = period["ElementValue"][0]
                    for upstream, column, aggregate in TEMPERATURES:
                        if upstream not in values:
                            continue
                        value = _temperature(values[upstream])
                        row = rows.setdefault((county_name, town["LocationName"], day), {
                            "countyName": county_name, "townName": town["LocationName"],
                            "lat": lat, "lon": lon, "dataDate": day})
                        row[column] = aggregate(row.get(column, value), value)
    _check_ranges(rows.values())
    columns = ["countyName", "townName", "lat", "lon", "dataDate", "mint", "maxt"]
    frame = pd.DataFrame(list(rows.values()), columns=columns)
    if len(counties) != COUNTY_COUNT:
        raise ValueError("Town forecast must include all 22 counties")
    dates = set(frame.dataDate)
    if len(dates) < 6 or any(set(group.dataDate) != dates for _, group in frame.groupby(["countyName", "townName"])):
        raise ValueError("Each town must have the same forecast dates")
    return frame.sort_values(["countyName", "townName", "dataDate"]).reset_index(drop=True)


if __name__ == "__main__":
    data = json.loads((ROOT / "weather_raw.json").read_text(encoding="utf-8"))
    frame = parse_weather(data)
    frame.to_csv(ROOT / "weather_data.csv", index=False, encoding="utf-8-sig")
    print(f"Parsed {len(frame)} rows for six regions")
    towns = parse_towns(json.loads((ROOT / "weather_town_raw.json").read_text(encoding="utf-8")))
    print(f"Parsed {len(towns)} rows for {len(towns.groupby(['countyName', 'townName']))} towns")
