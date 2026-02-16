import streamlit as st
import pandas as pd
import plotly.express as px
import json
from pathlib import Path

st.set_page_config(page_title="GPU Pricing Tracker", page_icon="⚡", layout="wide")
st.markdown("""<style>.stApp{background-color:#0f1117;color:#fafafa;} section[data-testid="stSidebar"]{background-color:#1a1c23;} h1,h2,h3,p,span,label{color:#fafafa !important;} .stMetric label{font-size:14px !important;} .stMetric [data-testid="stMetricValue"]{font-size:28px !important; color:#ffffff !important;} .stMarkdown{font-size:15px;}</style>""", unsafe_allow_html=True)

DATA_FILE = Path(__file__).parent / "gpu_pricing_data.json"
if not DATA_FILE.exists():
    st.error("Run: python gpu_price_collector.py --init")
    st.stop()

with open(DATA_FILE) as f:
    data = json.load(f)

entries = data["entries"]
gpus = data["metadata"]["tracked_gpus"]
COLORS = {"GB300":"#ff6b6b","GB200":"#ee5a24","B300":"#f368e0","B200":"#be2edd","H200 SXM":"#f43f5e","H100 SXM":"#8b5cf6","A100 80GB":"#3b82f6","A100 40GB":"#06b6d4","L40S":"#10b981","L40":"#2ed573","RTX 6000 Ada":"#ffa502","RTX 5090":"#ff4757","RTX 4090":"#f59e0b","RTX 3090":"#dfe6e9","L4":"#84cc16","A40":"#00d2d3","T4":"#f97316","V100":"#a3a3a3","AMD MI300X":"#e84118","AMD MI325X":"#c23616"}

rows = []
for e in entries:
    for gpu, price in e["prices"].items():
        rows.append({"date":e["date"],"week":e["week"],"gpu":gpu,"price":price})
df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])

latest = entries[-1]
four_wk = entries[-5] if len(entries)>=5 else entries[0]

with st.sidebar:
    st.markdown("### ⚡ GPU Pricing Tracker")
    st.markdown("**Flagship**")
    flagship = ["GB300","GB200","B300","B200","H200 SXM","H100 SXM"]
    sel_flag = st.multiselect("", [g for g in flagship if g in gpus], default=["H100 SXM","B200"], key="f", label_visibility="collapsed")
    st.markdown("**Mid-Tier**")
    mid = ["A100 80GB","A100 40GB","L40S","L40","AMD MI300X","AMD MI325X"]
    sel_mid = st.multiselect("", [g for g in mid if g in gpus], default=["A100 80GB","L40S"], key="m", label_visibility="collapsed")
    st.markdown("**Budget**")
    budget = ["RTX 6000 Ada","RTX 5090","RTX 4090","RTX 3090","L4","A40","T4","V100"]
    sel_bud = st.multiselect("", [g for g in budget if g in gpus], default=["RTX 4090","T4"], key="b", label_visibility="collapsed")
    selected = sel_flag + sel_mid + sel_bud
    weeks = st.slider("Weeks to show", 4, len(entries), len(entries))

st.markdown("# ⚡ GPU Cloud Pricing Dashboard")
st.caption(f"Weekly on-demand rates across major providers · {len(gpus)} GPUs tracked · Last updated {latest['date']}")

if selected:
    cols = st.columns(min(len(selected),6))
    for i, gpu in enumerate(selected[:6]):
        c = latest["prices"].get(gpu,0)
        p = four_wk["prices"].get(gpu,c)
        ch = ((c-p)/p*100) if p else 0
        with cols[i%len(cols)]:
            st.metric(gpu, f"${c:.2f}/hr", f"{ch:+.1f}% (4wk)", delta_color="inverse")

filtered = df[df["gpu"].isin(selected)]
filtered = filtered[filtered["date"]>=filtered["date"].max()-pd.Timedelta(weeks=weeks)]

st.markdown("### Weekly Price Trends")
fig = px.line(filtered, x="date", y="price", color="gpu", color_discrete_map=COLORS, labels={"price":"$/hr","date":"","gpu":"GPU"})
fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified", height=450, yaxis_tickprefix="$")
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown("### Current Rates (All GPUs)")
    bar = pd.DataFrame([{"gpu":g,"price":latest["prices"][g]} for g in gpus]).sort_values("price")
    fig2 = px.bar(bar, x="price", y="gpu", orientation="h", color="gpu", color_discrete_map=COLORS)
    fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False, height=600, xaxis_tickprefix="$")
    st.plotly_chart(fig2, use_container_width=True)

with c2:
    st.markdown("### Cost Estimates")
    hrs = st.select_slider("Duration:", [1,8,24,168,720], 24, format_func=lambda x:{1:"1 hour",8:"8 hours",24:"1 day",168:"1 week",720:"1 month"}[x])
    cost = pd.DataFrame([{"GPU":g,"$/hr":f"${latest['prices'][g]:.2f}",f"Cost ({hrs}h)":f"${latest['prices'][g]*hrs:,.2f}","4wk Chg":f"{((latest['prices'][g]-four_wk['prices'].get(g,latest['prices'][g]))/four_wk['prices'].get(g,latest['prices'][g])*100):+.1f}%"} for g in gpus])
    st.dataframe(cost, use_container_width=True, hide_index=True, height=560)

st.markdown("### Biggest Price Drops (4 Weeks)")
drops = pd.DataFrame([{"GPU":g,"Change %":((latest["prices"][g]-four_wk["prices"].get(g,latest["prices"][g]))/four_wk["prices"].get(g,latest["prices"][g])*100)} for g in gpus]).sort_values("Change %")
fig3 = px.bar(drops, x="GPU", y="Change %", color="Change %", color_continuous_scale=["#34d399","#fbbf24","#f87171"])
fig3.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=350, yaxis_ticksuffix="%")
st.plotly_chart(fig3, use_container_width=True)
