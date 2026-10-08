"""Who an email could go to, shown up front on each company.

The order is: the owner's own published email, then a general company inbox
(info@, contact@, sales@... clearly labelled as not the owner), then nothing.
Addresses only ever come from research that cited a real page; nothing is
guessed or built from a name pattern.
"""


def _email(research, name):
    fact = (research or {}).get(name) or {}
    if fact.get("status") in (None, "unknown") or not fact.get("value"):
        return None
    return fact


def best_contact(research):
    """Return {"email", "kind", "label", "sources"}; kind is "owner", "general" or None."""
    owner = _email(research, "owner_email")
    if owner:
        return {
            "email": owner["value"],
            "kind": "owner",
            "label": "Owner's email",
            "sources": owner.get("sources", []),
        }
    general = _email(research, "public_email")
    if general:
        return {
            "email": general["value"],
            "kind": "general",
            "label": "General inbox (not the owner's own email)",
            "sources": general.get("sources", []),
        }
    return {"email": None, "kind": None, "label": "No email found", "sources": []}


def linkedin_links(research):
    links = []
    for name, label in [("owner_linkedin_url", "Owner on LinkedIn"), ("company_linkedin_url", "Company on LinkedIn")]:
        fact = (research or {}).get(name) or {}
        if fact.get("status") not in (None, "unknown") and fact.get("value"):
            links.append((label, fact["value"]))
    return links
