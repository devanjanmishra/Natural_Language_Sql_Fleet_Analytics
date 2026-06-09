"""Interactive dashboard over the canonicalized fleet data.

Reads the canonical CSV and visualizes the cleaned data — fleet composition,
fault rates, and regional breakdowns. Because the data is canonicalized, the
charts group cleanly by model/fuel/region instead of fragmenting across messy
raw spellings.

Run:
  pip install streamlit pandas duckdb
  streamlit run scripts/dashboard.py
"""
import duckdb
import pandas as pd
import streamlit as st

CSV = "data/sample/fleet_canonical.csv"

st.set_page_config(page_title="Fleet Insight Dashboard", layout="wide")
st.title("🚚 Fleet Insight — Canonicalized Analytics")
st.caption("Dashboard built on LLM-canonicalized fleet data. Raw spellings like "
           "'Volvo FH16', 'fh-16', 'DSL', 'Sth' are normalized before aggregation.")

df = pd.read_csv(CSV)
con = duckdb.connect()
con.register("fleet", df)

# --- filters ---
with st.sidebar:
    st.header("Filters")
    models = st.multiselect("Model", sorted(df["model"].unique()), default=list(df["model"].unique()))
    fuels = st.multiselect("Fuel type", sorted(df["fuel_type"].unique()), default=list(df["fuel_type"].unique()))

f = df[df["model"].isin(models) & df["fuel_type"].isin(fuels)]

# --- KPIs ---
c1, c2, c3 = st.columns(3)
c1.metric("Vehicles", len(f))
c2.metric("Total fault events", int(f["fault_events"].sum()))
c3.metric("Avg faults / vehicle", round(f["fault_events"].mean(), 2) if len(f) else 0)

# --- charts ---
left, right = st.columns(2)

with left:
    st.subheader("Fleet composition by model")
    comp = f.groupby("model").size().rename("vehicles")
    st.bar_chart(comp)

with right:
    st.subheader("Avg faults per vehicle by fuel type")
    fault = f.groupby("fuel_type")["fault_events"].mean().round(2)
    st.bar_chart(fault)

st.subheader("Vehicles by region")
region = f.groupby("region").size().rename("vehicles")
st.bar_chart(region)

# --- before/after canonicalization proof ---
with st.expander("See raw → canonical normalization"):
    pairs = (df[["model_raw", "model"]].drop_duplicates()
             .sort_values("model").reset_index(drop=True))
    st.write("Each messy raw model value and the canonical value it maps to:")
    st.dataframe(pairs, use_container_width=True)

st.subheader("Detail")
st.dataframe(f, use_container_width=True)
