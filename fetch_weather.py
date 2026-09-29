"""Download CWA regional seven-day forecast JSON; never log credential URLs."""
import json
import os
from pathlib import Path

import requests
import truststore
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA_ID = "F-C0032-003"


def fetch_weather(output=ROOT / "weather_raw.json"):
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env")
    key = os.getenv("CWA_API_KEY", "")
    if not key:
        raise RuntimeError("Please configure CWA_API_KEY in .env or environment variables.")
    truststore.inject_into_ssl()
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


if __name__ == "__main__":
    fetch_weather()
    print(f"Downloaded {DATA_ID} to weather_raw.json")
