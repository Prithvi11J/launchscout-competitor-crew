"""Turn the markdown report into a PDF a founder can download and share."""

import markdown
from fpdf import FPDF

# fpdf2's built-in fonts cover Latin-1 only; replace the few characters reports use outside it.
REPLACEMENTS = {"₹": "Rs ", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "•": "-"}


def _latin1(text: str) -> str:
    for char, plain in REPLACEMENTS.items():
        text = text.replace(char, plain)
    return text.encode("latin-1", "replace").decode("latin-1")


def report_pdf(report_md: str) -> bytes:
    html = markdown.markdown(_latin1(report_md), extensions=["tables"])
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    pdf.write_html(html)
    return bytes(pdf.output())
