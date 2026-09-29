"""SQLite storage and parameterized queries used by Streamlit."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from parse_weather import parse_weather

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data.db"


def save_forecast(frame, issued_at, db_path=DB_PATH):
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS TemperatureForecasts (
            id INTEGER PRIMARY KEY, regionName TEXT NOT NULL, dataDate TEXT NOT NULL,
            mint REAL NOT NULL, maxt REAL NOT NULL, UNIQUE(regionName, dataDate),
            CHECK(mint <= maxt))""")
        conn.execute("CREATE TABLE IF NOT EXISTS Metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        # Replace the current forecast horizon atomically; do not mix different issue times.
        conn.execute("DELETE FROM TemperatureForecasts")
        conn.executemany("INSERT INTO TemperatureForecasts(regionName,dataDate,mint,maxt) VALUES (?,?,?,?)",
                         frame[["regionName", "dataDate", "mint", "maxt"]].itertuples(index=False, name=None))
        conn.executemany("INSERT OR REPLACE INTO Metadata VALUES (?,?)", [
            ("issued_at", issued_at), ("fetched_at", datetime.now(timezone.utc).isoformat()),
            ("source", "CWA F-C0032-003")])


def query_forecast(region=None, db_path=DB_PATH):
    with closing(sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
        sql = "SELECT regionName, dataDate, mint, maxt FROM TemperatureForecasts"
        params = ()
        if region is not None:
            sql += " WHERE regionName = ?"
            params = (region,)
        return pd.read_sql_query(sql + " ORDER BY dataDate, regionName", conn, params=params)


def get_regions(db_path=DB_PATH):
    with closing(sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
        return [row[0] for row in conn.execute("SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY regionName")]


def metadata(db_path=DB_PATH):
    with closing(sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
        return dict(conn.execute("SELECT name,value FROM Metadata"))


def import_raw():
    payload = json.loads((ROOT / "weather_raw.json").read_text(encoding="utf-8"))
    frame = parse_weather(payload)
    save_forecast(frame, payload["cwaopendata"]["Dataset"]["DatasetInfo"]["IssueTime"])
    frame.to_csv(ROOT / "weather_data.csv", index=False, encoding="utf-8-sig")
    return frame


if __name__ == "__main__":
    frame = import_raw()
    print(f"SQLite updated: {len(frame)} rows, {len(get_regions())} regions")
