"""Short, plain-English summaries for the Leads tab.

`lead_snapshot` turns a saved lead into the few things you want at a glance.
`buy_box_lines` describes John's buy box (his targeting settings).
No Streamlit code here, so it's tested in tests/test_snapshot.py.
"""

from contacts import best_contact
from qualification import CONTRADICTED, DOES_NOT_MEET, MEETS, NEEDS_REVIEW, UNKNOWN

# One word for the overall result.
FIT_WORDS = {MEETS: "Fits", NEEDS_REVIEW: "Check", DOES_NOT_MEET: "No fit"}

# Plain words for each criterion result.
RESULT_WORDS = {"supported": "Meets", CONTRADICTED: "Does not meet", UNKNOWN: "Unknown"}


def short_name(criterion):
    """'Annual revenue in range' -> 'revenue', and so on."""
    text = criterion.lower()
    for key, name in [
        ("located", "location"), ("industry", "industry"), ("revenue", "revenue"),
        ("sales team", "sales team"), ("identified", "owner"),
    ]:
        if key in text:
            return name
    return criterion


def _value(research, name):
    fact = research.get(name) or {}
    return fact.get("value") if fact.get("status") not in (None, "unknown") else None


def checks_met(lead):
    """(how many buy-box checks are met, how many there are); (0, 0) if not researched."""
    criteria = (lead.get("qualification") or {}).get("criteria") or []
    return sum(1 for c in criteria if c["result"] == "supported"), len(criteria)


def sort_by_checks(leads):
    """Most buy-box checks met first; researched before unresearched."""
    return sorted(leads, key=lambda lead: (-checks_met(lead)[0], -checks_met(lead)[1], lead["name"].lower()))


def lead_snapshot(lead):
    research = lead.get("research") or {}
    qualification = lead.get("qualification") or {}
    criteria = qualification.get("criteria") or []
    result = lead.get("qualification_result") or ""

    if not research:
        fit, reason = "Not checked", "Not researched yet."
    elif result == DOES_NOT_MEET:
        misses = [c for c in criteria if c["result"] == CONTRADICTED]
        fit, reason = FIT_WORDS[result], misses[0]["reason"] if misses else "Doesn't fit the buy box."
    elif result == MEETS:
        fit, reason = FIT_WORDS[result], "Meets every part of the buy box."
    else:
        unknown = [short_name(c["criterion"]) for c in criteria if c["result"] == UNKNOWN]
        fit = FIT_WORDS.get(result, "Check")
        reason = "Unknown: " + ", ".join(unknown) + "." if unknown else "Needs a person to check."

    owner = _value(research, "owner_name")
    title = _value(research, "owner_title")
    owner_text = f"{owner} ({title})" if owner and title else owner or "Owner not found"

    if lead.get("drafts_edited_at"):
        drafts = "Draft edited"
    elif lead.get("email_body"):
        drafts = "Draft ready"
    else:
        drafts = "No draft yet"

    flags = []
    if lead.get("research_error"):
        flags.append("Last research attempt failed")

    contact = best_contact(research)
    met, total = checks_met(lead)
    return {
        "checks": f"{met} of {total} checks met" if total else "",
        "email": contact["email"],
        "email_label": contact["label"],
        "email_kind": contact["kind"],
        "name": lead["name"],
        "place": _value(research, "headquarters") or lead.get("website") or "",
        "owner": owner_text,
        "fit": fit,
        "reason": reason,
        "drafts": drafts,
        "status": lead["status"],
        "flags": flags,
    }


def buy_box_lines(settings):
    """John's buy box as short, plain lines."""
    industries = ", ".join(settings["preferred_industries"]) or "any industry"
    if settings["allow_non_tech"]:
        industries += " (strong fits outside these are considered)"
    return [
        ("Where", settings["geography"]),
        ("Industry", industries),
        ("Revenue", f"${settings['revenue_min'] / 1_000_000:,.1f}M to ${settings['revenue_max'] / 1_000_000:,.1f}M a year"),
        ("Sales team", f"{settings['sales_reps_min']} to {settings['sales_reps_max']} salespeople"),
        ("Contact", settings["target_role"]),
    ]
