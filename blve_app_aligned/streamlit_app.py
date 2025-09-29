
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="BLVE.AGENCY — LinkedIn Growth Dashboard", layout="wide")

st.title("BLVE.AGENCY — LinkedIn Growth Dashboard")
st.markdown(
    """
    **BLVE.AGENCY** is a premium personal brand & thought leadership agency for venture capital GPs.
    We build a LinkedIn-first presence by training an AI agent on a partner’s writing, books, and talks,
    then pairing voice-true drafts with on-brand visuals, scheduling, and analytics.
    
    **Note:** The monthly charts here are *derived directly from the daily data*
    (month-end values) so the lines always line up.
    All numbers are **made-up** for demonstration.
    """
)

DATA_DIR = Path(__file__).parent

ACCOUNTS = {
    "Account A": {
        "daily_365": DATA_DIR / "account_A_daily_365.csv",
        "daily_30":  DATA_DIR / "account_A_daily_30.csv",
        "monthly":   DATA_DIR / "account_A_monthly_from_daily.csv",
    },
    "Account B": {
        "daily_365": DATA_DIR / "account_B_daily_365.csv",
        "daily_30":  DATA_DIR / "account_B_daily_30.csv",
        "monthly":   DATA_DIR / "account_B_monthly_from_daily.csv",
    },
    "Account C": {
        "daily_365": DATA_DIR / "account_C_daily_365.csv",
        "daily_30":  DATA_DIR / "account_C_daily_30.csv",
        "monthly":   DATA_DIR / "account_C_monthly_from_daily.csv",
    },
}

st.sidebar.header("Display Options")
show_daily30 = st.sidebar.checkbox("Show daily (last 30 days)", value=True)
show_monthly = st.sidebar.checkbox("Show monthly (last 12 months, month-end)", value=True)

for name, paths in ACCOUNTS.items():
    st.subheader(name)
    cols = st.columns(2)

    if show_monthly:
        dfm = pd.read_csv(paths["monthly"], parse_dates=["date"])
        with cols[0]:
            st.caption("Monthly followers (last 12 months; month-end values derived from daily)")
            st.line_chart(dfm.set_index("date")["followers"])
            st.download_button("Download monthly CSV", dfm.to_csv(index=False).encode("utf-8"),
                               file_name=f"{name.replace(' ', '_').lower()}_monthly.csv",
                               mime="text/csv")

    if show_daily30:
        dfd = pd.read_csv(paths["daily_30"], parse_dates=["date"])
        with cols[1]:
            st.caption("Daily followers (last 30 days)")
            st.line_chart(dfd.set_index("date")["followers"])
            st.download_button("Download daily 30 CSV", dfd.to_csv(index=False).encode("utf-8"),
                               file_name=f"{name.replace(' ', '_').lower()}_daily_30.csv",
                               mime="text/csv")

    with st.expander("See daily (last 365 days)"):
        df365 = pd.read_csv(paths["daily_365"], parse_dates=["date"])
        st.line_chart(df365.set_index("date")["followers"])
        st.download_button("Download daily 365 CSV", df365.to_csv(index=False).encode("utf-8"),
                           file_name=f"{name.replace(' ', '_').lower()}_daily_365.csv",
                           mime="text/csv")

    st.markdown("---")

st.markdown("Made-up data for demonstration only.")
