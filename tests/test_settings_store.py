"""Tests for the settings rules and storage (no real database needed)."""

import pytest

from settings_store import (
    DEFAULT_SETTINGS,
    SettingsStoreError,
    load_settings,
    save_settings,
    validate_settings,
)
from tests.fake_database import FakeDatabase


def settings(**changes):
    return {**DEFAULT_SETTINGS, **changes}


def test_johns_defaults_are_valid():
    assert validate_settings(DEFAULT_SETTINGS) == []
    assert DEFAULT_SETTINGS["geography"] == "South Carolina"
    assert DEFAULT_SETTINGS["revenue_min"] == 1_000_000
    assert DEFAULT_SETTINGS["revenue_max"] == 30_000_000
    assert DEFAULT_SETTINGS["sales_reps_min"] == 2
    assert DEFAULT_SETTINGS["sales_reps_max"] == 20
    assert DEFAULT_SETTINGS["target_role"] == "Owner"


def test_sender_details_start_blank():
    for field in ["sender_name", "sender_title", "sender_company", "signature", "booking_url"]:
        assert DEFAULT_SETTINGS[field] == ""


def test_min_equal_to_max_is_allowed():
    assert validate_settings(settings(sales_reps_min=5, sales_reps_max=5)) == []


def test_min_bigger_than_max_is_rejected():
    errors = validate_settings(settings(revenue_min=30_000_001, revenue_max=30_000_000))
    assert any("Revenue minimum" in e for e in errors)
    errors = validate_settings(settings(sales_reps_min=21, sales_reps_max=20))
    assert any("Sales team size minimum" in e for e in errors)


def test_negative_numbers_are_rejected():
    assert validate_settings(settings(revenue_min=-1))
    assert validate_settings(settings(sales_reps_min=-1))


def test_blank_required_fields_are_rejected():
    assert validate_settings(settings(geography="   "))
    assert validate_settings(settings(target_role=""))


def test_booking_url_must_be_a_web_link():
    assert validate_settings(settings(booking_url="calendly.com/john"))
    assert validate_settings(settings(booking_url="javascript:alert(1)"))
    assert validate_settings(settings(booking_url="https://calendly.com/john")) == []


def test_nothing_saved_yet_returns_none():
    assert load_settings(FakeDatabase()) == (None, None)


def test_save_then_load_in_a_fresh_session():
    db = FakeDatabase()
    save_settings(db, settings(geography="  North Carolina ", sales_reps_max=15))

    # A "fresh session" just means reading from the database again.
    loaded, saved_at = load_settings(db)
    assert loaded["geography"] == "North Carolina"  # spaces trimmed
    assert loaded["sales_reps_max"] == 15
    assert saved_at is not None


def test_empty_industries_are_dropped():
    db = FakeDatabase()
    save_settings(db, settings(preferred_industries=["Tech", " ", "", " SaaS "]))
    loaded, _ = load_settings(db)
    assert loaded["preferred_industries"] == ["Tech", "SaaS"]


def test_invalid_settings_never_reach_the_database():
    db = FakeDatabase()
    with pytest.raises(ValueError):
        save_settings(db, settings(revenue_min=50, revenue_max=10))
    assert db.upsert_calls == 0


def test_database_outage_raises_clear_error():
    db = FakeDatabase()
    db.fail_with = ConnectionError("network down")
    with pytest.raises(SettingsStoreError, match="Couldn't save"):
        save_settings(db, DEFAULT_SETTINGS)
    with pytest.raises(SettingsStoreError, match="Couldn't load"):
        load_settings(db)


def test_unconfirmed_write_is_not_a_success():
    db = FakeDatabase()
    db.confirm_writes = False
    with pytest.raises(SettingsStoreError, match="didn't confirm"):
        save_settings(db, DEFAULT_SETTINGS)
