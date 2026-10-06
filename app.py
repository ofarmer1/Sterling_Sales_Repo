"""Sterling Sales lead finder.

Step 1: a password-protected skeleton with three empty tabs.
"""

import hmac
import os

import streamlit as st


def get_app_password():
    """Return the app password, or an empty string if none is set.

    Looks in Streamlit secrets first (used when deployed), then in the
    APP_PASSWORD environment variable (handy for local dev).
    """
    try:
        password = st.secrets.get("APP_PASSWORD", "")
    except FileNotFoundError:
        # No secrets.toml file exists, which is normal for local dev.
        password = ""
    return password or os.environ.get("APP_PASSWORD", "")


def password_gate():
    """Show a sign-in form until the right password is entered.

    Returns True when the user is allowed in.
    """
    password = get_app_password()

    # No password configured: let everyone in (local dev only).
    if not password:
        return True

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


def main():
    st.set_page_config(page_title="Sterling Sales", page_icon="📇")

    if not password_gate():
        st.stop()

    st.title("Sterling Sales")

    leads_tab, find_tab, settings_tab = st.tabs(["Leads", "Find leads", "Settings"])

    with leads_tab:
        st.write("Your researched leads and their draft emails will show up here.")

    with find_tab:
        st.write("Search for new companies that match the ideal client profile here.")

    with settings_tab:
        st.write("Set the ideal client profile and qualification rules here.")


main()
