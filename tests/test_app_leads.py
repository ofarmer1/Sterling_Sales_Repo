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
    app = sign_in(make_app())
    assert any("AI research isn't set up" in i.value for i in app.info)
    assert not has_button(app, "Research this company")
    assert ai.calls == []


def test_research_drafts_edit_and_reload(world):
    db, ai = world
    add_companies(db, [{"name": "Palmetto Software"}])
    app = sign_in(make_ai_app())

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
    fresh = sign_in(make_ai_app())
    assert next(t for t in fresh.text_area if t.label == "Email body").value == "My own edited email"
    assert get_lead(db, lead["id"])["status"] == "draft ready"


def test_status_change_saves(world):
    db, _ = world
    add_companies(db, [{"name": "Acme"}])
    app = sign_in(make_app())
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
    assert names == ["Found Co"]
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
    opener = next(s for s in app.selectbox if s.label == "Open a company")
    assert len(opener.options) == 1
