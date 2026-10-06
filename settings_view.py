"""The Settings tab."""

from datetime import datetime

import streamlit as st

from settings_store import (
    DEFAULT_SETTINGS,
    SettingsStoreError,
    load_settings,
    save_settings,
    validate_settings,
)


def settings_tab(db):
    # Show the result of the last save (kept across the page refresh).
    if "settings_message" in st.session_state:
        st.success(st.session_state.pop("settings_message"))

    if db is None:
        st.warning(
            "Not connected to the database yet, so settings can't be saved. "
            "Add SUPABASE_URL and SUPABASE_SECRET_KEY to "
            ".streamlit/secrets.toml (see the README), then restart the app. "
            "The form below shows John's starting settings."
        )
        saved, saved_at = None, None
    else:
        try:
            saved, saved_at = load_settings(db)
        except SettingsStoreError as error:
            st.error(
                f"{error}\n\nCheck your Supabase keys and that you ran "
                "supabase/schema.sql. Settings can't be saved until this works."
            )
            return

    if saved:
        try:
            saved_at = datetime.fromisoformat(saved_at).strftime("%b %d, %Y at %H:%M UTC")
        except (TypeError, ValueError):
            pass  # show it as-is if it's in an unexpected format
        st.caption(f"Last saved: {saved_at}")
        current = saved
    else:
        if db is not None:
            st.info("No settings saved yet. These are John's starting settings.")
        current = DEFAULT_SETTINGS

    with st.form("settings"):
        st.subheader("Who to target")
        geography = st.text_input("Geography", current["geography"])
        industries = st.text_input(
            "Preferred industries (separate with commas)",
            ", ".join(current["preferred_industries"]),
        )
        allow_non_tech = st.checkbox(
            "Also consider strong fits outside these industries", current["allow_non_tech"]
        )

        col1, col2 = st.columns(2)
        revenue_min = col1.number_input(
            "Revenue minimum ($/year)", value=current["revenue_min"], step=500_000
        )
        revenue_max = col2.number_input(
            "Revenue maximum ($/year)", value=current["revenue_max"], step=500_000
        )
        reps_min = col1.number_input(
            "Salespeople minimum", value=current["sales_reps_min"], step=1
        )
        reps_max = col2.number_input(
            "Salespeople maximum", value=current["sales_reps_max"], step=1
        )
        target_role = st.text_input("Person to contact", current["target_role"])

        st.subheader("How to write")
        messaging_style = st.text_area("Messaging style", current["messaging_style"])
        value_proposition = st.text_area(
            "Main value to highlight", current["value_proposition"]
        )
        call_to_action = st.text_area("Call to action", current["call_to_action"])

        st.subheader("Who it's from")
        st.caption("Leave blank until John confirms these. They're never made up.")
        sender_name = st.text_input("Sender name", current["sender_name"])
        sender_title = st.text_input("Sender title", current["sender_title"])
        sender_company = st.text_input("Sender company", current["sender_company"])
        signature = st.text_area("Email signature", current["signature"])
        booking_url = st.text_input(
            "Booking link (optional)", current["booking_url"]
        )

        submitted = st.form_submit_button("Save settings", disabled=db is None)

    if not submitted:
        return

    new_settings = {
        "geography": geography,
        "preferred_industries": industries.split(","),
        "allow_non_tech": allow_non_tech,
        "revenue_min": int(revenue_min),
        "revenue_max": int(revenue_max),
        "sales_reps_min": int(reps_min),
        "sales_reps_max": int(reps_max),
        "target_role": target_role,
        "messaging_style": messaging_style,
        "value_proposition": value_proposition,
        "call_to_action": call_to_action,
        "sender_name": sender_name,
        "sender_title": sender_title,
        "sender_company": sender_company,
        "signature": signature,
        "booking_url": booking_url,
    }

    errors = validate_settings(new_settings)
    if errors:
        for problem in errors:
            st.error(problem)
        st.warning("Nothing was saved. Fix the problems above and try again.")
        return

    try:
        save_settings(db, new_settings)
    except SettingsStoreError as error:
        st.error(f"{error}\n\nNothing was saved.")
        return

    st.session_state["settings_message"] = "Settings saved to the database."
    st.rerun()
