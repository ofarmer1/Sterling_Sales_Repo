"""Research one company with web search, then check the answer's sources.

Every fact comes back as:
    {"value": ..., "status": "verified" | "estimate" | "unknown",
     "sources": [urls], "note": "..."}

"verified" means the AI says a source states it AND the web search really
opened that source. The app does NOT read the page to prove it says so, so
the screen calls these "cited" and asks a person to check the link.

After the AI answers, `check_research` cleans it up so we never show more
certainty than we have:
- a source the web search never actually looked at is removed;
- a "verified" fact with no remaining source becomes an "estimate";
- an "unknown" fact has no value;
- emails and LinkedIn links are only kept when verified with a source,
  because guessed contact details are worse than none.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from ai_client import object_schema

# Facts we ask for: name -> what we tell the AI it means.
FACT_FIELDS = {
    "company_name": "The company's official name.",
    "website": "The company's own website address.",
    "headquarters": "Headquarters city and state, e.g. 'Greenville, SC'.",
    "state": "Two-letter US state code of the headquarters, e.g. 'SC'.",
    "south_carolina_evidence": "What shows the company is based or operating in South Carolina.",
    "what_they_sell": "What the company sells, in one or two sentences.",
    "who_they_serve": "Who their customers are.",
    "industry": "Their industry in a few words.",
    "is_tech_company": "'yes' if they mainly sell technology or software, otherwise 'no'.",
    "non_tech_fit_reason": "If the company is outside the preferred industries, why it might still be a strong fit for sales training (e.g. a sizeable B2B sales team). Otherwise unknown.",
    "owner_name": "The full name of the company's owner (founder/owner/majority owner). A CEO or sales leader is NOT automatically the owner.",
    "owner_title": "The owner's title.",
    "ownership_evidence": "The evidence that this person owns the company (e.g. 'founder and owner' on the About page).",
    "owner_linkedin_url": "The owner's public LinkedIn profile URL, only if you saw it.",
    "company_linkedin_url": "The company's public LinkedIn page URL, only if you saw it.",
    "public_email": "A general business email published by the company, only if you saw it. Never guess.",
    "public_phone": "The company's published business phone number.",
}

RANGE_FIELDS = {
    "annual_revenue": "Annual revenue in US dollars. Use low/high numbers. Mark as estimate if it comes from estimate sites (ZoomInfo, Growjo, etc.).",
    "sales_team_size": "Number of salespeople (not total employees). Never turn a total employee count into a sales team size.",
}

STATUSES = ["verified", "estimate", "unknown"]

# Shared inboxes that won't reach the owner (jobs@, support@...).
ROLE_EMAIL_PREFIXES = {
    "jobs", "job", "careers", "career", "hr", "recruiting", "recruitment", "hiring",
    "support", "help", "helpdesk", "service", "customerservice", "noreply", "no-reply",
    "donotreply", "billing", "accounts", "accounting", "invoices", "admin", "webmaster",
    "privacy", "legal", "press", "media", "marketing", "info", "hello", "contact",
    "office", "team", "sales",
}


def email_warning(email):
    """Explain why an email isn't suitable for owner outreach, or '' if it might be."""
    if not email or "@" not in email:
        return ""
    prefix = email.split("@", 1)[0].lower()
    if prefix in ROLE_EMAIL_PREFIXES:
        return f"{email} is a shared {prefix}@ inbox, not the owner. Not suitable for owner outreach."
    return ""

# Contact details we only keep when verified with a source.
STRICT_FIELDS = {"owner_linkedin_url", "company_linkedin_url", "public_email"}

_fact = {
    "value": {"type": ["string", "null"]},
    "status": {"type": "string", "enum": STATUSES},
    "sources": {"type": "array", "items": {"type": "string"}},
    "note": {"type": "string"},
}
_range = {
    **_fact,
    "low": {"type": ["number", "null"]},
    "high": {"type": ["number", "null"]},
}

RESEARCH_SCHEMA = object_schema(
    {
        **{name: object_schema(_fact) for name in FACT_FIELDS},
        **{name: object_schema(_range) for name in RANGE_FIELDS},
        "outreach_context": {
            "type": "array",
            "items": object_schema(
                {
                    "fact": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                }
            ),
        },
    }
)

INSTRUCTIONS = """You research companies for a sales-training consultant.
Use web search to find accurate, current, public information.

For every fact give: value, status, sources (the exact URLs you used), and a short note.
- status "verified": stated directly by a reliable source you list.
- status "estimate": inferred, approximate, or from a data-estimate site.
- status "unknown": not found. Set value to null and sources to [].

Rules:
- Make sure you have the right company (check the website and location).
- The owner is the person who owns the company. Don't call a CEO, president or
  sales leader the owner unless a source says they own or founded it and still own it.
- Revenue and sales-team size are often private. Leave them unknown rather than guess.
  Never convert total employees into a number of salespeople. The number of
  products a company sells is not evidence of revenue.
- For the owner, the source must support that they hold the role today.
- outreach_context: 2 to 5 specific, recent, public facts useful for a personal
  sales email (new product, expansion, hiring salespeople, awards...), each with sources.
- Never invent sources, emails, names or numbers."""


def build_prompt(name, website, settings):
    lines = [f"Company: {name}"]
    if website:
        lines.append(f"Website: {website}")
    lines.append(f"Target region: {settings['geography']}")
    industries = ", ".join(settings["preferred_industries"]) or "any"
    lines.append(f"Preferred industries: {industries}")
    lines.append("Research this company and fill in every field.")
    return "\n".join(lines)


def research_company(ai, name, website, settings):
    """Research one company. Returns (research, seen_urls, usage).

    Raises ai_client.AIError if the request fails.
    """
    result = ai.ask_json(
        INSTRUCTIONS,
        build_prompt(name, website, settings),
        RESEARCH_SCHEMA,
        "company_research",
        web_search=True,
    )
    research = check_research(result.data, result.seen_urls)
    research["researched_at"] = datetime.now(timezone.utc).isoformat()
    return research, sorted(result.seen_urls), result.usage


def normalize_url(url):
    """Make URLs comparable: lower-case host, no 'www.', no trailing slash or #part."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def check_research(data, seen_urls):
    """Clean the AI's research so it never claims more than the sources support."""
    seen = {normalize_url(url) for url in seen_urls}
    cleaned = {}

    for name in list(FACT_FIELDS) + list(RANGE_FIELDS):
        fact = dict(data.get(name) or {})
        fact.setdefault("value", None)
        fact.setdefault("note", "")
        if name in RANGE_FIELDS:
            fact.setdefault("low", None)
            fact.setdefault("high", None)
        if fact.get("status") not in STATUSES:
            fact["status"] = "unknown"

        # Keep only sources the search really looked at.
        given = [url for url in fact.get("sources") or [] if url]
        kept = [url for url in given if normalize_url(url) in seen]
        fact["sources"] = kept
        if len(kept) < len(given):
            fact["note"] = _add_note(fact["note"], "Some sources couldn't be confirmed and were removed.")

        has_value = fact["value"] not in (None, "") or (
            name in RANGE_FIELDS and (fact["low"] is not None or fact["high"] is not None)
        )
        if not has_value:
            fact["status"] = "unknown"

        if fact["status"] == "verified" and not kept:
            fact["status"] = "estimate"
            fact["note"] = _add_note(fact["note"], "No confirmed source, so treated as an estimate.")

        if name in STRICT_FIELDS and fact["status"] != "verified":
            fact["status"] = "unknown"
            fact["note"] = _add_note(fact["note"], "Not kept: contact details must be verified.")

        if fact["status"] == "unknown":
            fact["value"] = None
            fact["sources"] = []
            if name in RANGE_FIELDS:
                fact["low"] = fact["high"] = None

        cleaned[name] = fact

    email = cleaned["public_email"]
    # Some sites hide addresses ("[email protected]"); that's not a real address.
    if email["value"] and not re.fullmatch(r"[^@\s\[\]]+@[^@\s\[\]]+\.[a-zA-Z]{2,}", email["value"].strip()):
        email.update(value=None, status="unknown", sources=[])
        email["note"] = _add_note(email["note"], "The address was hidden or not a real email address.")
    email["unsuitable_reason"] = email_warning(email["value"])
    if email["unsuitable_reason"]:
        email["note"] = _add_note(email["note"], email["unsuitable_reason"])

    cleaned["outreach_context"] = []
    for item in data.get("outreach_context") or []:
        kept = [url for url in item.get("sources") or [] if normalize_url(url) in seen]
        if item.get("fact") and kept:
            cleaned["outreach_context"].append({"fact": item["fact"], "sources": kept})

    return cleaned


def _add_note(note, extra):
    return f"{note} {extra}".strip() if note else extra
