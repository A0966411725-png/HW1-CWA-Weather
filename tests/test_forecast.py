import copy
import tempfile
import unittest
from pathlib import Path

from database import get_regions, query_forecast, save_forecast
from parse_weather import REGIONS, parse_weather


def fixture():
    locations = []
    for region in REGIONS:
        elements = []
        for name, value in [("MinTemperature", "20"), ("MaxTemperature", "30")]:
            elements.append({"Time": [{"StartTime": f"2026-09-{day:02d}T00:00:00+08:00", "ElementValue": {name: value}} for day in range(20, 27)]})
        locations.append({"LocationName": region, "WeatherElement": elements})
    return {"cwaopendata": {"Dataset": {"Locations": {"Location": locations}}}}


class ForecastTests(unittest.TestCase):
    def test_six_regions_seven_dates(self):
        frame = parse_weather(fixture())
        self.assertEqual(len(frame), 42)
        self.assertEqual(frame.mint.min(), 20)
        self.assertEqual(frame.maxt.max(), 30)

    def test_join_uses_date_not_array_order(self):
        payload = fixture()
        payload["cwaopendata"]["Dataset"]["Locations"]["Location"][0]["WeatherElement"][1]["Time"].reverse()
        self.assertEqual(len(parse_weather(payload)), 42)

    def test_rejects_missing_nan_and_inverted(self):
        for bad in ["NaN", "-99", "35"]:
            payload = fixture()
            payload["cwaopendata"]["Dataset"]["Locations"]["Location"][0]["WeatherElement"][0]["Time"][0]["ElementValue"]["MinTemperature"] = bad
            with self.assertRaises(ValueError):
                parse_weather(payload)
        payload = fixture()
        payload["cwaopendata"]["Dataset"]["Locations"]["Location"].pop()
        with self.assertRaises(ValueError):
            parse_weather(payload)

    def test_repeat_import_and_parameterized_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            frame = parse_weather(fixture())
            save_forecast(frame, "2026-09-20T05:00:00+08:00", path)
            frame.loc[frame.regionName == REGIONS[0], "maxt"] = 31
            save_forecast(frame, "2026-09-20T11:00:00+08:00", path)
            self.assertEqual(len(query_forecast(db_path=path)), 42)
            self.assertEqual(len(get_regions(path)), 6)
            self.assertEqual(query_forecast(REGIONS[0], path).maxt.min(), 31)
            self.assertTrue(query_forecast("' OR 1=1 --", path).empty)

    def test_failed_import_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            frame = parse_weather(fixture())
            save_forecast(frame, "2026-09-20T05:00:00+08:00", path)
            invalid = copy.deepcopy(frame)
            invalid.loc[0, "mint"] = 99
            with self.assertRaises(Exception):
                save_forecast(invalid, "2026-09-20T11:00:00+08:00", path)
            self.assertEqual(len(query_forecast(db_path=path)), 42)
