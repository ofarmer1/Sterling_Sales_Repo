"""The app's look: a little extra styling on top of the theme in
.streamlit/config.toml, and the page header."""

import streamlit as st

NAVY = "#1F3A5F"

CSS = f"""
<style>
/* Narrower, calmer page with a bit more breathing room. */
.block-container {{ max-width: 900px; padding-top: 2.5rem; }}
h1, h2, h3, h4 {{ color: {NAVY} !important; letter-spacing: -0.01em; }}
/* Forms on white. */
div[data-testid="stForm"] {{ background: #FFFFFF; }}
/* Tabs: bigger, clearer labels. */
button[data-baseweb="tab"] p {{ font-size: 1.05rem; font-weight: 600; }}
/* Cards (bordered containers): soft shadow and white background. */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: #FFFFFF;
    box-shadow: 0 1px 3px rgba(16, 24, 40, 0.06);
}}
/* Header strip. */
.sterling-header {{
    border-bottom: 3px solid {NAVY};
    padding-bottom: 0.6rem;
    margin-bottom: 1.2rem;
}}
.sterling-header .title {{ font-size: 1.9rem; font-weight: 700; color: {NAVY}; line-height: 1.2; }}
.sterling-header .subtitle {{ color: #5B6472; font-size: 0.95rem; }}
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)


def header(read_only=False):
    subtitle = "Find, research and qualify leads. Drafts are for you to review and send yourself."
    if read_only:
        subtitle = "View-only access: look around and download, but nothing can be changed here."
    st.markdown(
        f"""<div class="sterling-header">
        <div class="title">Sterling Sales</div>
        <div class="subtitle">{subtitle}</div>
        </div>""",
        unsafe_allow_html=True,
    )
