"""A pretend AI for tests. Returns canned answers and never costs money."""

from ai_client import AIError, AIResult, Usage


class FakeAI:
    def __init__(self):
        self.calls = []  # (schema_name, prompt) for every request
        self.answers = {}  # schema_name -> function(prompt) -> (data, seen_urls)
        self.fail_for = set()  # company names whose research should fail

    def ask_json(self, instructions, prompt, schema, schema_name, web_search=False, max_searches=8):
        self.calls.append((schema_name, prompt))
        for name in self.fail_for:
            if f"Company: {name}" in prompt:
                raise AIError(f"The AI request failed: pretend outage for {name}")
        data, seen = self.answers[schema_name](prompt)
        usage = Usage(model="gpt-5.4-mini", input_tokens=1000, output_tokens=200,
                      web_searches=2 if web_search else 0)
        return AIResult(data=data, seen_urls=set(seen), usage=usage)


def fact(value, status="verified", sources=("https://example.com/about",), note=""):
    return {"value": value, "status": status, "sources": list(sources), "note": note}


def range_fact(low, high, status="verified", sources=("https://example.com/about",)):
    return {**fact(f"{low} to {high}", status, sources), "low": low, "high": high}


def unknown_fact(ranged=False):
    item = {"value": None, "status": "unknown", "sources": [], "note": ""}
    if ranged:
        item.update(low=None, high=None)
    return item


def good_research(**changes):
    """Research for a company that meets all of John's criteria."""
    data = {
        "company_name": fact("Palmetto Software"),
        "website": fact("https://palmettosoftware.example"),
        "headquarters": fact("Greenville, SC"),
        "state": fact("SC"),
        "south_carolina_evidence": fact("Office in Greenville, SC"),
        "what_they_sell": fact("Scheduling software for clinics"),
        "who_they_serve": fact("Clinics in the Southeast"),
        "industry": fact("Healthcare software"),
        "is_tech_company": fact("yes"),
        "non_tech_fit_reason": unknown_fact(),
        "owner_name": fact("Pat Owner"),
        "owner_title": fact("Founder and CEO"),
        "ownership_evidence": fact("About page: founded and owned by Pat Owner"),
        "owner_linkedin_url": unknown_fact(),
        "company_linkedin_url": unknown_fact(),
        "public_email": unknown_fact(),
        "public_phone": fact("864-555-0100"),
        "annual_revenue": range_fact(5_000_000, 8_000_000),
        "sales_team_size": range_fact(4, 6),
        "outreach_context": [
            {"fact": "Opened a Charleston office in 2026", "sources": ["https://example.com/news"]}
        ],
    }
    data.update(changes)
    return data


SEEN = ["https://example.com/about", "https://example.com/news"]


def drafts_answer(prompt):
    return (
        {
            "email_subject": "Quick idea for Palmetto",
            "email_body": "Hi Pat,\n\nSaw the new Charleston office...",
            "linkedin_note": "Hi Pat, congrats on the Charleston office!",
        },
        [],
    )


def standard_fake_ai():
    ai = FakeAI()
    ai.answers["company_research"] = lambda prompt: (good_research(), SEEN)
    ai.answers["outreach_drafts"] = drafts_answer
    ai.answers["company_candidates"] = lambda prompt: (
        {
            "companies": [
                {"name": "Found Co", "website": "https://foundco.example", "reason": "SC SaaS firm",
                 "sources": ["https://example.com/list"]},
                {"name": "No Source Co", "website": "", "reason": "made up", "sources": ["https://fake.example"]},
                {"name": "Second Co", "website": "https://second.example", "reason": "Another SC firm",
                 "sources": ["https://example.com/list"]},
            ]
        },
        ["https://example.com/list"],
    )
    return ai
