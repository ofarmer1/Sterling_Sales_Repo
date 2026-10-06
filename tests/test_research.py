"""Tests for checking research sources (no real AI calls)."""

from research import RESEARCH_SCHEMA, check_research, normalize_url, research_company
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import SEEN, fact, good_research, range_fact, standard_fake_ai, unknown_fact


def test_good_research_keeps_verified_facts():
    cleaned = check_research(good_research(), SEEN)
    assert cleaned["owner_name"]["status"] == "verified"
    assert cleaned["owner_name"]["value"] == "Pat Owner"
    assert cleaned["annual_revenue"]["low"] == 5_000_000


def test_sources_the_search_never_saw_are_removed():
    data = good_research(owner_name=fact("Pat Owner", sources=["https://invented.example/page"]))
    cleaned = check_research(data, SEEN)
    owner = cleaned["owner_name"]
    assert owner["sources"] == []
    assert owner["status"] == "estimate"  # downgraded: no confirmed source
    assert "couldn't be confirmed" in owner["note"]


def test_verified_without_any_source_becomes_estimate():
    cleaned = check_research(good_research(industry=fact("Software", sources=[])), SEEN)
    assert cleaned["industry"]["status"] == "estimate"


def test_unknown_facts_have_no_value():
    data = good_research(owner_name={"value": "Someone", "status": "unknown", "sources": [], "note": ""})
    assert check_research(data, SEEN)["owner_name"]["value"] is None


def test_empty_value_becomes_unknown():
    cleaned = check_research(good_research(owner_name=fact("")), SEEN)
    assert cleaned["owner_name"]["status"] == "unknown"


def test_guessed_email_is_dropped():
    data = good_research(public_email=fact("info@palmetto.example", status="estimate"))
    cleaned = check_research(data, SEEN)
    assert cleaned["public_email"]["status"] == "unknown"
    assert cleaned["public_email"]["value"] is None


def test_verified_email_with_real_source_is_kept():
    data = good_research(public_email=fact("info@palmetto.example"))
    assert check_research(data, SEEN)["public_email"]["value"] == "info@palmetto.example"


def test_estimated_revenue_stays_an_estimate():
    data = good_research(annual_revenue=range_fact(2_000_000, 4_000_000, status="estimate"))
    assert check_research(data, SEEN)["annual_revenue"]["status"] == "estimate"


def test_unsourced_outreach_context_is_dropped():
    data = good_research(outreach_context=[
        {"fact": "Real news", "sources": ["https://example.com/news"]},
        {"fact": "Invented news", "sources": ["https://nowhere.example"]},
    ])
    facts = [item["fact"] for item in check_research(data, SEEN)["outreach_context"]]
    assert facts == ["Real news"]


def test_missing_fields_become_unknown():
    cleaned = check_research({}, [])
    assert cleaned["owner_name"]["status"] == "unknown"
    assert cleaned["sales_team_size"]["low"] is None


def test_url_matching_ignores_small_differences():
    assert normalize_url("https://www.Example.com/about/") == normalize_url("http://example.com/about#team")


def test_research_company_records_time_and_sources():
    ai = standard_fake_ai()
    research, seen, usage = research_company(ai, "Palmetto Software", "palmetto.example", DEFAULT_SETTINGS)
    assert research["researched_at"]
    assert seen == sorted(SEEN)
    assert usage.web_searches == 2
    assert "Company: Palmetto Software" in ai.calls[0][1]


def test_schema_is_strict():
    # OpenAI's strict mode needs every property listed as required.
    assert set(RESEARCH_SCHEMA["required"]) == set(RESEARCH_SCHEMA["properties"])
    assert RESEARCH_SCHEMA["additionalProperties"] is False
