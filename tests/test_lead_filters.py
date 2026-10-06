"""Tests for filtering leads."""

from lead_filters import filter_leads
from tests.fake_ai import fact, range_fact, unknown_fact
from tests.fake_database import LEAD_DEFAULTS


def lead(name, result="", status="new", source="provided", **research):
    return {**LEAD_DEFAULTS, "name": name, "qualification_result": result,
            "status": status, "source": source, "research": research or None}


LEADS = [
    lead("Palmetto Software", "Meets criteria", "draft ready",
         industry=fact("Healthcare software"), headquarters=fact("Greenville, SC"), state=fact("SC"),
         owner_name=fact("Pat Owner"),
         annual_revenue=range_fact(5_000_000, 8_000_000), sales_team_size=range_fact(4, 6)),
    lead("Big Steel", "Does not meet criteria", "researched", "discovered",
         industry=fact("Steel"), headquarters=fact("Charlotte, NC"), state=fact("NC"),
         annual_revenue=range_fact(90_000_000, 120_000_000), sales_team_size=range_fact(40, 50)),
    lead("Mystery Co", "Needs review", "researched",
         industry=fact("Software"), headquarters=fact("Columbia, SC"),
         annual_revenue=unknown_fact(ranged=True), sales_team_size=unknown_fact(ranged=True)),
    lead("Brand New Co"),
]


def names(leads):
    return [l["name"] for l in leads]


def test_no_filters_returns_everything():
    assert names(filter_leads(LEADS)) == names(LEADS)


def test_search_matches_company_or_owner():
    assert names(filter_leads(LEADS, search="steel")) == ["Big Steel"]
    assert names(filter_leads(LEADS, search="pat owner")) == ["Palmetto Software"]


def test_qualification_and_not_checked():
    assert names(filter_leads(LEADS, results=["Meets criteria", "Needs review"])) == ["Palmetto Software", "Mystery Co"]
    assert names(filter_leads(LEADS, results=["Not checked"])) == ["Brand New Co"]


def test_status_and_source():
    assert names(filter_leads(LEADS, statuses=["researched"])) == ["Big Steel", "Mystery Co"]
    assert names(filter_leads(LEADS, sources=["discovered"])) == ["Big Steel"]


def test_industry_and_location():
    assert names(filter_leads(LEADS, industry="software")) == ["Palmetto Software", "Mystery Co"]
    assert names(filter_leads(LEADS, location="sc")) == ["Palmetto Software", "Mystery Co"]


def test_revenue_range_keeps_unknown_by_default():
    found = filter_leads(LEADS, revenue_min=1_000_000, revenue_max=30_000_000)
    assert names(found) == ["Palmetto Software", "Mystery Co", "Brand New Co"]


def test_revenue_range_can_hide_unknown():
    found = filter_leads(LEADS, revenue_min=1_000_000, revenue_max=30_000_000, include_unknown=False)
    assert names(found) == ["Palmetto Software"]


def test_sales_team_range_edges_are_inclusive():
    assert names(filter_leads(LEADS, reps_min=6, reps_max=6, include_unknown=False)) == ["Palmetto Software"]
    assert names(filter_leads(LEADS, reps_min=7, reps_max=39, include_unknown=False)) == []


def test_filters_combine():
    found = filter_leads(LEADS, location="sc", results=["Meets criteria"], search="palmetto")
    assert names(found) == ["Palmetto Software"]
