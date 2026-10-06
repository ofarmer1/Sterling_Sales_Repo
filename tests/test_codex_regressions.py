"""Regression tests for the problems Codex reproduced on Oct 6, 2026."""

import pytest

from ai_client import AIError
from batch import needs_retry, process_batch, research_one
from leads_store import add_companies, get_lead, set_status
from qualification import DOES_NOT_MEET, MEETS, NEEDS_REVIEW, qualify
from research import check_research
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import SEEN, fact, good_research, standard_fake_ai
from tests.fake_database import FakeDatabase

SETTINGS = dict(DEFAULT_SETTINGS)


def one_sided(low=None, high=None, status="verified"):
    shown = f"over {low}" if high is None else f"under {high}"
    return {**fact(shown, status), "low": low, "high": high}


def result_for(settings=None, **changes):
    research = check_research(good_research(**changes), SEEN)
    return qualify(research, {**SETTINGS, **(settings or {})})


def criterion(result, starts_with):
    return next(c for c in result["criteria"] if c["criterion"].startswith(starts_with))


# 1. Retry when research worked but drafting failed ---------------------------

def test_retry_writes_drafts_that_failed_after_research():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "Palmetto Software"}])
    lead_id = added[0]["id"]
    ai = standard_fake_ai()
    good_drafts = ai.answers["outreach_drafts"]

    def broken(prompt):
        raise AIError("pretend drafting outage")

    ai.answers["outreach_drafts"] = broken
    summary = process_batch(db, ai, SETTINGS, [lead_id])
    assert summary["failed"]
    lead = get_lead(db, lead_id)
    assert lead["research"] and not lead["email_body"]
    assert needs_retry(lead)  # shows up under "Retry failed or missing drafts"

    ai.answers["outreach_drafts"] = good_drafts
    research_calls = sum(1 for name, _ in ai.calls if name == "company_research")
    summary = process_batch(db, ai, SETTINGS, [lead_id])
    lead = get_lead(db, lead_id)
    assert summary["done"] == ["Palmetto Software"]
    assert lead["email_body"]
    assert lead["status"] == "draft ready"
    # Research wasn't paid for twice.
    assert sum(1 for name, _ in ai.calls if name == "company_research") == research_calls


# 2. Qualification must not be over-confident ---------------------------------

def test_revenue_with_only_a_lower_bound_is_not_exact():
    # "Over $10M" could be $50M, so it can't count as inside $1M-$30M.
    result = result_for(annual_revenue=one_sided(low=10_000_000))
    assert criterion(result, "Annual revenue")["result"] == "unknown"
    assert result["result"] == NEEDS_REVIEW


def test_revenue_with_only_an_upper_bound_is_not_exact():
    result = result_for(annual_revenue=one_sided(high=5_000_000))
    assert criterion(result, "Annual revenue")["result"] == "unknown"


def test_one_sided_revenue_clearly_outside_is_still_rejected():
    # "At least $40M" is above the $30M maximum whatever the real number is.
    result = result_for(annual_revenue=one_sided(low=40_000_000))
    assert criterion(result, "Annual revenue")["result"] == "contradicted"


def test_one_sided_sales_team_is_not_exact():
    result = result_for(sales_team_size=one_sided(low=5))
    assert criterion(result, "Sales team")["result"] == "unknown"


def test_estimated_non_tech_is_not_a_firm_rejection():
    result = result_for(
        {"allow_non_tech": False},
        is_tech_company=fact("no", status="estimate"),
        industry=fact("Plumbing supply", status="estimate"),
        what_they_sell=fact("Pipes and fittings", status="estimate"),
    )
    assert criterion(result, "Preferred industry")["result"] == "unknown"
    assert result["result"] == NEEDS_REVIEW


def test_verified_non_tech_is_still_rejected_when_not_allowed():
    result = result_for(
        {"allow_non_tech": False},
        is_tech_company=fact("no"), industry=fact("Plumbing supply"),
        what_they_sell=fact("Pipes and fittings"),
    )
    assert result["result"] == DOES_NOT_MEET


# 3. Preferred industries from Settings are used -------------------------------

def test_changed_industries_are_respected():
    manufacturing = {"preferred_industries": ["Manufacturing"], "allow_non_tech": False}
    # A verified software company no longer counts as a match.
    result = result_for(manufacturing)
    assert criterion(result, "Preferred industry (Manufacturing)")["result"] == "contradicted"

    # A verified manufacturer does.
    result = result_for(
        manufacturing,
        is_tech_company=fact("no"), industry=fact("Precision manufacturing"),
        what_they_sell=fact("Machined parts"),
    )
    assert criterion(result, "Preferred industry")["result"] == "supported"
    assert result["result"] == MEETS


def test_tech_answer_counts_when_tech_is_preferred():
    result = result_for({"preferred_industries": ["SaaS"]}, industry=fact("Healthcare"),
                        what_they_sell=fact("Scheduling platform"))
    assert criterion(result, "Preferred industry")["result"] == "supported"


def test_short_terms_match_whole_words_only():
    result = result_for(
        {"preferred_industries": ["IT"], "allow_non_tech": False},
        is_tech_company=fact("no"), industry=fact("Kitchen fitting"),
        what_they_sell=fact("Kitchens"),
    )
    assert criterion(result, "Preferred industry")["result"] == "contradicted"


def test_no_preferred_industries_is_unknown_not_a_pass():
    result = result_for({"preferred_industries": []})
    assert criterion(result, "Industry")["result"] == "unknown"


# 4. A failed research refresh keeps the approved status ------------------------

def test_failed_refresh_keeps_status_and_old_research():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "Palmetto Software"}])
    lead_id = added[0]["id"]
    ai = standard_fake_ai()
    research_one(db, ai, SETTINGS, lead_id)
    set_status(db, lead_id, "approved")

    ai.fail_for = {"Palmetto Software"}
    with pytest.raises(AIError):
        research_one(db, ai, SETTINGS, lead_id)
    lead = get_lead(db, lead_id)
    assert lead["status"] == "approved"
    assert lead["research"]
    assert "pretend outage" in lead["research_error"]
    assert not needs_retry(lead) or lead["email_body"] == ""


def test_first_research_failure_still_marks_failed():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "Broken Co"}])
    ai = standard_fake_ai()
    ai.fail_for = {"Broken Co"}
    with pytest.raises(AIError):
        research_one(db, ai, SETTINGS, added[0]["id"])
    assert get_lead(db, added[0]["id"])["status"] == "research failed"


# 5. Source labels are honest -----------------------------------------------------

def test_export_calls_sourced_facts_cited_not_verified():
    from export import _value
    assert _value({"owner_name": fact("Pat")}, "owner_name") == "Pat (cited)"
