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


# ---- Richer research, contacts and personal drafts ------------------------------

from drafting import personalization_warnings, specific_terms, usable_facts


def test_news_kept_only_with_seen_sources():
    data = good_research(recent_news=[
        {"headline": "Palmetto opens Charleston office", "date": "2026-03", "summary": "New office.",
         "sources": ["https://example.com/news"]},
        {"headline": "Invented award", "date": None, "summary": "", "sources": ["https://nowhere.example"]},
    ])
    news = check_research(data, SEEN)["recent_news"]
    assert [n["headline"] for n in news] == ["Palmetto opens Charleston office"]


def test_owner_email_must_be_verified_and_not_a_shared_inbox():
    cleaned = check_research(good_research(owner_email=fact("pat@palmetto.example", status="estimate")), SEEN)
    assert cleaned["owner_email"]["value"] is None  # guessed: dropped
    cleaned = check_research(good_research(owner_email=fact("info@palmetto.example")), SEEN)
    assert cleaned["owner_email"]["value"] is None  # a shared inbox isn't the owner's
    assert cleaned["public_email"]["value"] == "info@palmetto.example"  # but it's kept as the general inbox
    cleaned = check_research(good_research(owner_email=fact("pat@palmetto.example")), SEEN)
    assert cleaned["owner_email"]["value"] == "pat@palmetto.example"


def test_writer_gets_news():
    research = check_research(good_research(recent_news=[
        {"headline": "Palmetto opens Charleston office", "date": "2026-03", "summary": "", "sources": ["https://example.com/news"]}
    ]), SEEN)
    assert any("recent news (2026-03): Palmetto opens Charleston office" in line for line in usable_facts(research))


def test_generic_draft_is_flagged_and_specific_one_is_not():
    research = check_research(good_research(), SEEN)
    assert "charleston" in specific_terms(research)
    generic = {"email_body": "Hi Pat, we help sales teams hit quota. Open to a call?", "linkedin_note": ""}
    specific = {"email_body": "Hi Pat, congrats on the new Charleston office. Open to a call?", "linkedin_note": ""}
    assert any("Sounds generic" in w for w in personalization_warnings(generic, research))
    assert personalization_warnings(specific, research) == []


def test_buzzwords_are_flagged():
    research = check_research(good_research(), SEEN)
    draft = {"email_body": "Charleston news! Let's leverage synergy.", "linkedin_note": ""}
    warnings = personalization_warnings(draft, research)
    assert any("leverage" in w and "synergy" in w for w in warnings)


def test_min_checks_filter():
    from lead_filters import filter_leads
    from qualification import qualify
    from tests.fake_database import LEAD_DEFAULTS
    from tests.fake_ai import unknown_fact
    def lead(name, **changes):
        r = check_research(good_research(**changes), SEEN)
        return {**LEAD_DEFAULTS, "name": name, "research": r, "qualification": qualify(r, DEFAULT_SETTINGS)}
    leads = [lead("Five"), lead("Four", annual_revenue=unknown_fact(ranged=True)), {**LEAD_DEFAULTS, "name": "New"}]
    assert [l["name"] for l in filter_leads(leads, min_checks=5)] == ["Five"]
    assert [l["name"] for l in filter_leads(leads, min_checks=4)] == ["Five", "Four"]
