"""Show a finished report: downloads, the report itself, and its evidence trail."""

from collections import defaultdict
from urllib.parse import urlparse

import streamlit as st

from launchscout.pdf import report_pdf

ICONS = {"price": ":material/sell:", "rating": ":material/star:", "like": ":material/thumb_up:",
         "complaint": ":material/thumb_down:"}


@st.cache_data
def _pdf(report_md: str) -> bytes:
    return report_pdf(report_md)


def show_report(report_md: str, trail: list[dict], file_stem: str, key: str) -> None:
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("Markdown", report_md, f"{file_stem}.md", "text/markdown",
                       icon=":material/download:", key=f"md_{key}", width="stretch")
    c2.download_button("PDF", _pdf(report_md), f"{file_stem}.pdf", "application/pdf",
                       icon=":material/picture_as_pdf:", key=f"pdf_{key}", width="stretch")

    report_tab, trail_tab = st.tabs(["Report", f"Evidence trail ({len(trail)})"])
    with report_tab:
        st.markdown(report_md)
    with trail_tab:
        show_trail(trail)


def show_trail(trail: list[dict]) -> None:
    st.caption("Every price, rating and customer quote in the report, with the exact words it came from. "
               "Claims no page supported were removed before the report was written.")
    if not trail:
        st.info("No evidence trail was saved for this report.")
        return
    by_competitor: dict[str, list[dict]] = defaultdict(list)
    for item in trail:
        by_competitor[item["competitor"]].append(item)
    for competitor, items in by_competitor.items():
        with st.expander(f"{competitor} · {len(items)} claims", icon=":material/fact_check:"):
            for item in items:
                site = urlparse(item["source_url"] or "").netloc.removeprefix("www.")
                st.markdown(f"{ICONS.get(item['kind'], '')} **{item['claim']}**")
                if item["excerpt"]:
                    st.markdown(f"> {item['excerpt']}")
                st.caption(f"{item['from'].capitalize()} · [{site}]({item['source_url']})")
