
BLVE.AGENCY — LinkedIn Growth Dashboard (Aligned)

What changed:
- Monthly values are now *derived from the daily series* (month-end) so they line up exactly.
- Provided three CSVs per account:
  * daily_365 (full year)
  * daily_30 (last 30 days)
  * monthly_from_daily (last 12 months derived from daily)

Run:
1) cd blve_app_aligned
2) python -m venv .venv && source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate                            # Windows
3) pip install streamlit pandas
4) python -m streamlit run streamlit_app.py
