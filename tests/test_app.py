"""Tests that click through the real app screens using Streamlit's AppTest.

The database is the in-memory FakeDatabase, not a real Supabase project.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.fake_database import FakeDatabase

PASSWORD = "test-password"
SECRET_KEY = "sb_secret_TEST_ONLY_not_real"
APP_FILE = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    # Run from an empty folder so the real .streamlit/secrets.toml (your
    # actual password and database keys) is never used by the tests.
    monkeypatch.chdir(tmp_path)
    for name in ["APP_PASSWORD", "SUPABASE_URL", "SUPABASE_SECRET_KEY"]:
        monkeypatch.delenv(name, raising=False)
    st.cache_resource.clear()  # forget the database connection between tests
    yield
    st.cache_resource.clear()


def make_app(database_keys=True):
    app = AppTest.from_file(APP_FILE, default_timeout=10)
    app.secrets["APP_PASSWORD"] = PASSWORD
    if database_keys:
        app.secrets["SUPABASE_URL"] = "https://test.supabase.co"
        app.secrets["SUPABASE_SECRET_KEY"] = SECRET_KEY
    return app


def sign_in(app, password=PASSWORD):
    app.run()
    app.text_input[0].input(password)
    app.button[0].click()
    app.run()
    return app


def all_text(app):
    parts = [e.value for e in app.markdown] + [e.value for e in app.error]
    parts += [e.value for e in app.warning] + [e.value for e in app.success]
    parts += [e.value for e in app.info] + [e.value for e in app.caption]
    parts += [str(w.value) for w in app.text_input] + [str(w.value) for w in app.text_area]
    return "\n".join(str(p) for p in parts)


def widget(app, label):
    for group in (app.text_input, app.text_area, app.number_input, app.checkbox):
        for w in group:
            if w.label == label:
                return w
    raise KeyError(label)


def save_button(app):
    return next(b for b in app.button if b.label == "Save settings")


# ---- Password ---------------------------------------------------------------

def test_no_password_configured_keeps_app_locked():
    app = AppTest.from_file(APP_FILE).run()
    assert not app.tabs
    assert "app is locked" in app.error[0].value


def test_wrong_password_is_rejected():
    app = sign_in(make_app(), "wrong")
    assert not app.tabs
    assert any("Wrong password" in e.value for e in app.error)


def test_right_password_shows_tabs():
    with patch("supabase.create_client", return_value=FakeDatabase()):
        app = sign_in(make_app())
    assert [t.label for t in app.tabs] == ["Leads", "Find leads", "Settings"]


def test_secrets_never_appear_on_screen():
    with patch("supabase.create_client", return_value=FakeDatabase()):
        app = sign_in(make_app())
    text = all_text(app)
    assert PASSWORD not in text
    assert SECRET_KEY not in text


# ---- Settings ---------------------------------------------------------------

def test_without_database_keys_save_is_disabled():
    app = sign_in(make_app(database_keys=False))
    assert any("Not connected to the database" in w.value for w in app.warning)
    assert save_button(app).disabled
    assert widget(app, "Geography").value == "South Carolina"


def test_save_then_reload_in_fresh_session():
    db = FakeDatabase()
    with patch("supabase.create_client", return_value=db):
        app = sign_in(make_app())
        assert any("No settings saved yet" in i.value for i in app.info)
        widget(app, "Salespeople maximum").set_value(12)
        widget(app, "Sender name").input("Test Sender")
        save_button(app).click()
        app.run()
        assert any("Settings saved" in s.value for s in app.success)

        st.cache_resource.clear()
        fresh = sign_in(make_app())  # a brand-new browser session
    assert widget(fresh, "Salespeople maximum").value == 12
    assert widget(fresh, "Sender name").value == "Test Sender"
    assert any("Last saved" in c.value for c in fresh.caption)


def test_invalid_range_is_not_saved():
    db = FakeDatabase()
    with patch("supabase.create_client", return_value=db):
        app = sign_in(make_app())
        widget(app, "Revenue minimum ($/year)").set_value(40_000_000)
        save_button(app).click()
        app.run()
    assert any("Revenue minimum can't be bigger" in e.value for e in app.error)
    assert not app.success
    assert db.upsert_calls == 0


def test_database_failure_shows_error_not_success():
    db = FakeDatabase()
    with patch("supabase.create_client", return_value=db):
        app = sign_in(make_app())
        db.fail_with = ConnectionError("network down")
        save_button(app).click()
        app.run()
    assert any("Couldn't" in e.value for e in app.error)
    assert not app.success


def test_other_tabs_still_show():
    with patch("supabase.create_client", return_value=FakeDatabase()):
        app = sign_in(make_app())
    assert "draft emails will show up here" in app.tabs[0].markdown[0].value
    assert "Search for new companies" in app.tabs[1].markdown[0].value
