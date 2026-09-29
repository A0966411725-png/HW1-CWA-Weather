"""Normalize real CWA JSON into six regions × seven forecast dates."""
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
REGIONS = ("北部地區", "中部地區", "南部地區", "東北部地區", "東部地區", "東南部地區")


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
                for upstream, column, aggregate in (("MinTemperature", "mint", min), ("MaxTemperature", "maxt", max)):
                    if upstream not in values:
                        continue
                    value = float(values[upstream])
                    if not math.isfinite(value) or not -30 <= value <= 55:
                        raise ValueError("Invalid forecast temperature")
                    row = by_date.setdefault(day, {"regionName": region, "dataDate": day})
                    row[column] = aggregate(row.get(column, value), value)
        for day in sorted(by_date):
            row = by_date[day]
            if "mint" not in row or "maxt" not in row or row["mint"] > row["maxt"]:
                raise ValueError("Incomplete or inverted temperature range")
            rows.append(row)
    frame = pd.DataFrame(rows, columns=["regionName", "dataDate", "mint", "maxt"])
    if frame.empty or set(frame.regionName) != set(REGIONS):
        raise ValueError("Forecast must include all six regions")
    if frame.duplicated(["regionName", "dataDate"]).any():
        raise ValueError("Duplicate region/date in forecast")
    dates = set(frame.dataDate)
    if len(dates) != 7 or any(set(group.dataDate) != dates for _, group in frame.groupby("regionName")):
        raise ValueError("Each region must have the same seven forecast dates")
    return frame.sort_values(["regionName", "dataDate"]).reset_index(drop=True)


if __name__ == "__main__":
    data = json.loads((ROOT / "weather_raw.json").read_text(encoding="utf-8"))
    frame = parse_weather(data)
    frame.to_csv(ROOT / "weather_data.csv", index=False, encoding="utf-8-sig")
    print(f"Parsed {len(frame)} rows for six regions")
