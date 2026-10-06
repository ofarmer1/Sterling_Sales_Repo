"""Tests for saving leads, drafts, batches and retries (fake database and AI)."""

import pytest

from batch import MAX_BATCH, draft_one, process_batch, research_one
from discovery import discover_companies
from drafting import SIGNATURE_MISSING, add_signature, draft_warnings, generate_drafts
from leads_store import (
    LeadsStoreError, STATUSES, add_companies, company_key, get_lead, list_leads,
    save_draft_edits, save_generated_drafts, set_status, usage_totals,
)
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import good_research, standard_fake_ai, fact, SEEN
from tests.fake_database import FakeDatabase

SETTINGS = dict(DEFAULT_SETTINGS)


def setup(*names):
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": n, "website": ""} for n in names])
    return db, [row["id"] for row in added]


# ---- Duplicates ---------------------------------------------------------------

def test_company_key_matches_domains_and_names():
    assert company_key("A", "https://www.acme.com/about") == company_key("B", "acme.com")
    assert company_key("Acme, Inc.") == company_key("acme")
    assert company_key("Acme LLC") == company_key("ACME Co")


def test_duplicates_are_skipped():
    db = FakeDatabase()
    add_companies(db, [{"name": "Acme Software", "website": "acme.com"}])
    added, skipped = add_companies(db, [
        {"name": "ACME", "website": "https://www.acme.com"},  # same website
        {"name": "Beta", "website": ""},
        {"name": "Beta Inc.", "website": ""},  # same name, same batch
    ])
    assert [row["name"] for row in added] == ["Beta"]
    assert skipped == ["ACME", "Beta Inc."]
    assert len(list_leads(db)) == 2


# ---- Research one -------------------------------------------------------------

def test_research_one_saves_research_and_qualification():
    db, (lead_id,) = setup("Palmetto Software")
    lead = research_one(db, standard_fake_ai(), SETTINGS, lead_id)
    assert lead["status"] == "researched"
    assert lead["qualification_result"] == "Meets criteria"
    assert lead["researched_at"]
    assert lead["research_sources"] == sorted(SEEN)
    assert usage_totals(db)["requests"] == 1


def test_failed_research_is_recorded_not_lost():
    db, (lead_id,) = setup("Broken Co")
    ai = standard_fake_ai()
    ai.fail_for = {"Broken Co"}
    with pytest.raises(Exception):
        research_one(db, ai, SETTINGS, lead_id)
    lead = get_lead(db, lead_id)
    assert lead["status"] == "research failed"
    assert "pretend outage" in lead["research_error"]


def test_usage_log_failure_does_not_lose_research():
    db, (lead_id,) = setup("Palmetto Software")
    db.fail_tables = {"usage_log"}
    lead = research_one(db, standard_fake_ai(), SETTINGS, lead_id)
    assert lead["research"]


# ---- Drafts -------------------------------------------------------------------

def test_signature_placeholder_when_missing():
    assert add_signature("Hi", SETTINGS).endswith(SIGNATURE_MISSING)
    assert add_signature("Hi", {**SETTINGS, "signature": "John"}).endswith("John")


def test_draft_prompt_only_uses_known_facts_and_booking_link():
    ai = standard_fake_ai()
    research = good_research(public_email={"value": None, "status": "unknown", "sources": [], "note": ""})
    generate_drafts(ai, "Palmetto", research, {**SETTINGS, "booking_url": "https://cal.example/john"})
    prompt = ai.calls[-1][1]
    assert "Pat Owner" in prompt
    assert "public email" not in prompt
    assert "https://cal.example/john" in prompt


def test_no_booking_link_is_invented():
    ai = standard_fake_ai()
    generate_drafts(ai, "Palmetto", good_research(), SETTINGS)
    assert "Booking link" not in ai.calls[-1][1]


def test_estimates_are_labelled_for_the_writer():
    ai = standard_fake_ai()
    generate_drafts(ai, "P", good_research(industry=fact("Software", status="estimate")), SETTINGS)
    assert "estimate, don't state as fact" in ai.calls[-1][1]


def test_long_linkedin_note_is_flagged():
    warnings = draft_warnings({"email_body": "Hi\n\nJohn", "linkedin_note": "x" * 301})
    assert any("301 characters" in w for w in warnings)


def test_drafts_save_and_status():
    db, (lead_id,) = setup("Palmetto Software")
    ai = standard_fake_ai()
    research_one(db, ai, SETTINGS, lead_id)
    lead = draft_one(db, ai, SETTINGS, lead_id)
    assert lead["status"] == "draft ready"
    assert lead["email_subject"] == "Quick idea for Palmetto"
    assert lead["email_body"].endswith(SIGNATURE_MISSING)


def test_drafts_need_research_first():
    db, (lead_id,) = setup("New Co")
    with pytest.raises(LeadsStoreError):
        draft_one(db, standard_fake_ai(), SETTINGS, lead_id)


def test_edits_are_never_overwritten_by_accident():
    db, (lead_id,) = setup("Palmetto Software")
    ai = standard_fake_ai()
    research_one(db, ai, SETTINGS, lead_id)
    draft_one(db, ai, SETTINGS, lead_id)
    save_draft_edits(db, lead_id, "My subject", "My body", "My note")

    with pytest.raises(LeadsStoreError, match="on purpose"):
        draft_one(db, ai, SETTINGS, lead_id)
    assert get_lead(db, lead_id)["email_body"] == "My body"

    # Researching again keeps the edited drafts too.
    research_one(db, ai, SETTINGS, lead_id)
    assert get_lead(db, lead_id)["email_body"] == "My body"

    # Replacing on purpose works.
    draft_one(db, ai, SETTINGS, lead_id, replace_protected=True)
    assert get_lead(db, lead_id)["email_subject"] == "Quick idea for Palmetto"


def test_approved_drafts_are_protected_and_status_kept():
    db, (lead_id,) = setup("Palmetto Software")
    ai = standard_fake_ai()
    research_one(db, ai, SETTINGS, lead_id)
    draft_one(db, ai, SETTINGS, lead_id)
    set_status(db, lead_id, "approved")
    with pytest.raises(LeadsStoreError):
        save_generated_drafts(db, lead_id, {"email_subject": "x", "email_body": "y", "linkedin_note": "z"})
    research_one(db, ai, SETTINGS, lead_id)
    assert get_lead(db, lead_id)["status"] == "approved"


def test_there_is_no_sent_status():
    assert "sent" not in STATUSES
    with pytest.raises(ValueError):
        set_status(FakeDatabase(), 1, "sent")


def test_failed_save_of_edits_raises():
    db, (lead_id,) = setup("Palmetto Software")
    db.fail_with = ConnectionError("down")
    with pytest.raises(LeadsStoreError):
        save_draft_edits(db, lead_id, "s", "b", "n")


# ---- Batches and retries ------------------------------------------------------

def test_batch_keeps_going_when_one_company_fails():
    db, ids = setup("Alpha", "Broken Co", "Gamma")
    ai = standard_fake_ai()
    ai.fail_for = {"Broken Co"}
    progress = []
    summary = process_batch(db, ai, SETTINGS, ids, on_progress=lambda *a: progress.append(a))
    assert summary["done"] == ["Alpha", "Gamma"]
    assert summary["failed"][0][0] == "Broken Co"
    assert len(progress) == 3
    assert get_lead(db, ids[0])["email_body"]  # drafts written for a fit


def test_retry_only_redoes_failures():
    db, ids = setup("Alpha", "Broken Co")
    ai = standard_fake_ai()
    ai.fail_for = {"Broken Co"}
    process_batch(db, ai, SETTINGS, ids)
    research_calls_before = sum(1 for name, _ in ai.calls if name == "company_research")

    ai.fail_for = set()
    summary = process_batch(db, ai, SETTINGS, ids)  # same list again
    research_calls_after = sum(1 for name, _ in ai.calls if name == "company_research")
    assert summary["skipped"] == ["Alpha"]
    assert summary["done"] == ["Broken Co"]
    assert research_calls_after - research_calls_before == 1


def test_no_drafts_for_companies_that_do_not_fit():
    db, (lead_id,) = setup("Far Away Co")
    ai = standard_fake_ai()
    ai.answers["company_research"] = lambda p: (good_research(state=fact("TX"), south_carolina_evidence={"value": None, "status": "unknown", "sources": [], "note": ""}), SEEN)
    process_batch(db, ai, SETTINGS, [lead_id])
    lead = get_lead(db, lead_id)
    assert lead["qualification_result"] == "Does not meet criteria"
    assert lead["email_body"] == ""


def test_batch_is_capped():
    db, ids = setup(*[f"Company {i}" for i in range(MAX_BATCH + 3)])
    summary = process_batch(db, standard_fake_ai(), SETTINGS, ids, write_drafts=False)
    assert len(summary["done"]) == MAX_BATCH


# ---- Discovery ----------------------------------------------------------------

def test_discovery_drops_candidates_without_real_sources():
    candidates, usage = discover_companies(standard_fake_ai(), SETTINGS, 5)
    assert [c["name"] for c in candidates] == ["Found Co"]
    assert candidates[0]["reason"] == "SC SaaS firm"


def test_discovery_count_is_capped_and_existing_excluded():
    ai = standard_fake_ai()
    discover_companies(ai, SETTINGS, 500, ["Already Here"])
    prompt = ai.calls[-1][1]
    assert "Find 20 companies" in prompt
    assert "Already Here" in prompt


def test_booking_link_is_always_in_the_email_when_set():
    with_link = {**SETTINGS, "booking_url": "https://cal.example/john"}
    body = add_signature("Hi Pat, worth a chat?", with_link)
    assert "https://cal.example/john" in body
    # Not added twice if the AI already included it.
    once = add_signature("Book here: https://cal.example/john", with_link)
    assert once.count("https://cal.example/john") == 1
    # No link set: none invented.
    assert "http" not in add_signature("Hi", SETTINGS)
