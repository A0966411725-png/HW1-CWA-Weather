"""Download CWA seven-day forecast JSON; never log credential URLs."""
import json
import os
from pathlib import Path

import requests
import truststore
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA_ID = "F-C0032-003"
# One-week town forecasts for all 22 counties (F-D0047-003, -007, ..., -087), queried through F-D0047-093.
TOWN_DATASETS = [f"F-D0047-{n:03d}" for n in range(3, 88, 4)]


def _api_key():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env")
    key = os.getenv("CWA_API_KEY", "")
    if not key:
        raise RuntimeError("Please configure CWA_API_KEY in .env or environment variables.")
    truststore.inject_into_ssl()
    return key


def fetch_weather(output=ROOT / "weather_raw.json"):
    key = _api_key()
    try:
        response = requests.get(
            f"https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/{DATA_ID}",
            params={"Authorization": key, "downloadType": "WEB", "format": "JSON"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if "cwaopendata" not in payload:
            raise ValueError("Unexpected forecast response")
    except (requests.RequestException, ValueError):
        raise RuntimeError("CWA forecast download failed; previous database is unchanged.") from None
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def fetch_towns(output=ROOT / "weather_town_raw.json"):
    key = _api_key()
    counties = []
    try:
        for start in range(0, len(TOWN_DATASETS), 5):  # CWA answers at most five datasets per request
            response = requests.get(
                "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-093",
                params={"Authorization": key, "format": "JSON", "ElementName": "最高溫度,最低溫度",
                        "locationId": ",".join(TOWN_DATASETS[start:start + 5])},
                timeout=60,
            )
            response.raise_for_status()
            counties += response.json()["records"]["Locations"]
    except (requests.RequestException, ValueError, KeyError):
        raise RuntimeError("CWA town forecast download failed; previous database is unchanged.") from None
    payload = {"Locations": counties}
    Path(output).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


if __name__ == "__main__":
    fetch_weather()
    print(f"Downloaded {DATA_ID} to weather_raw.json")
    fetch_towns()
    print("Downloaded town forecasts to weather_town_raw.json")
