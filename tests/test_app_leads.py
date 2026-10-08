"""Click-through tests for the Leads and Find leads tabs.

Uses the fake database and fake AI: no real Supabase or OpenAI calls.
"""

from unittest.mock import patch

import pytest
import streamlit as st

from leads_store import add_companies, get_lead, list_leads
from tests.fake_ai import standard_fake_ai
from tests.fake_database import FakeDatabase
from tests.test_app import make_app, sign_in, clean_environment  # noqa: F401 (fixture)


def button(app, label):
    return next(b for b in app.button if b.label == label)


def has_button(app, label):
    return any(b.label == label for b in app.button)


@pytest.fixture
def world():
    db = FakeDatabase()
    ai = standard_fake_ai()
    with patch("supabase.create_client", return_value=db), \
         patch("ai_client.AIClient", return_value=ai):
        yield db, ai


def open_first(app):
    """Click the first company's Open button on the Leads tab."""
    next(b for b in app.button if b.label == "Open").click()
    app.run()
    return app


def make_ai_app():
    app = make_app()
    app.secrets["OPENAI_API_KEY"] = "sk-test-not-real"
    return app


def test_add_companies_with_duplicates(world):
    db, _ = world
    app = sign_in(make_app())
    form_text = next(t for t in app.text_area if t.label.startswith("One company per line"))
    form_text.input("Acme Software, acme.com\nACME, https://www.acme.com\nBeta Co")
    button(app, "Add companies").click()
    app.run()
    assert any("Added 2 companies" in s.value and "ACME" in s.value for s in app.success)
    assert [lead["name"] for lead in list_leads(db)] == ["Acme Software", "Beta Co"]


def test_without_openai_key_research_explains_setup(world):
    db, ai = world
    add_companies(db, [{"name": "Acme"}])
    app = open_first(sign_in(make_app()))
    assert any("AI research isn't set up" in i.value for i in app.info)
    assert not has_button(app, "Research this company")
    assert ai.calls == []


def test_research_drafts_edit_and_reload(world):
    db, ai = world
    add_companies(db, [{"name": "Palmetto Software"}])
    app = open_first(sign_in(make_ai_app()))

    button(app, "Research this company").click()
    app.run()
    assert any("Research saved" in s.value for s in app.success)
    assert any("Meets criteria" in s.value for s in app.success)

    button(app, "Write drafts").click()
    app.run()
    lead = list_leads(db)[0]
    assert lead["status"] == "draft ready"
    assert any("No signature yet" in w.value for w in app.warning)

    # Mailbox saving is clearly not available yet.
    assert button(app, "Save to mailbox drafts").disabled

    body = next(t for t in app.text_area if t.label == "Email body")
    body.input("My own edited email")
    button(app, "Save edits").click()
    app.run()
    assert any("Edits saved" in s.value for s in app.success)

    # The "write new drafts" button is locked until you tick the replace box.
    assert button(app, "Write new drafts").disabled

    # A brand-new session still shows the edit.
    st.cache_resource.clear()
    fresh = open_first(sign_in(make_ai_app()))
    assert next(t for t in fresh.text_area if t.label == "Email body").value == "My own edited email"
    assert get_lead(db, lead["id"])["status"] == "draft ready"


def test_status_change_saves(world):
    db, _ = world
    add_companies(db, [{"name": "Acme"}])
    app = open_first(sign_in(make_app()))
    status = next(s for s in app.selectbox if s.label == "Review status")
    assert "sent" not in status.options
    status.set_value("manually contacted")
    button(app, "Save status").click()
    app.run()
    assert list_leads(db)[0]["status"] == "manually contacted"


def test_batch_with_failure_then_retry(world):
    db, ai = world
    add_companies(db, [{"name": "Alpha"}, {"name": "Broken Co"}])
    ai.fail_for = {"Broken Co"}
    app = sign_in(make_ai_app())
    button(app, "Process selected").click()
    app.run()
    assert any("1 finished" in w.value and "1 failed" in w.value for w in app.warning)
    assert get_lead(db, 1)["status"] == "draft ready"
    assert get_lead(db, 2)["status"] == "research failed"

    ai.fail_for = set()
    app.run()  # refresh the page so the retry button shows the new count
    button(app, "Retry failed or missing drafts (1)").click()
    app.run()
    assert get_lead(db, 2)["status"] in ("researched", "draft ready")
    research_calls = [c for c in ai.calls if c[0] == "company_research"]
    assert len(research_calls) == 3  # Alpha once, Broken Co twice


def test_discovery_adds_only_sourced_candidates(world):
    db, _ = world
    app = sign_in(make_ai_app())
    button(app, "Search for companies").click()
    app.run()
    names = [lead["name"] for lead in list_leads(db)]
    assert names == ["Found Co", "Second Co"]
    assert list_leads(db)[0]["source"] == "discovered"


def test_export_button_present(world):
    db, _ = world
    add_companies(db, [{"name": "Acme"}])
    app = sign_in(make_app())
    assert app.get("download_button")


def test_filter_narrows_table_and_download(world):
    db, _ = world
    add_companies(db, [{"name": "Acme"}, {"name": "Beta"}])
    app = sign_in(make_app())
    search = next(t for t in app.text_input if t.label == "Search company or owner name")
    search.input("beta")
    app.run()
    assert any("Showing 1 of 2" in c.value for c in app.caption)
    assert len([b for b in app.button if b.label == "Open"]) == 1


def test_discovery_runs_end_to_end_with_no_companies_given(world):
    db, ai = world
    app = sign_in(make_ai_app())
    button(app, "Search for companies").click()
    app.run()
    leads = list_leads(db)
    assert [lead["name"] for lead in leads] == ["Found Co", "Second Co"]
    lead = leads[0]
    assert lead["research"] and lead["qualification_result"]
    assert lead["email_body"] and lead["linkedin_note"]
    assert lead["status"] == "draft ready"  # ready for a person to review; nothing sent
    assert any("Open the Leads tab" in s.value for s in app.success)


def test_snapshot_cards_and_buy_box(world):
    db, ai = world
    add_companies(db, [{"name": "Palmetto Software"}, {"name": "Beta Co"}])
    app = sign_in(make_ai_app())
    # Buy box summary is shown in plain words.
    assert any("South Carolina" in m.value for m in app.markdown)
    assert any("2 to 20 salespeople" in m.value for m in app.markdown)
    # One card per company, each with an Open button.
    assert len([b for b in app.button if b.label == "Open"]) == 2
    assert any("Not researched yet" in m.value for m in app.markdown)

    # Open one, research it, and see it against the buy box.
    open_first(app)
    button(app, "Research this company").click()
    app.run()
    assert any("How it compares with John's buy box" in m.value for m in app.markdown)
    button(app, "← Back to all companies").click()
    app.run()
    assert any("Owner:** Pat Owner (Founder and CEO)" in m.value for m in app.markdown)


# ---- Accounts and John's view-only login --------------------------------------

import auth

VIEWER = "viewer-test-password"


def add_viewer(db):
    auth.create_user(db, "john", VIEWER, "view", "ofarmer")


def test_viewer_sees_leads_only_and_cannot_change_or_spend(world):
    db, ai = world
    add_viewer(db)
    added, _ = add_companies(db, [{"name": "Palmetto Software"}, {"name": "New Co"}])
    # Give the first company research and drafts so there is something to see.
    from batch import draft_one, research_one
    from settings_store import DEFAULT_SETTINGS
    research_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    draft_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    calls_before = len(ai.calls)

    with patch("ai_client.AIClient") as make_client:
        app = sign_in(make_ai_app(), VIEWER, username="john")
        assert [t.label for t in app.tabs] == ["Companies", "Drafts"]  # no Find, no Settings
        assert any("View-only access" in m.value for m in app.markdown)
        assert not any("AI usage" in c.value for c in app.caption)
        assert app.get("download_button")  # can still download

        open_first(app)
        labels = [b.label for b in app.button]
        for forbidden in ["Research this company", "Write drafts", "Write new drafts",
                          "Save status", "Save edits", "Save to mailbox drafts"]:
            assert forbidden not in labels
        assert not app.text_area  # drafts are shown, not editable
        assert not app.selectbox  # status can't be changed
        assert any("Review status:** draft ready" in m.value for m in app.markdown)
        assert any("Quick idea for Palmetto" in c.value for c in app.code)
        make_client.assert_not_called()  # no OpenAI connection for the viewer

    assert len(ai.calls) == calls_before


def test_full_account_gets_everything(world):
    db, _ = world
    auth.create_user(db, "helper", "helper-password-123", "full", "ofarmer")
    app = sign_in(make_ai_app(), "helper-password-123", username="helper")
    assert [t.label for t in app.tabs] == ["Companies", "Drafts", "Find", "Settings"]


def test_oliver_signs_in_with_the_app_password(world):
    app = sign_in(make_ai_app())
    assert [t.label for t in app.tabs] == ["Companies", "Drafts", "Find", "Settings"]
    assert any(m.value == "**ofarmer**" for m in app.sidebar.markdown)


def test_wrong_username_or_password(world):
    db, _ = world
    add_viewer(db)
    for username, password in [("john", "wrong-password"), ("nobody", VIEWER), ("ofarmer", VIEWER), ("", "")]:
        app = sign_in(make_ai_app(), password, username=username)
        assert not app.tabs


def test_too_many_wrong_tries_locks_for_a_minute(world):
    app = make_ai_app()
    app.run()
    for _ in range(5):
        next(t for t in app.text_input if t.label == "Username").input("ofarmer")
        next(t for t in app.text_input if t.label == "Password").input("nope")
        next(b for b in app.button if b.label == "Sign in").click()
        app.run()
    assert any("Too many wrong tries" in e.value for e in app.error)


def test_sign_out(world):
    app = sign_in(make_ai_app())
    next(b for b in app.sidebar.button if b.label == "Sign out").click()
    app.run()
    assert not app.tabs
    assert any(t.label == "Username" for t in app.text_input)


def test_oliver_can_add_a_viewer_in_settings(world):
    db, _ = world
    app = sign_in(make_ai_app())
    next(t for t in app.text_input if t.label == "Username (e.g. john)").input("john")
    next(t for t in app.text_input if t.label.startswith("Password (at least")).input(VIEWER)
    next(b for b in app.button if b.label == "Add account").click()
    app.run()
    assert any("Added john" in s.value for s in app.success)
    users = auth.list_users(db)
    assert [(u["username"], u["role"]) for u in users] == [("john", "view")]
    stored = db.tables["app_users"]
    assert all(VIEWER not in str(row) for row in stored.values())  # only the hash is stored


def test_invite_link_lets_john_create_his_own_account(world):
    db, _ = world
    code = auth.create_invite(db, "view", "John")
    app = make_ai_app()
    app.query_params["invite"] = code
    app.run()
    assert any("Create your account" in s.value for s in app.subheader)
    next(t for t in app.text_input if t.label == "Choose a username").input("john")
    next(t for t in app.text_input if t.label == "Choose a password").input(VIEWER)
    next(t for t in app.text_input if t.label == "Type the password again").input(VIEWER)
    next(b for b in app.button if b.label == "Create account").click()
    app.run()
    assert [t.label for t in app.tabs] == ["Companies", "Drafts"]  # signed in, view only
    assert auth.check_invite(db, code) is None  # used up

    # The same link can't be used again.
    again = make_ai_app()
    again.query_params["invite"] = code
    again.run()
    assert any("isn't valid any more" in e.value for e in again.error)


def test_mismatched_passwords_on_invite(world):
    db, _ = world
    code = auth.create_invite(db, "view")
    app = make_ai_app()
    app.query_params["invite"] = code
    app.run()
    next(t for t in app.text_input if t.label == "Choose a username").input("john")
    next(t for t in app.text_input if t.label == "Choose a password").input(VIEWER)
    next(t for t in app.text_input if t.label == "Type the password again").input("different-one")
    next(b for b in app.button if b.label == "Create account").click()
    app.run()
    assert any("don't match" in e.value for e in app.error)
    assert auth.check_invite(db, code) is not None


def test_oliver_creates_an_invite_link(world):
    db, _ = world
    app = sign_in(make_ai_app())
    next(t for t in app.text_input if t.label.startswith("Who is it for")).input("John")
    next(b for b in app.button if b.label == "Create invite link").click()
    app.run()
    link = next(c.value for c in app.code if "?invite=" in c.value)
    code = link.split("?invite=")[1]
    assert auth.check_invite(db, code)["note"] == "John"


def test_drafts_tab_approve_then_mark_sent(world):
    db, ai = world
    added, _ = add_companies(db, [{"name": "Palmetto Software"}])
    from batch import draft_one, research_one
    from settings_store import DEFAULT_SETTINGS
    research_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    draft_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])

    app = sign_in(make_ai_app())
    drafts = app.tabs[1]
    assert any("Waiting for approval" in m.value for m in drafts.markdown)
    button(app, "Approve").click()
    app.run()
    assert get_lead(db, added[0]["id"])["status"] == "approved"
    assert any("Approved, ready to send by hand" in m.value for m in app.tabs[1].markdown)
    button(app, "I sent it").click()
    app.run()
    assert get_lead(db, added[0]["id"])["status"] == "manually contacted"


def test_viewer_cannot_approve(world):
    db, ai = world
    add_viewer(db)
    added, _ = add_companies(db, [{"name": "Palmetto Software"}])
    from batch import draft_one, research_one
    from settings_store import DEFAULT_SETTINGS
    research_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    draft_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    app = sign_in(make_ai_app(), VIEWER, username="john")
    assert not has_button(app, "Approve")
    assert any("Quick idea for Palmetto" in m.value for m in app.tabs[1].markdown)
