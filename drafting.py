"""Write a cold email and LinkedIn note from a company's research.

The AI only sees facts that are verified or estimated (never unknowns), plus
John's messaging settings. Drafts are for a person to review and send by hand.
Nothing here sends anything.
"""

from ai_client import object_schema

LINKEDIN_LIMIT = 300  # LinkedIn's limit for a connection-request note

SIGNATURE_MISSING = "[Signature not set yet: add it in Settings]"

DRAFT_SCHEMA = object_schema(
    {
        "email_subject": {"type": "string"},
        "email_body": {"type": "string"},
        "linkedin_note": {"type": "string"},
    }
)

INSTRUCTIONS = """You write short cold outreach for a sales-training consultant.
You will get facts about one company and the consultant's style preferences.

Rules:
- Short and direct. Email body under 120 words. Subject under 8 words.
- Personal, not a template: mention at least one specific fact about this company
  from the facts given (recent news is best, then a product or announcement).
  Only use facts given to you, and don't state estimates as fact.
- The value: what the company could gain by getting more of its reps to quota.
  Present it as a possible opportunity. Never claim their reps are missing quota
  or invent problems they have.
- Humor only if it fits naturally. No flattery, no big promises.
- No buzzwords, e.g. synergy, leverage, cutting-edge, game-changer, best-in-class,
  revolutionize, unlock, empower, seamless, robust, holistic.
- End with the call to action given.
- Don't include a signature or sign-off name; it's added separately.
- Don't invent names, links, numbers or contact details.
- LinkedIn note: under 280 characters, friendly, mentions one specific fact.
- Address the owner by first name if a name is given."""


def usable_facts(research):
    """List the facts the writer may use (skip anything unknown)."""
    lines = []
    for name, fact in research.items():
        if not isinstance(fact, dict) or fact.get("status") not in ("verified", "estimate"):
            continue
        value = fact.get("value")
        if value in (None, ""):
            continue
        label = name.replace("_", " ")
        if fact["status"] == "estimate":
            label += " (estimate, don't state as fact)"
        lines.append(f"- {label}: {value}")
    for item in research.get("recent_news") or []:
        when = f" ({item['date']})" if item.get("date") else ""
        lines.append(f"- recent news{when}: {item['headline']}. {item.get('summary', '')}")
    for item in research.get("outreach_context") or []:
        lines.append(f"- recent context: {item['fact']}")
    return lines


def build_prompt(company_name, research, settings):
    call_to_action = settings["call_to_action"]
    if settings["booking_url"]:
        call_to_action += f" Booking link to include: {settings['booking_url']}"
    sender = settings["sender_name"] or "the consultant"
    company = settings["sender_company"] or "a sales training firm"
    parts = [
        f"Write on behalf of {sender} at {company}.",
        f"Style: {settings['messaging_style']}",
        f"Value to highlight: {settings['value_proposition']}",
        f"Call to action: {call_to_action}",
        "",
        f"Company: {company_name}",
        "Facts:",
        *usable_facts(research),
    ]
    return "\n".join(parts)


def add_signature(body, settings):
    """Put the booking link (if set and missing) and the signature under the email."""
    body = body.rstrip()
    booking_url = settings["booking_url"].strip()
    if booking_url and booking_url not in body:
        body += f"\n\nIf it's easier, grab a time here: {booking_url}"
    signature = settings["signature"].strip()
    return f"{body}\n\n{signature or SIGNATURE_MISSING}"


def generate_drafts(ai, company_name, research, settings):
    """Ask the AI for drafts. Returns (drafts, usage)."""
    result = ai.ask_json(
        INSTRUCTIONS,
        build_prompt(company_name, research, settings),
        DRAFT_SCHEMA,
        "outreach_drafts",
        web_search=False,
    )
    drafts = {
        "email_subject": result.data["email_subject"].strip(),
        "email_body": add_signature(result.data["email_body"], settings),
        "linkedin_note": result.data["linkedin_note"].strip(),
    }
    return drafts, result.usage


BUZZWORDS = [
    "synergy", "leverage", "cutting-edge", "game-changer", "game changer", "best-in-class",
    "revolutionize", "paradigm", "unlock", "empower", "seamless", "robust", "holistic",
    "world-class", "disrupt", "circle back", "touch base",
]

_COMMON_WORDS = {
    "company", "companies", "business", "businesses", "customers", "clients", "services",
    "service", "software", "solutions", "solution", "products", "product", "provides",
    "offers", "including", "through", "across", "people", "their", "about", "which",
    "south", "carolina", "development", "management", "support", "systems", "system",
}


def specific_terms(research):
    """Distinctive words from the research (news, context, products) to look for in a draft."""
    texts = [item.get("headline", "") + " " + item.get("summary", "") for item in research.get("recent_news") or []]
    texts += [item.get("fact", "") for item in research.get("outreach_context") or []]
    sell = (research.get("what_they_sell") or {}).get("value") or ""
    texts.append(sell)
    terms = set()
    for text in texts:
        for word in text.replace("/", " ").replace(",", " ").split():
            word = word.strip(".;:()'\"").lower()
            if len(word) >= 6 and word.isalpha() and word not in _COMMON_WORDS:
                terms.add(word)
    return terms


def personalization_warnings(drafts, research):
    """Flag drafts that could have been sent to any company."""
    body = drafts["email_body"].lower()
    warnings = []
    terms = specific_terms(research or {})
    if terms and not any(term in body for term in terms):
        warnings.append("Sounds generic: the email doesn't mention anything specific from the research.")
    used = [word for word in BUZZWORDS if word in body]
    if used:
        warnings.append("Buzzwords to cut: " + ", ".join(used) + ".")
    return warnings


def draft_warnings(drafts, research=None):
    """Things a reviewer should know about a draft."""
    warnings = personalization_warnings(drafts, research) if research else []
    if len(drafts["linkedin_note"]) > LINKEDIN_LIMIT:
        warnings.append(
            f"LinkedIn note is {len(drafts['linkedin_note'])} characters; "
            f"LinkedIn allows {LINKEDIN_LIMIT}."
        )
    if SIGNATURE_MISSING in drafts["email_body"]:
        warnings.append("No signature yet. Add one in Settings, or edit the email.")
    if "[" in drafts["email_body"].replace(SIGNATURE_MISSING, ""):
        warnings.append("The email has a [bracket] placeholder to fill in.")
    return warnings
