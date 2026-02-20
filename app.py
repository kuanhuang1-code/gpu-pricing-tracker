import streamlit as st
import pandas as pd
import json
import os
from pathlib import Path

st.set_page_config(layout="wide", page_title="gpu cloud pricing tracker")

DATA_FILE = Path(__file__).parent / "gpu_pricing_data.json"

def load_data():
    if not DATA_FILE.exists():
        return pd.DataFrame(), {}

    with open(DATA_FILE, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            st.error("error: could not decode gpu_pricing_data.json. it might be empty or corrupted.")
            return pd.DataFrame(), {}

    entries = data.get("entries", [])
    metadata = data.get("metadata", {})

    if not entries:
        return pd.DataFrame(), metadata

    rows = []
    for entry in entries:
        for gpu, price in entry["prices"].items():
            rows.append({
                "date": entry["date"],
                "week": entry["week"],
                "gpu_model": gpu,
                "price_per_hour": price,
            })

    df = pd.DataFrame(rows)
    df["price_per_hour"] = pd.to_numeric(df["price_per_hour"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df, metadata


st.title("⚡️ gpu cloud pricing tracker")

data, metadata = load_data()

if data.empty:
    st.warning("no gpu pricing data available. please run `python gpu_price_collector.py --init` to collect data.")
else:
    st.sidebar.header("filter options")

    # gpu model filter
    gpu_models = sorted(data["gpu_model"].unique())
    selected_gpus = st.sidebar.multiselect("select gpu model(s)", gpu_models, default=gpu_models)

    # apply filters
    filtered_data = data[data["gpu_model"].isin(selected_gpus)]

    st.subheader("current gpu prices (per hour)")

    # show the latest week's prices
    latest_date = filtered_data["date"].max()
    latest_data = filtered_data[filtered_data["date"] == latest_date]

    if latest_data.empty:
        st.info("no data matches your selected filters.")
    else:
        # display data table
        display_df = latest_data[["gpu_model", "price_per_hour", "date"]].sort_values(by="price_per_hour").reset_index(drop=True)
        st.dataframe(display_df.style.format({"price_per_hour": "${:.2f}"}))

        # basic statistics
        st.subheader("summary statistics")

        valid_prices = latest_data["price_per_hour"].dropna()
        if not valid_prices.empty:
            avg_price = valid_prices.mean()
            st.metric(label="average price across selected gpus", value=f"${avg_price:.2f}")
        else:
            st.info("no valid prices to calculate average for selected filters.")

        st.write(f"last updated: {latest_date.strftime('%Y-%m-%d')}")

        # charting
        st.subheader("price distribution by gpu model")
        avg_prices_gpu = latest_data.groupby("gpu_model")["price_per_hour"].mean().sort_values()
        st.bar_chart(avg_prices_gpu.dropna())

        st.subheader("price over time")
        pivot = filtered_data.pivot_table(index="date", columns="gpu_model", values="price_per_hour")
        st.line_chart(pivot)
