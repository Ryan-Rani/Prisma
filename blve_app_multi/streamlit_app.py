
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="BLVE.AGENCY — Growth Dashboard", layout="wide")

DATA_DIR = Path(__file__).parent

METRICS = ["followers", "likes", "comments"]
ACCOUNTS = ["A", "B", "C"]

def load_frames(metric: str):
    frames = {}
    for acc in ACCOUNTS:
        frames[acc] = {
            "monthly": pd.read_csv(DATA_DIR / f"{metric}_{acc}_monthly_from_daily.csv", parse_dates=["date"]),
            "daily30": pd.read_csv(DATA_DIR / f"{metric}_{acc}_daily_30.csv", parse_dates=["date"]),
            "daily365": pd.read_csv(DATA_DIR / f"{metric}_{acc}_daily_365.csv", parse_dates=["date"]),
        }
    return frames

# Header
st.title("BLVE.AGENCY — LinkedIn Growth Dashboard")
st.markdown(
    """
    **BLVE.AGENCY** helps venture capital GPs build a LinkedIn-first presence by training an AI agent on a partner’s
    writing, books, and talks, then pairing voice-true drafts with on-brand visuals, scheduling, and analytics.
    Below is a sample dashboard (with made-up data) to illustrate reporting.
    """
)

# Header buttons for pages
if "page" not in st.session_state:
    st.session_state.page = "followers"

with st.container():
    cols = st.columns(3)
    if cols[0].button("Followers", use_container_width=True):
        st.session_state.page = "followers"
    if cols[1].button("Likes", use_container_width=True):
        st.session_state.page = "likes"
    if cols[2].button("Comments", use_container_width=True):
        st.session_state.page = "comments"

metric = st.session_state.page

st.subheader(metric.capitalize())

frames = load_frames(metric)

st.sidebar.header("Display Options")
show_daily30 = st.sidebar.checkbox("Show daily (last 30 days)", value=True)
show_monthly = st.sidebar.checkbox("Show monthly (last 12 months, month-end)", value=True)

for acc in ACCOUNTS:
    st.markdown(f"### Account {acc}")
    cols = st.columns(2)

    if show_monthly:
        dfm = frames[acc]["monthly"].rename(columns={"value": metric})
        with cols[0]:
            st.caption("Monthly (last 12 months; month-end values derived from daily)")
            st.line_chart(dfm.set_index("date")[metric])
            st.download_button(f"Download monthly CSV — {acc}", dfm.to_csv(index=False).encode("utf-8"),
                               file_name=f"{metric}_{acc}_monthly.csv", mime="text/csv")

    if show_daily30:
        dfd = frames[acc]["daily30"].rename(columns={"value": metric})
        with cols[1]:
            st.caption("Daily (last 30 days)")
            st.line_chart(dfd.set_index("date")[metric])
            st.download_button(f"Download daily 30 CSV — {acc}", dfd.to_csv(index=False).encode("utf-8"),
                               file_name=f"{metric}_{acc}_daily_30.csv", mime="text/csv")

    with st.expander("See daily (last 365 days)"):
        df365 = frames[acc]["daily365"].rename(columns={"value": metric})
        st.line_chart(df365.set_index("date")[metric])
        st.download_button(f"Download daily 365 CSV — {acc}", df365.to_csv(index=False).encode("utf-8"),
                           file_name=f"{metric}_{acc}_daily_365.csv", mime="text/csv")

    st.markdown("---")

st.markdown("Made-up data for demonstration only.")
