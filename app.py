"""Sterling Sales lead finder.

Finds and researches companies that fit John's ideal client profile,
qualifies them, and drafts outreach for a person to review and send by hand.
Nothing is ever sent from this app.

This file handles sign-in and connections; each tab lives in its own file:
leads_view.py, find_view.py and settings_view.py.
"""

import hmac
import os

import streamlit as st
from supabase import create_client

from ai_client import DEFAULT_BUDGET_USD, DEFAULT_MODEL, AIClient
from find_view import find_tab
from leads_view import leads_tab
from settings_store import DEFAULT_SETTINGS, SettingsStoreError, current_settings
from settings_view import settings_tab


def get_secret(name):
    """Return a secret, or an empty string if it isn't set.

    Looks in Streamlit secrets first (.streamlit/secrets.toml locally, or the
    Secrets box on Streamlit Cloud), then in an environment variable.
    """
    try:
        value = st.secrets.get(name, "")
    except FileNotFoundError:
        # No secrets.toml file exists.
        value = ""
    return value or os.environ.get(name, "")


def password_gate():
    """Show a sign-in form until the right password is entered.

    Returns True when the user is allowed in.
    """
    password = get_secret("APP_PASSWORD")

    # No password configured: refuse to open, so a deployed app is never
    # left open by accident.
    if not password:
        st.title("Sterling Sales")
        st.error(
            "No app password is set, so the app is locked. Add APP_PASSWORD to "
            ".streamlit/secrets.toml (see the README), then restart the app."
        )
        return False

    if st.session_state.get("signed_in"):
        return True

    st.title("Sterling Sales")
    with st.form("sign_in"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        # compare_digest compares safely without leaking timing info.
        if hmac.compare_digest(entered, password):
            st.session_state["signed_in"] = True
            st.rerun()
        else:
            st.error("Wrong password. Try again.")

    return False


@st.cache_resource
def get_database():
    """Connect to Supabase, or return None if the keys aren't set yet."""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_SECRET_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


@st.cache_resource
def get_ai():
    """Connect to OpenAI, or return None if the key isn't set yet."""
    key = get_secret("OPENAI_API_KEY")
    if not key:
        return None
    try:
        budget = float(get_secret("AI_BUDGET_USD") or DEFAULT_BUDGET_USD)
    except ValueError:
        budget = DEFAULT_BUDGET_USD
    return AIClient(key, get_secret("OPENAI_MODEL") or DEFAULT_MODEL, budget)


def main():
    st.set_page_config(page_title="Sterling Sales", page_icon="📇")

    if not password_gate():
        st.stop()

    st.title("Sterling Sales")

    db = get_database()
    ai = get_ai()

    settings = dict(DEFAULT_SETTINGS)
    if db is not None:
        try:
            settings = current_settings(db)
        except SettingsStoreError as error:
            st.error(f"{error}\n\nUsing John's starting settings for now.")

    leads, find, settings_area = st.tabs(["Leads", "Find leads", "Settings"])

    with leads:
        leads_tab(db, ai, settings)

    with find:
        find_tab(db, ai, settings)

    with settings_area:
        settings_tab(db)


main()
