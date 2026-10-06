"""Tests for the tighter discovery rules and email warnings (fake AI only)."""

from discovery import DISCOVERY_SCHEMA, discover_companies
from research import check_research, email_warning
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import SEEN, FakeAI, fact, good_research

LIST = "https://example.com/list"
OWNER_PAGE = "https://example.com/team"
SIZE_PAGE = "https://example.com/size"


def candidate(name, **changes):
    item = {
        "name": name, "website": f"https://{name.lower().replace(' ', '')}.example",
        "reason": "SC software firm", "sources": [LIST],
        "owner_name": None, "owner_role": None, "owner_sources": [],
        "size_evidence": None, "size_sources": [],
        "likely_exceeds_limits": False, "exceeds_evidence": None,
    }
    item.update(changes)
    return item


def discover(items, seen=(LIST, OWNER_PAGE, SIZE_PAGE), count=3):
    ai = FakeAI()
    ai.answers["company_candidates"] = lambda prompt: ({"companies": items}, list(seen))
    found, _ = discover_companies(ai, DEFAULT_SETTINGS, count)
    return found, ai


def test_named_owner_with_source_comes_first():
    found, _ = discover([
        candidate("No Owner Co"),
        candidate("Owner Co", owner_name="Pat Founder", owner_role="Founder and owner", owner_sources=[OWNER_PAGE]),
    ])
    assert [c["name"] for c in found] == ["Owner Co", "No Owner Co"]
    assert "Owner/founder: Pat Founder (Founder and owner)" in found[0]["reason"]
    assert OWNER_PAGE in found[0]["sources"]
    assert "needs review" in found[1]["reason"]


def test_owner_without_a_seen_source_is_not_trusted():
    found, _ = discover([candidate("Co", owner_name="Made Up", owner_sources=["https://nowhere.example"])])
    assert found[0]["owner_name"] == ""


def test_credible_evidence_of_too_big_is_skipped():
    found, _ = discover([
        candidate("Huge Co", likely_exceeds_limits=True, exceeds_evidence="$200M revenue", size_sources=[SIZE_PAGE]),
        candidate("Small Co"),
    ])
    assert [c["name"] for c in found] == ["Small Co"]


def test_unsourced_too_big_claim_is_not_a_rejection():
    found, _ = discover([candidate("Maybe Big Co", likely_exceeds_limits=True, size_sources=[])])
    assert [c["name"] for c in found] == ["Maybe Big Co"]


def test_missing_size_is_unknown_not_excluded():
    found, _ = discover([candidate("Quiet Co")])
    assert "Size: no public evidence yet (unknown)" in found[0]["reason"]


def test_asks_for_extra_candidates_but_returns_only_count():
    found, ai = discover([candidate(f"Co {i}") for i in range(6)], count=3)
    assert len(found) == 3
    assert "Find 6 companies" in ai.calls[0][1]


def test_prompt_states_the_rules():
    _, ai = discover([candidate("Co")])
    prompt = ai.calls[0][1]
    assert "South Carolina" in prompt and "$1,000,000 to $30,000,000" in prompt
    assert "2 to 20 salespeople" in prompt


def test_discovery_schema_is_strict():
    item = DISCOVERY_SCHEMA["properties"]["companies"]["items"]
    assert set(item["required"]) == set(item["properties"])


def test_role_emails_are_flagged():
    for email in ["jobs@acme.com", "Careers@acme.com", "support@acme.com", "info@acme.com", "no-reply@acme.com"]:
        assert "Not suitable" in email_warning(email)
    assert email_warning("pat@acme.com") == ""
    assert email_warning(None) == ""


def test_research_flags_role_email_but_never_invents_one():
    cleaned = check_research(good_research(public_email=fact("jobs@palmetto.example")), SEEN)
    assert "Not suitable" in cleaned["public_email"]["unsuitable_reason"]
    assert cleaned["public_email"]["value"] == "jobs@palmetto.example"  # shown, flagged, not used
    cleaned = check_research(good_research(), SEEN)
    assert cleaned["public_email"]["value"] is None
    assert cleaned["public_email"]["unsuitable_reason"] == ""


def test_hidden_email_placeholder_is_not_kept():
    cleaned = check_research(good_research(public_email=fact("[email protected]")), SEEN)
    assert cleaned["public_email"]["value"] is None
    assert cleaned["public_email"]["status"] == "unknown"
