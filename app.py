"""HW10: all displayed forecast data comes from SQLite SQL queries."""
import sqlite3
from datetime import datetime, timedelta, timezone

import altair as alt
import folium
import streamlit as st
from streamlit_folium import st_folium

from database import get_regions, metadata, query_forecast
from parse_weather import REGIONS

st.set_page_config(page_title="Taiwan Weather Forecast", page_icon="🌤️", layout="wide")
st.title("🌤️ Taiwan Weather Forecast")
st.caption("台灣六大區域 · 一週高低溫預報 · 中央氣象署 CWA")

try:
    available = get_regions()
    info = metadata()
    all_data = query_forecast()
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
    st.altair_chart(chart, use_container_width=True)
with right:
    st.dataframe(data[["dataDate", "mint", "maxt"]].rename(columns={"dataDate": "日期", "mint": "最低溫 °C", "maxt": "最高溫 °C"}), hide_index=True, use_container_width=True)
    st.download_button("下載此區域 CSV", data.to_csv(index=False).encode("utf-8-sig"), file_name=f"{region}.csv", mime="text/csv")

st.subheader("台灣區域預報地圖")
selected_date = st.selectbox("選擇預報日期", sorted(all_data.dataDate.unique()))
st.caption("標記位置為區域示意中心；顏色以（最低溫＋最高溫）÷2 分類，並非氣象署發布的日平均溫。")
coordinates = {"北部地區": (25.0, 121.3), "中部地區": (24.0, 120.7), "南部地區": (22.9, 120.4),
               "東北部地區": (24.7, 121.75), "東部地區": (23.8, 121.5), "東南部地區": (22.8, 121.15)}
weather_map = folium.Map(location=[23.7, 121], zoom_start=7, tiles="OpenStreetMap")
for row in all_data[all_data.dataDate == selected_date].itertuples(index=False):
    average = (row.mint + row.maxt) / 2
    color = "#1879c7" if average < 20 else "#219653" if average < 25 else "#e5b800" if average <= 30 else "#ed6a28"
    folium.CircleMarker(coordinates[row.regionName], radius=13, color=color, fill=True, fill_opacity=0.85,
        tooltip=f"{row.regionName} · {row.mint:g}–{row.maxt:g} °C",
        popup=f"{row.regionName}<br>{row.dataDate}<br>最低 {row.mint:g} °C / 最高 {row.maxt:g} °C").add_to(weather_map)
st_folium(weather_map, height=430, use_container_width=True, returned_objects=[])
st.caption("🔵 <20°C　🟢 20–<25°C　🟡 25–30°C　🟠 >30°C ｜地圖資料 © OpenStreetMap contributors")
with st.expander("資料處理方式"):
    st.write("CWA JSON → Python 解析高低溫 → SQLite → SQL 查詢 → 折線圖、表格與地圖。網站只讀取資料庫，資料擷取由獨立程式執行。")
