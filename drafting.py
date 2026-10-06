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
- Use one or two specific facts from the research, so it's clearly not a mass email.
- The value: what the company could gain by getting more of its reps to quota.
  Present it as a possible opportunity. Never claim their reps are missing quota
  or invent problems they have.
- Humor only if it fits naturally. No buzzwords, no flattery, no big promises.
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


def draft_warnings(drafts):
    """Things a reviewer should know about a draft."""
    warnings = []
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
