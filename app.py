"""HW1: all displayed forecast data comes from SQLite SQL queries."""
import math
import sqlite3
from datetime import datetime, timedelta, timezone

import altair as alt
import folium
import streamlit as st
from branca.element import MacroElement, Template
from streamlit_folium import st_folium

from database import get_regions, metadata, query_forecast, query_towns
from parse_weather import REGIONS

TAIWAN = timezone(timedelta(hours=8))
# Course colour scale for the daily mean temperature: label, background, text colour.
BANDS = [("<20", "#1c7ed6", "white"), ("20–24", "#2f9e44", "white"),
         ("25–30", "#f5c400", "#212529"), (">30", "#e03131", "white")]
REGION_CENTRES = {"北部地區": (25.0, 121.3), "中部地區": (24.0, 120.7), "南部地區": (22.9, 120.4),
                  "東北部地區": (24.7, 121.75), "東部地區": (23.8, 121.5), "東南部地區": (22.8, 121.15)}


def daily_mean(row):
    """(MinT + MaxT) / 2 rounded half up; the marker number and colour both use this value."""
    return math.floor((row.mint + row.maxt) / 2 + 0.5)


def temperature_marker(value, size):
    _, background, text = BANDS[0 if value < 20 else 1 if value < 25 else 2 if value <= 30 else 3]
    return folium.DivIcon(
        html=f'<div style="width:{size}px;height:{size}px;line-height:{size}px;border-radius:50%;'
             f'background:{background};color:{text};font-size:{size // 2}px;font-weight:700;text-align:center;'
             f'font-family:sans-serif;border:1px solid rgba(0,0,0,.35);box-shadow:0 1px 3px rgba(0,0,0,.35)">'
             f'{value}</div>',
        icon_size=(size, size), icon_anchor=(size // 2, size // 2), class_name="temperature-marker")


class Legend(MacroElement):
    """Colour scale drawn in the map corner, like the AirBox example."""
    _template = Template("""
        {% macro script(this, kwargs) %}
        var legend = L.control({position: "bottomleft"});
        legend.onAdd = function () {
            var div = L.DomUtil.create("div");
            div.innerHTML = {{ this.html|tojson }};
            return div;
        };
        legend.addTo({{ this._parent.get_name() }});
        {% endmacro %}
    """)

    def __init__(self):
        super().__init__()
        self._name = "Legend"
        cells = "".join(f'<span style="background:{background};color:{text};padding:3px 9px;font-weight:700">'
                        f'{label}</span>' for label, background, text in BANDS)
        self.html = ('<div style="background:rgba(255,255,255,.92);padding:6px 8px;border-radius:6px;'
                     'box-shadow:0 1px 4px rgba(0,0,0,.3);font:12px sans-serif;color:#212529">'
                     f'<div style="margin-bottom:4px;font-weight:600">日均溫 °C</div><div style="display:flex">{cells}</div></div>')


st.set_page_config(page_title="Taiwan Weather Forecast", page_icon="🌤️", layout="wide")
st.title("🌤️ Taiwan Weather Forecast")
st.caption("台灣六大區域 · 一週高低溫預報 · 中央氣象署 CWA")

try:
    available = get_regions()
    info = metadata()
    all_data = query_forecast()
    towns = query_towns()
except (sqlite3.Error, OSError):
    st.error("預報資料目前無法讀取，請稍後再試。")
    st.stop()
if all_data.empty:
    st.info("目前沒有可顯示的預報資料。")
    st.stop()

issued = datetime.fromisoformat(info["issued_at"])
st.caption(f"預報發布：{issued:%Y/%m/%d %H:%M}（台灣時間）｜來源：{info['source']}")
if datetime.now(timezone.utc) - issued > timedelta(hours=24):
    st.warning("目前顯示的是較早的預報版本，請留意發布時間與預報日期。")
with st.sidebar:
    st.header("預報查詢")
    region = st.selectbox("選擇地區", [r for r in REGIONS if r in available])
    st.caption("溫度單位：°C。每筆代表該區域當日預報範圍。")
    st.button("重新讀取資料", help="讀取網站目前的 SQLite 資料庫")

data = query_forecast(region)
st.subheader(region)
left, right = st.columns([2, 1])
with left:
    chart_data = data.melt(id_vars=["dataDate"], value_vars=["mint", "maxt"], var_name="series", value_name="temperature")
    chart_data["series"] = chart_data.series.map({"mint": "最低溫 MinT", "maxt": "最高溫 MaxT"})
    chart = alt.Chart(chart_data).mark_line(point=True).encode(
        x=alt.X("dataDate:T", title="預報日期", axis=alt.Axis(format="%m/%d")),
        y=alt.Y("temperature:Q", title="氣溫（°C）", scale=alt.Scale(zero=False)),
        color=alt.Color("series:N", title=None, scale=alt.Scale(domain=["最低溫 MinT", "最高溫 MaxT"], range=["#1879c7", "#e34c4c"])),
        tooltip=[alt.Tooltip("dataDate:T", title="日期", format="%Y/%m/%d"), alt.Tooltip("series:N", title="預報"), alt.Tooltip("temperature:Q", title="°C")],
    ).properties(height=310)
    st.altair_chart(chart, width="stretch")
with right:
    st.dataframe(data[["dataDate", "mint", "maxt"]].rename(columns={"dataDate": "日期", "mint": "最低溫 °C", "maxt": "最高溫 °C"}), hide_index=True, width="stretch")
    st.download_button("下載此區域 CSV", data.to_csv(index=False).encode("utf-8-sig"), file_name=f"{region}.csv", mime="text/csv")

st.subheader("台灣溫度預報地圖")
layer = st.radio("地圖圖層", ["鄉鎮市區", "六大區域"] if not towns.empty else ["六大區域"], horizontal=True)
points = towns if layer == "鄉鎮市區" else all_data
selected_date = st.selectbox("選擇預報日期", sorted(points.dataDate.unique()))
day = points[points.dataDate == selected_date]
if layer == "鄉鎮市區":
    fetched = datetime.fromisoformat(info["towns_fetched_at"]).astimezone(TAIWAN) if "towns_fetched_at" in info else None
    st.caption(f"{len(day)} 個鄉鎮市區，來源 CWA 一週鄉鎮預報" + (f"（擷取：{fetched:%Y/%m/%d %H:%M}）" if fetched else "")
               + "。標記位置為各鄉鎮市區的代表點。")
else:
    st.caption("標記位置為區域示意中心。")
st.caption("標記數字與顏色為當日（最低溫＋最高溫）÷2，四捨五入，並非氣象署發布的日平均溫；滑鼠移到標記上可看高低溫。")

weather_map = folium.Map(location=[23.7, 121], zoom_start=7, zoom_snap=0.25, tiles="OpenStreetMap")
weather_map.fit_bounds([[21.9, 119.4], [25.3, 122.0]])
for row in day.itertuples(index=False):
    if layer == "鄉鎮市區":
        folium.Marker([row.lat, row.lon], icon=temperature_marker(daily_mean(row), 22),
                      tooltip=f"{row.countyName}{row.townName} · {row.mint:g}–{row.maxt:g} °C").add_to(weather_map)
    else:
        folium.Marker(REGION_CENTRES[row.regionName], icon=temperature_marker(daily_mean(row), 36),
                      tooltip=f"{row.regionName} · {row.mint:g}–{row.maxt:g} °C",
                      popup=f"{row.regionName}<br>{row.dataDate}<br>最低 {row.mint:g} °C / 最高 {row.maxt:g} °C").add_to(weather_map)
Legend().add_to(weather_map)
st_folium(weather_map, height=560, use_container_width=True, returned_objects=[])
with st.expander("資料處理方式"):
    st.write("CWA JSON → Python 解析高低溫 → SQLite → SQL 查詢 → 折線圖、表格與地圖。網站只讀取資料庫，資料擷取由獨立程式執行。"
             "六大區域使用 F-C0032-003；地圖的鄉鎮圖層使用 22 縣市的一週鄉鎮預報（經 F-D0047-093 查詢）。")
