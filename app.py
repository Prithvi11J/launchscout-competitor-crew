"""LaunchScout: entry point.

    .venv\\Scripts\\streamlit run app.py

This file only sets up the frame (page config, logo, navigation). Each screen is its own
script in app_pages/, and shared state lives in ui/state.py.
"""

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"  # absolute, so the app works from any working directory

st.set_page_config(page_title="LaunchScout · competitor research for local founders",
                   page_icon=str(ASSETS / "mark.svg"), layout="wide", initial_sidebar_state="collapsed")
st.logo(str(ASSETS / "mark.svg"), size="large")

pages = [
    st.Page("app_pages/research.py", title="Research", icon=":material/travel_explore:", default=True),
    st.Page("app_pages/examples.py", title="Example reports", icon=":material/description:"),
    st.Page("app_pages/how_it_works.py", title="How it works", icon=":material/account_tree:"),
]
st.navigation(pages, position="top").run()
