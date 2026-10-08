"""Tests for the Leads tab snapshot and buy box text."""

from qualification import qualify
from research import check_research
from settings_store import DEFAULT_SETTINGS
from snapshot import buy_box_lines, lead_snapshot, short_name
from tests.fake_ai import SEEN, fact, good_research, unknown_fact
from tests.fake_database import LEAD_DEFAULTS


def lead_with(**changes):
    research = check_research(good_research(**changes), SEEN)
    q = qualify(research, DEFAULT_SETTINGS)
    return {**LEAD_DEFAULTS, "id": 1, "name": "Palmetto Software", "status": "researched",
            "research": research, "qualification": q, "qualification_result": q["result"]}


def test_not_researched():
    snap = lead_snapshot({**LEAD_DEFAULTS, "id": 1, "name": "New Co"})
    assert snap["fit"] == "Not checked"
    assert snap["reason"] == "Not researched yet."
    assert snap["owner"] == "Owner not found"
    assert snap["drafts"] == "No draft yet"


def test_fit_in_one_word_and_owner():
    snap = lead_snapshot(lead_with())
    assert snap["fit"] == "Fits"
    assert snap["owner"] == "Pat Owner (Founder and CEO)"
    assert snap["place"] == "Greenville, SC"


def test_needs_review_lists_unknowns():
    snap = lead_snapshot(lead_with(annual_revenue=unknown_fact(ranged=True), sales_team_size=unknown_fact(ranged=True)))
    assert snap["fit"] == "Check"
    assert snap["reason"] == "Unknown: revenue, sales team."


def test_no_fit_gives_the_reason():
    snap = lead_snapshot(lead_with(state=fact("NC"), south_carolina_evidence=unknown_fact()))
    assert snap["fit"] == "No fit"
    assert "NC" in snap["reason"]


def test_general_inbox_is_offered_but_labelled():
    snap = lead_snapshot(lead_with(public_email=fact("info@palmetto.example")))
    assert snap["email"] == "info@palmetto.example"
    assert snap["email_kind"] == "general"
    assert "not the owner" in snap["email_label"]


def test_owner_email_comes_first():
    snap = lead_snapshot(lead_with(owner_email=fact("pat@palmetto.example"), public_email=fact("info@palmetto.example")))
    assert snap["email"] == "pat@palmetto.example"
    assert snap["email_kind"] == "owner"


def test_no_email_found():
    snap = lead_snapshot(lead_with())
    assert snap["email"] is None and snap["email_label"] == "No email found"


def test_checks_met_and_sorting():
    from snapshot import checks_met, sort_by_checks
    good = {**lead_with(), "name": "Good"}
    weaker = {**lead_with(annual_revenue=unknown_fact(ranged=True)), "name": "Weaker"}
    new = {**LEAD_DEFAULTS, "id": 9, "name": "Aaa New"}
    assert checks_met(good) == (5, 5)
    assert checks_met(weaker) == (4, 5)
    assert checks_met(new) == (0, 0)
    assert [l["name"] for l in sort_by_checks([new, weaker, good])] == ["Good", "Weaker", "Aaa New"]
    assert lead_snapshot(good)["checks"] == "5 of 5 checks met"


def test_draft_states():
    lead = lead_with()
    assert lead_snapshot({**lead, "email_body": "Hi"})["drafts"] == "Draft ready"
    assert lead_snapshot({**lead, "email_body": "Hi", "drafts_edited_at": "2026-10-06"})["drafts"] == "Draft edited"


def test_buy_box_in_plain_words():
    lines = dict(buy_box_lines(DEFAULT_SETTINGS))
    assert lines["Where"] == "South Carolina"
    assert lines["Revenue"] == "$1.0M to $30.0M a year"
    assert lines["Sales team"] == "2 to 20 salespeople"
    assert lines["Contact"] == "Owner"
    assert "strong fits" in lines["Industry"]


def test_short_names():
    assert short_name("Annual revenue in range") == "revenue"
    assert short_name("Owner identified") == "owner"
