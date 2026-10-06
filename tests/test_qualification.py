"""Tests for the qualification rules."""

from qualification import (
    DOES_NOT_MEET, MEETS, NEEDS_REVIEW, qualify, target_states,
)
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import SEEN, fact, good_research, range_fact, unknown_fact
from research import check_research


def run(settings=None, **changes):
    research = check_research(good_research(**changes), SEEN)
    return qualify(research, {**DEFAULT_SETTINGS, **(settings or {})})


def criterion(result, starts_with):
    return next(c for c in result["criteria"] if c["criterion"].startswith(starts_with))


def test_good_company_meets_criteria():
    result = run()
    assert result["result"] == MEETS
    assert all(c["result"] == "supported" for c in result["criteria"])
    assert all(c["sources"] for c in result["criteria"])  # every pass is traceable


def test_unknown_revenue_is_not_a_pass():
    result = run(annual_revenue=unknown_fact(ranged=True))
    assert result["result"] == NEEDS_REVIEW
    assert criterion(result, "Annual revenue")["result"] == "unknown"


def test_unknown_sales_team_is_not_a_pass():
    assert run(sales_team_size=unknown_fact(ranged=True))["result"] == NEEDS_REVIEW


def test_known_mismatch_beats_everything_else():
    result = run(state=fact("NC"), south_carolina_evidence=unknown_fact())
    assert result["result"] == DOES_NOT_MEET
    assert criterion(result, "Located")["result"] == "contradicted"


def test_revenue_boundaries_are_inclusive():
    assert run(annual_revenue=range_fact(1_000_000, 1_000_000))["result"] == MEETS
    assert run(annual_revenue=range_fact(30_000_000, 30_000_000))["result"] == MEETS


def test_revenue_just_outside_is_contradicted():
    result = run(annual_revenue=range_fact(30_000_001, 40_000_000))
    assert result["result"] == DOES_NOT_MEET


def test_revenue_overlapping_edge_needs_review():
    result = run(annual_revenue=range_fact(20_000_000, 50_000_000))
    assert criterion(result, "Annual revenue")["result"] == "unknown"


def test_estimated_revenue_inside_range_is_not_a_pass():
    result = run(annual_revenue=range_fact(5_000_000, 6_000_000, status="estimate"))
    assert criterion(result, "Annual revenue")["result"] == "unknown"


def test_estimated_revenue_outside_range_is_flagged_but_not_rejected():
    result = run(annual_revenue=range_fact(90_000_000, 99_000_000, status="estimate"))
    assert criterion(result, "Annual revenue")["result"] == "unknown"
    assert "outside" in criterion(result, "Annual revenue")["reason"]


def test_sales_team_boundaries():
    assert run(sales_team_size=range_fact(2, 2))["result"] == MEETS
    assert run(sales_team_size=range_fact(20, 20))["result"] == MEETS
    assert run(sales_team_size=range_fact(1, 1))["result"] == DOES_NOT_MEET
    assert run(sales_team_size=range_fact(21, 30))["result"] == DOES_NOT_MEET


def test_owner_without_ownership_evidence_needs_review():
    result = run(ownership_evidence=unknown_fact())
    assert criterion(result, "Owner")["result"] == "unknown"
    assert result["result"] == NEEDS_REVIEW


def test_non_tech_when_not_allowed_is_contradicted():
    result = run({"allow_non_tech": False}, is_tech_company=fact("no"), industry=fact("Plumbing"))
    assert result["result"] == DOES_NOT_MEET


def test_strong_non_tech_fit_needs_a_person_to_decide():
    result = run(is_tech_company=fact("no"), industry=fact("Industrial supply"),
                 non_tech_fit_reason=fact("Has 10 outside sales reps"))
    assert result["result"] == NEEDS_REVIEW
    assert "strong fit" in criterion(result, "Tech")["reason"]


def test_unverified_state_is_unknown():
    result = run(state=fact("SC", status="estimate"))
    assert criterion(result, "Located")["result"] == "unknown"


def test_out_of_state_with_verified_sc_presence_needs_review():
    result = run(state=fact("GA"), south_carolina_evidence=fact("Sales office in Columbia, SC"))
    assert criterion(result, "Located")["result"] == "unknown"


def test_conflicting_evidence_estimate_vs_verified():
    # A source we can't confirm can't make the company pass.
    result = run(owner_name=fact("Pat Owner", sources=["https://made-up.example"]))
    assert criterion(result, "Owner")["result"] == "unknown"


def test_geography_setting_parsing():
    assert target_states("South Carolina") == {"SC"}
    assert target_states("SC, North Carolina; GA") == {"SC", "NC", "GA"}
    assert target_states("The Moon") == set()


def test_unrecognized_geography_is_unknown_not_pass():
    result = run({"geography": "Upstate"})
    assert criterion(result, "Located")["result"] == "unknown"
