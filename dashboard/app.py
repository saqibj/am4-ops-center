"""Streamlit dashboard: hub explorer, aircraft comparison, route analyzer, fleet planner, contribution, map."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
from app.paths import db_path, ensure_runtime_dirs, migrate_legacy_repo_db

ensure_runtime_dirs()
migrate_legacy_repo_db()
DB_PATH = os.environ.get("AM4_ROUTEMINE_DB", str(db_path()))


@st.cache_resource
def connect(db: str) -> sqlite3.Connection:
    p = Path(db)
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    conn = sqlite3.connect(str(p), check_same_thread=False)
    return conn


def _conn() -> sqlite3.Connection:
    return connect(DB_PATH)


def _hub_options(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT iata AS hub, name, country FROM airports
        WHERE iata IS NOT NULL AND TRIM(iata) != ''
        ORDER BY iata
        """,
        conn,
    )


def _aircraft_options(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT shortname, name, type, cost FROM aircraft ORDER BY shortname",
        conn,
    )


st.set_page_config(page_title="AM4 Ops Center", layout="wide")
st.title("AM4 Ops Center")

try:
    conn = _conn()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

page = st.sidebar.radio(
    "Page",
    [
        "Hub Explorer",
        "Aircraft Comparison",
        "Route Analyzer",
        "Fleet Planner",
        "Contribution Optimizer",
        "Global Heatmap",
    ],
)

hub_df = _hub_options(conn)
ac_df = _aircraft_options(conn)

if page == "Hub Explorer":
    st.subheader("Hub Explorer")
    hubs = hub_df["hub"].dropna().unique().tolist()
    hub = st.selectbox("Hub (IATA)", hubs, index=0 if hubs else None)
    ac_type = st.selectbox("Aircraft type", ["(all)", "PAX", "CARGO", "VIP"])
    min_profit = st.number_input("Min profit / day", value=0.0)
    max_dist = st.number_input("Max distance (km, 0 = no limit)", value=0.0)
    hide_stop = st.checkbox("Hide stopover routes", value=False)
    sort_by = st.selectbox("Sort by", ["profit_per_ac_day", "contribution", "income_per_ac_day"])
    if hub:
        q = """
        SELECT * FROM v_best_routes WHERE hub = ?
        """
        params: list = [hub]
        df = pd.read_sql_query(q, conn, params=params)
        if ac_type != "(all)":
            df = df[df["ac_type"].str.upper() == ac_type.upper()]
        df = df[df["profit_per_ac_day"] >= min_profit]
        if max_dist > 0:
            df = df[df["distance_km"] <= max_dist]
        if hide_stop:
            df = df[df["needs_stopover"] == 0]
        df = df.sort_values(sort_by, ascending=False)
        st.dataframe(df, use_container_width=True, height=520)

elif page == "Aircraft Comparison":
    st.subheader("Aircraft comparison — best routes for one aircraft")
    shortnames = ac_df["shortname"].tolist()
    ac_pick = st.selectbox("Aircraft", shortnames, index=0 if shortnames else None)
    min_profit = st.number_input("Min profit / day", value=0.0, key="ac_cmp_minp")
    sort_by = st.selectbox("Sort by", ["profit_per_ac_day", "contribution"], key="ac_cmp_sort")
    if ac_pick:
        q = """
        SELECT v.* FROM v_best_routes v
        WHERE v.aircraft = ?
        """
        df = pd.read_sql_query(q, conn, params=(ac_pick,))
        df = df[df["profit_per_ac_day"] >= min_profit]
        df = df.sort_values(sort_by, ascending=False)
        st.dataframe(df, use_container_width=True, height=520)

elif page == "Route Analyzer":
    st.subheader("Route analyzer — all aircraft for an origin/destination pair")
    o = st.selectbox("Origin", hub_df["hub"].tolist(), key="ra_o")
    d = st.selectbox("Destination", hub_df["hub"].tolist(), key="ra_d")
    if o and d and o != d:
        q = """
        SELECT ac.shortname, ac.name, ac.type, ac.cost,
               ra.profit_per_ac_day, ra.trips_per_day, ra.profit_per_trip,
               ra.config_y, ra.config_j, ra.config_f, ra.flight_time_hrs,
               ra.distance_km, ra.needs_stopover, ra.contribution
        FROM route_aircraft ra
        JOIN airports a0 ON ra.origin_id = a0.id
        JOIN airports a1 ON ra.dest_id = a1.id
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1 AND a0.iata = ? AND a1.iata = ?
        ORDER BY ra.profit_per_ac_day DESC
        """
        df = pd.read_sql_query(q, conn, params=(o, d))
        st.dataframe(df, use_container_width=True, height=520)

elif page == "Fleet Planner":
    st.subheader("Fleet planner — aircraft under budget at a hub (by average route profit)")
    hub = st.selectbox("Hub", hub_df["hub"].tolist(), key="fp_hub")
    budget = st.number_input("Budget ($)", min_value=0, value=200_000_000, step=1_000_000)
    top_n = st.slider("Top N aircraft to show", 5, 50, 15)
    if hub:
        oid = pd.read_sql_query("SELECT id FROM airports WHERE iata = ? LIMIT 1", conn, params=(hub,))
        if oid.empty:
            st.warning("Unknown hub.")
        else:
            origin_id = int(oid.iloc[0, 0])
            q = """
            SELECT ac.shortname, ac.name, ac.type, ac.cost,
                   COUNT(*) AS routes,
                   AVG(ra.profit_per_ac_day) AS avg_daily_profit,
                   MAX(ra.profit_per_ac_day) AS best_daily_profit
            FROM route_aircraft ra
            JOIN aircraft ac ON ra.aircraft_id = ac.id
            WHERE ra.is_valid = 1 AND ra.origin_id = ? AND ac.cost <= ?
            GROUP BY ra.aircraft_id
            ORDER BY avg_daily_profit DESC
            LIMIT ?
            """
            df = pd.read_sql_query(q, conn, params=(origin_id, int(budget), top_n))
            st.dataframe(df, use_container_width=True)

elif page == "Contribution Optimizer":
    st.subheader("Routes ranked by alliance contribution")
    limit = st.slider("Rows", 50, 5000, 500, step=50)
    df = pd.read_sql_query(
        f"SELECT * FROM v_best_routes ORDER BY contribution DESC LIMIT {int(limit)}",
        conn,
    )
    st.dataframe(df, use_container_width=True, height=520)

elif page == "Global Heatmap":
    st.subheader("Destination map from a hub (profit-weighted)")
    hub = st.selectbox("Hub", hub_df["hub"].tolist(), key="map_hub")
    top_n = st.slider("Top destinations", 20, 500, 100)
    if hub:
        q = """
        SELECT ap.iata, ap.lat, ap.lng, ra.profit_per_ac_day
        FROM route_aircraft ra
        JOIN airports orig ON ra.origin_id = orig.id
        JOIN airports ap ON ra.dest_id = ap.id
        WHERE ra.is_valid = 1 AND orig.iata = ?
        ORDER BY ra.profit_per_ac_day DESC
        LIMIT ?
        """
        df = pd.read_sql_query(q, conn, params=(hub, int(top_n)))
        if df.empty:
            st.info("No rows for this hub.")
        else:
            plot_df = df.rename(columns={"lat": "lat", "lng": "lon"})
            st.map(plot_df)
            st.dataframe(df, use_container_width=True)
