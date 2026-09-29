import copy
import tempfile
import unittest
from pathlib import Path

from database import get_regions, query_forecast, query_towns, save_forecast, save_towns
from parse_weather import COUNTY_COUNT, REGIONS, parse_towns, parse_weather


def fixture():
    locations = []
    for region in REGIONS:
        elements = []
        for name, value in [("MinTemperature", "20"), ("MaxTemperature", "30")]:
            elements.append({"Time": [{"StartTime": f"2026-09-{day:02d}T00:00:00+08:00", "ElementValue": {name: value}} for day in range(20, 27)]})
        locations.append({"LocationName": region, "WeatherElement": elements})
    return {"cwaopendata": {"Dataset": {"Locations": {"Location": locations}}}}


def town_fixture():
    """22 counties × 2 towns, day and night periods for seven dates, shaped like F-D0047-093."""
    def periods(name, day_value, night_value):
        return [{"StartTime": f"2026-09-{day:02d}T{hour}:00:00+08:00", "ElementValue": [{name: value}]}
                for day in range(20, 27) for hour, value in (("06", day_value), ("18", night_value))]
    counties = []
    for index in range(COUNTY_COUNT):
        towns = [{"LocationName": town, "Latitude": "24.0", "Longitude": "121.0", "WeatherElement": [
            {"ElementName": "最高溫度", "Time": periods("MaxTemperature", "31", "27")},
            {"ElementName": "最低溫度", "Time": periods("MinTemperature", "26", "22")}]} for town in ("東區", "西區")]
        counties.append({"LocationsName": f"縣市{index}", "Location": towns})
    return {"Locations": counties}


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


class TownForecastTests(unittest.TestCase):
    def test_day_and_night_periods_merge_per_date(self):
        frame = parse_towns(town_fixture())
        self.assertEqual(len(frame), COUNTY_COUNT * 2 * 7)
        self.assertEqual(set(frame.mint), {22})
        self.assertEqual(set(frame.maxt), {31})

    def test_rejects_missing_county_bad_value_and_coordinates(self):
        payload = town_fixture()
        payload["Locations"].pop()
        with self.assertRaises(ValueError):
            parse_towns(payload)
        payload = town_fixture()
        payload["Locations"][0]["Location"][0]["WeatherElement"][0]["Time"][0]["ElementValue"][0]["MaxTemperature"] = "-99"
        with self.assertRaises(ValueError):
            parse_towns(payload)
        payload = town_fixture()
        payload["Locations"][0]["Location"][0]["Latitude"] = "0"
        with self.assertRaises(ValueError):
            parse_towns(payload)

    def test_town_import_replaces_and_filters_by_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            save_forecast(parse_weather(fixture()), "2026-09-20T05:00:00+08:00", path)
            self.assertTrue(query_towns(db_path=path).empty)
            frame = parse_towns(town_fixture())
            save_towns(frame, path)
            save_towns(frame, path)
            self.assertEqual(len(query_towns(db_path=path)), COUNTY_COUNT * 2 * 7)
            self.assertEqual(len(query_towns("2026-09-21", path)), COUNTY_COUNT * 2)
            self.assertTrue(query_towns("' OR 1=1 --", path).empty)
