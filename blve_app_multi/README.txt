
BLVE.AGENCY — Multi-Page LinkedIn Dashboard (Followers · Likes · Comments)

What's new:
- Three pages accessible from header buttons:
  • Followers
  • Likes
  • Comments
- Each page shows the same charts:
  • Monthly (last 12 months, derived from daily month-end)
  • Daily (last 30 days)
  • Daily (last 365 days) in an expander
- CSV downloads provided per account per view.

Run:
1) cd blve_app_multi
2) python -m venv .venv && source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate                             # Windows
3) pip install streamlit pandas
4) python -m streamlit run streamlit_app.py

Notes:
- All data is made up for demonstration.
- Monthly is derived from daily so the series align.
- Replace CSVs with your real exports to use in production.
