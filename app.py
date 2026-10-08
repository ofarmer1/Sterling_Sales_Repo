"""Sterling Sales lead finder.

Finds and researches companies that fit John's ideal client profile,
qualifies them, and drafts outreach for a person to review and send by hand.
Nothing is ever sent from this app.

This file handles sign-in and connections; each tab lives in its own file:
leads_view.py, find_view.py and settings_view.py.
"""

import os
import time

import streamlit as st
from supabase import create_client

import auth
import style
from accounts_view import accounts_section
from ai_client import DEFAULT_BUDGET_USD, DEFAULT_MODEL, AIClient
from find_view import find_tab
from leads_view import drafts_tab, leads_tab
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


COOKIE_NAME = "sterling_session"
MAX_FAILED_SIGN_INS = 5
LOCKOUT_SECONDS = 60


def admin_username():
    return (get_secret("ADMIN_USERNAME") or "ofarmer").strip().lower()


def set_cookie(token, days):
    """Ask the browser to keep (or, with days=0, forget) the sign-in token."""
    max_age = int(days * 24 * 60 * 60)
    # The token is our own random letters and numbers, never user input.
    st.iframe(
        f"""<script>
        const secure = window.parent.location.protocol === 'https:' ? '; Secure' : '';
        window.parent.document.cookie =
            '{COOKIE_NAME}={token}; max-age={max_age}; path=/; SameSite=Strict' + secure;
        </script>""",
        height=1,
    )


def sign_in_gate(db):
    """Show the sign-in form until someone signs in.

    Returns (username, role) once signed in, or None. Role is "full" or "view".
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
        return None

    if st.session_state.get("role"):
        return st.session_state["username"], st.session_state["role"]

    # A remembered login from an earlier visit on this device.
    remembered = auth.restore_session(db, st.context.cookies.get(COOKIE_NAME), admin_username())
    if remembered:
        st.session_state["username"], st.session_state["role"] = remembered
        st.session_state["token"] = st.context.cookies.get(COOKIE_NAME)
        return remembered

    st.title("Sterling Sales")
    st.caption("Lead finder for Sterling Sales Training & Consulting")

    invite_code = st.query_params.get("invite")
    if invite_code:
        return invite_page(db, invite_code)

    locked_until = st.session_state.get("locked_until", 0)
    if time.time() < locked_until:
        st.error(f"Too many wrong tries. Wait {int(locked_until - time.time())} seconds and try again.")
        return None

    # Keep the sign-in box narrow on wide screens.
    form_column, _ = st.columns([1, 1])
    with form_column, st.form("sign_in"):
        username = st.text_input("Username")
        entered = st.text_input("Password", type="password")
        remember = st.checkbox(
            f"Keep me signed in on this device for {auth.REMEMBER_DAYS} days",
            disabled=db is None,
        )
        submitted = st.form_submit_button("Sign in", type="primary")

    if not submitted:
        return None
    try:
        role = auth.authenticate(db, username, entered, admin_username(), password)
    except auth.AuthError as error:
        st.error(str(error))
        return None
    if role is None:
        failures = st.session_state.get("failures", 0) + 1
        st.session_state["failures"] = failures
        if failures >= MAX_FAILED_SIGN_INS:
            st.session_state["locked_until"] = time.time() + LOCKOUT_SECONDS
            st.session_state["failures"] = 0
            st.error(f"Too many wrong tries. Wait {LOCKOUT_SECONDS} seconds and try again.")
        else:
            st.error("Wrong username or password. Try again.")
        return None

    st.session_state["failures"] = 0
    st.session_state["username"] = username.strip().lower()
    st.session_state["role"] = role
    if remember:
        try:
            st.session_state["new_token"] = auth.create_session(db, st.session_state["username"], role)
        except auth.AuthError as error:
            st.warning(f"{error} You're signed in, but will need to sign in again next time.")
    st.rerun()


def invite_page(db, code):
    """First visit from an invite link: choose your own username and password."""
    invite = auth.check_invite(db, code)
    if invite is None:
        st.error("This invite link isn't valid any more (it may have been used or expired). Ask Oliver for a new one.")
        if st.button("Go to sign in"):
            st.query_params.clear()
            st.rerun()
        return None

    st.subheader("Create your account")
    st.caption(f"Pick a username and a password (at least {auth.MIN_PASSWORD_LENGTH} characters). You'll use them to sign in from now on.")
    form_column, _ = st.columns([1, 1])
    with form_column, st.form("accept_invite"):
        username = st.text_input("Choose a username")
        password = st.text_input("Choose a password", type="password")
        again = st.text_input("Type the password again", type="password")
        remember = st.checkbox(f"Keep me signed in on this device for {auth.REMEMBER_DAYS} days", value=True)
        submitted = st.form_submit_button("Create account", type="primary")
    if not submitted:
        return None
    if password != again:
        st.error("The two passwords don't match.")
        return None
    try:
        role = auth.accept_invite(db, code, username, password, admin_username())
    except auth.AuthError as error:
        st.error(str(error))
        return None

    st.query_params.clear()
    st.session_state["username"] = username.strip().lower()
    st.session_state["role"] = role
    if remember:
        try:
            st.session_state["new_token"] = auth.create_session(db, st.session_state["username"], role)
        except auth.AuthError:
            pass
    st.rerun()


def sign_out():
    auth.end_session(get_database(), st.session_state.get("token"))
    for key in ["username", "role", "token", "new_token"]:
        st.session_state.pop(key, None)
    st.session_state["clear_cookie"] = True


def account_sidebar(username, role):
    with st.sidebar:
        st.markdown(f"**{username}**")
        st.caption(auth.ROLES[role])
        if st.button("Sign out"):
            sign_out()
            st.rerun()


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
    style.apply()

    db = get_database()

    # Finish a sign-out: tell the browser to forget the remembered login.
    if st.session_state.pop("clear_cookie", False):
        set_cookie("", 0)

    signed_in = sign_in_gate(db)
    if signed_in is None:
        st.stop()
    username, role = signed_in
    read_only = role == "view"

    # Finish a "keep me signed in": give the browser its token.
    if "new_token" in st.session_state:
        st.session_state["token"] = st.session_state.pop("new_token")
        set_cookie(st.session_state["token"], auth.REMEMBER_DAYS)

    account_sidebar(username, role)
    style.header(read_only)

    # View-only users never get the AI connection, so they can't spend money.
    ai = None if read_only else get_ai()

    settings = dict(DEFAULT_SETTINGS)
    if db is not None:
        try:
            settings = current_settings(db)
        except SettingsStoreError as error:
            st.error(f"{error}\n\nUsing John's starting settings for now.")

    if read_only:
        companies, drafts = st.tabs(["Companies", "Drafts"])
        with companies:
            leads_tab(db, None, settings, read_only=True)
        with drafts:
            drafts_tab(db, read_only=True)
        return

    companies, drafts, find, settings_area = st.tabs(["Companies", "Drafts", "Find", "Settings"])

    with companies:
        leads_tab(db, ai, settings)

    with drafts:
        drafts_tab(db)

    with find:
        find_tab(db, ai, settings)

    with settings_area:
        settings_tab(db)
        accounts_section(db, admin_username())


main()
