import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import timedelta


st.set_page_config(
    page_title="Power Consumption & Energy Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

TITLE = "Power Consumption & Energy Analytics Dashboard"
SUBTITLE = "Interactive electrical energy monitoring and load analysis"

st.title(TITLE)
st.markdown(f"#### {SUBTITLE}")


@st.cache_data
def load_data(path="sample_power_data.csv"):
    df = pd.read_csv(path, parse_dates=["timestamp"]) 
    df = df.sort_values("timestamp").reset_index(drop=True)
    # Derived electrical quantities
    df["apparent_power_W"] = df["voltage_V"] * df["current_A"]
    # Use measured active power if given, otherwise calculate
    df["active_power_calc_W"] = df["voltage_V"] * df["current_A"] * df["power_factor"]
    # Prefer provided active_power_W column if present
    if "active_power_W" in df.columns:
        df["active_power_W"] = df["active_power_W"].fillna(df["active_power_calc_W"]) 
    else:
        df["active_power_W"] = df["active_power_calc_W"]

    # Estimate per-row duration (hours) using median diff
    if len(df) > 1:
        df["delta_hours"] = df.groupby("equipment")["timestamp"].diff().dt.total_seconds() / 3600.0
        median = df["delta_hours"].median()
        median = median if not np.isnan(median) else 1.0
        df["delta_hours"] = df["delta_hours"].fillna(median)
    else:
        df["delta_hours"] = 1.0

    df["energy_kwh"] = df["active_power_W"] * df["delta_hours"] / 1000.0
    return df


df = load_data()

# Sidebar controls
st.sidebar.header("Filters & Settings")
equipment_options = df["equipment"].unique().tolist()
selected_equipment = st.sidebar.multiselect("Equipment", options=equipment_options, default=equipment_options)

min_date = df["timestamp"].min().date()
max_date = df["timestamp"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

pf_min, pf_max = float(df["power_factor"].min()), float(df["power_factor"].max())
pf_range = st.sidebar.slider("Power factor range", min_value=0.0, max_value=1.0, value=(pf_min, pf_max), step=0.01)

tariff = st.sidebar.number_input("Electricity tariff (₹/kWh)", min_value=0.0, value=8.0, step=0.5)

if st.sidebar.button("Reset filters"):
    # reset by rerunning with defaults
    st.session_state.clear()
    st.experimental_rerun()

# Apply filters
start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
mask = (
    df["equipment"].isin(selected_equipment)
    & (df["timestamp"] >= start_date)
    & (df["timestamp"] <= end_date)
    & (df["power_factor"] >= pf_range[0])
    & (df["power_factor"] <= pf_range[1])
)

data = df.loc[mask].copy()

if data.empty:
    st.warning("No data matches the selected filters. Adjust filters to view analytics.")
    st.stop()

# Aggregate KPIs
total_energy = data["energy_kwh"].sum()
avg_power = data["active_power_W"].mean()
peak_power = data["active_power_W"].max()
avg_current = data["current_A"].mean()
avg_pf = data["power_factor"].mean()
estimated_cost = total_energy * tariff

col1, col2, col3, col4, col5 = st.columns([1.5,1,1,1,1])
with col1:
    st.metric("Total Energy (kWh)", f"{total_energy:,.2f}")
with col2:
    st.metric("Average Power (W)", f"{avg_power:,.1f}")
with col3:
    st.metric("Peak Power (W)", f"{peak_power:,.1f}")
with col4:
    st.metric("Average Power Factor", f"{avg_pf:,.2f}")
with col5:
    st.metric("Estimated Cost (₹)", f"{estimated_cost:,.2f}")

st.markdown("---")

# Time series: Power over time
st.subheader("Power consumption over time")
fig_time = px.line(
    data.sort_values("timestamp"),
    x="timestamp",
    y="active_power_W",
    color="equipment",
    labels={"active_power_W":"Active Power (W)", "timestamp":"Time"},
    template="plotly_white",
)
fig_time.update_layout(legend_title_text="Equipment")
st.plotly_chart(fig_time, use_container_width=True)

# Energy by equipment
st.subheader("Energy & Power by Equipment")
energy_by_eq = data.groupby("equipment").agg(
    energy_kwh=("energy_kwh","sum"),
    avg_power_W=("active_power_W","mean"),
    peak_power_W=("active_power_W","max"),
    avg_pf=("power_factor","mean"),
).reset_index()

fig_energy = px.bar(energy_by_eq.sort_values("energy_kwh", ascending=False), x="equipment", y="energy_kwh",
                    labels={"energy_kwh":"Energy (kWh)"}, template="plotly_white", color_discrete_sequence=["#1f77b4"])
st.plotly_chart(fig_energy, use_container_width=True)

fig_avg_power = px.bar(energy_by_eq.sort_values("avg_power_W", ascending=False), x="equipment", y="avg_power_W",
                      labels={"avg_power_W":"Average Power (W)"}, template="plotly_white", color_discrete_sequence=["#ff7f0e"])
st.plotly_chart(fig_avg_power, use_container_width=True)

fig_pf = px.bar(energy_by_eq.sort_values("avg_pf"), x="equipment", y="avg_pf", labels={"avg_pf":"Average PF"}, template="plotly_white")
st.plotly_chart(fig_pf, use_container_width=True)

# Voltage vs Current scatter
st.subheader("Voltage vs Current")
fig_scatter = px.scatter(data, x="voltage_V", y="current_A", color="equipment", size="active_power_W",
                         labels={"voltage_V":"Voltage (V)", "current_A":"Current (A)"}, template="plotly_white")
st.plotly_chart(fig_scatter, use_container_width=True)

# Equipment contribution pie
st.subheader("Equipment energy contribution")
fig_pie = px.pie(energy_by_eq, names="equipment", values="energy_kwh", hole=0.35, template="plotly_white")
st.plotly_chart(fig_pie, use_container_width=True)

st.markdown("---")

st.header("Engineering Insights")
insights = []
top_energy = energy_by_eq.sort_values("energy_kwh", ascending=False).iloc[0]
insights.append(f"Highest energy consumer: {top_energy['equipment']} ({top_energy['energy_kwh']:.2f} kWh)")
top_peak = energy_by_eq.sort_values("peak_power_W", ascending=False).iloc[0]
insights.append(f"Highest peak load: {top_peak['equipment']} ({top_peak['peak_power_W']:.1f} W)")
low_pf = energy_by_eq.sort_values("avg_pf").iloc[0]
insights.append(f"Lowest average power factor: {low_pf['equipment']} ({low_pf['avg_pf']:.2f})")
insights.append(f"Overall average power factor: {avg_pf:.2f}")
insights.append(f"Estimated total electricity cost: ₹{estimated_cost:.2f}")

for it in insights:
    st.write("-", it)

st.markdown("---")

st.header("About the Project")
st.markdown(
    """
- **Electrical power analysis**: We compute apparent and active power and convert power to energy (kWh) by integrating power over time.
- **Power factor**: Shows how effectively the current contributes to real work. Low PF increases apparent power for the same active power.
- **Energy consumption**: Summing active power over time gives energy usage in kWh — the billing quantity.
- **Data analytics**: Uses Pandas for time-series aggregation and Plotly for interactive visualizations to explore loads and energy distribution.

This compact dashboard is useful for energy monitoring, detecting high-consuming equipment, and estimating costs for simple energy audits.
"""
)

st.markdown("---")

st.caption("Built with Python, Streamlit, Pandas, NumPy, and Plotly.")