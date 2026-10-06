"""Load, check and save John's settings.

The settings live in one row of the Supabase table `app_settings`
(see supabase/schema.sql). This file has no Streamlit code in it, so the
rules can be tested on their own (see tests/test_settings_store.py).
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

TABLE = "app_settings"
ROW_ID = 1

# John's confirmed starting settings. They're shown until settings are saved.
DEFAULT_SETTINGS = {
    "geography": "South Carolina",
    "preferred_industries": ["Tech", "Software"],
    "allow_non_tech": True,
    "revenue_min": 1_000_000,
    "revenue_max": 30_000_000,
    "sales_reps_min": 2,
    "sales_reps_max": 20,
    "target_role": "Owner",
    "messaging_style": (
        "Short and direct. Funny where it fits, not too serious. No buzzwords."
    ),
    "value_proposition": (
        "What the company could gain by getting more of its reps to quota."
    ),
    "call_to_action": (
        "Ask for a call, or a reply with interest and two good times for a call."
    ),
    # Sender details stay blank until they're provided. Never make these up.
    "sender_name": "",
    "sender_title": "",
    "sender_company": "",
    "signature": "",
    "booking_url": "",
}

# The setting names, in the order they're stored.
SETTING_FIELDS = list(DEFAULT_SETTINGS.keys())


class SettingsStoreError(Exception):
    """Raised when the database can't be read or written."""


def validate_settings(settings):
    """Check settings before saving. Returns a list of problems (empty if fine)."""
    errors = []

    if not settings["geography"].strip():
        errors.append("Geography can't be empty.")
    if not settings["target_role"].strip():
        errors.append("Target role can't be empty.")

    for label, low_key, high_key in [
        ("Revenue", "revenue_min", "revenue_max"),
        ("Sales team size", "sales_reps_min", "sales_reps_max"),
    ]:
        low, high = settings[low_key], settings[high_key]
        if not isinstance(low, int) or not isinstance(high, int):
            errors.append(f"{label} minimum and maximum must be whole numbers.")
        elif low < 0 or high < 0:
            errors.append(f"{label} can't be negative.")
        elif low > high:
            errors.append(f"{label} minimum can't be bigger than the maximum.")

    url = settings["booking_url"].strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("Booking URL must start with http:// or https://.")

    return errors


def clean_settings(settings):
    """Trim spaces and drop empty industries so we store tidy values."""
    cleaned = dict(settings)
    for key, value in cleaned.items():
        if isinstance(value, str):
            cleaned[key] = value.strip()
    cleaned["preferred_industries"] = [
        item.strip() for item in settings["preferred_industries"] if item.strip()
    ]
    return cleaned


def load_settings(client):
    """Read the saved settings.

    Returns (settings, saved_at). If nothing has been saved yet, returns
    (None, None). Raises SettingsStoreError if the database can't be reached.
    """
    try:
        response = (
            client.table(TABLE).select("*").eq("id", ROW_ID).limit(1).execute()
        )
    except Exception as error:
        raise SettingsStoreError(f"Couldn't load settings: {error}") from error

    if not response.data:
        return None, None

    row = response.data[0]
    settings = {field: row.get(field, DEFAULT_SETTINGS[field]) for field in SETTING_FIELDS}
    # Postgres may return None for an empty list; treat it as empty.
    settings["preferred_industries"] = settings["preferred_industries"] or []
    return settings, row.get("updated_at")


def save_settings(client, settings):
    """Validate and save settings. Returns the row the database saved.

    Raises ValueError if the settings are invalid, and SettingsStoreError if
    the database write fails or doesn't confirm the save.
    """
    settings = clean_settings(settings)
    errors = validate_settings(settings)
    if errors:
        raise ValueError(" ".join(errors))

    # Record when this save happened (in UTC).
    row = {"id": ROW_ID, **settings, "updated_at": datetime.now(timezone.utc).isoformat()}

    try:
        response = client.table(TABLE).upsert(row).execute()
    except Exception as error:
        raise SettingsStoreError(f"Couldn't save settings: {error}") from error

    # Only call it a success if the database sent the saved row back.
    if not response.data:
        raise SettingsStoreError("The database didn't confirm the save.")
    return response.data[0]
