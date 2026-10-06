"""Save and load leads (companies) and AI usage in Supabase.

Tables are in supabase/schema.sql. Like settings_store.py, this file has no
Streamlit code, so it can be tested with the fake database.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

LEADS = "leads"
USAGE = "usage_log"

# Review statuses a person can pick. The app never uses "sent".
STATUSES = [
    "new",
    "research failed",
    "researched",
    "needs review",
    "draft ready",
    "approved",
    "manually contacted",
]
# Once a person has approved or contacted, drafts are only replaced on purpose.
PROTECTED_STATUSES = {"approved", "manually contacted"}

# Words dropped when comparing company names ("Acme, Inc." == "acme").
_NAME_SUFFIXES = {"inc", "llc", "co", "corp", "corporation", "company", "ltd", "the", "group"}


class LeadsStoreError(Exception):
    """Raised when the database can't be read or written."""


def now():
    return datetime.now(timezone.utc).isoformat()


def company_key(name, website=""):
    """A key for spotting duplicates: the website's domain, else a tidy name."""
    if website.strip():
        address = website.strip()
        if "://" not in address:
            address = "https://" + address
        host = urlparse(address).netloc.lower().removeprefix("www.")
        if host:
            return host
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    words = [w for w in words if w not in _NAME_SUFFIXES]
    return "name:" + " ".join(words)


def _run(query, action):
    try:
        return query.execute()
    except Exception as error:
        raise LeadsStoreError(f"Couldn't {action}: {error}") from error


def list_leads(db):
    response = _run(db.table(LEADS).select("*").order("id"), "load leads")
    return response.data or []


def get_lead(db, lead_id):
    response = _run(db.table(LEADS).select("*").eq("id", lead_id).limit(1), "load the lead")
    if not response.data:
        raise LeadsStoreError("That lead no longer exists.")
    return response.data[0]


def add_companies(db, companies, source="provided"):
    """Add companies, skipping duplicates. Returns (added_rows, skipped_names).

    Each company is a dict with name, and optionally website, reason, sources.
    """
    existing = {lead["company_key"] for lead in list_leads(db)}
    rows, skipped = [], []
    for company in companies:
        name = company.get("name", "").strip()
        website = company.get("website", "").strip()
        if not name:
            continue
        key = company_key(name, website)
        if key in existing:
            skipped.append(name)
            continue
        existing.add(key)
        rows.append(
            {
                "company_key": key,
                "name": name,
                "website": website,
                "source": source,
                "discovery_reason": company.get("reason", ""),
                "discovery_sources": company.get("sources", []),
            }
        )
    if not rows:
        return [], skipped
    response = _run(db.table(LEADS).insert(rows), "add companies")
    if len(response.data or []) != len(rows):
        raise LeadsStoreError("The database didn't confirm all the new companies.")
    return response.data, skipped


def update_lead(db, lead_id, changes, action="save the lead"):
    """Save changes to one lead. Only reports success if the database confirms."""
    changes = {**changes, "updated_at": now()}
    response = _run(db.table(LEADS).update(changes).eq("id", lead_id), action)
    if not response.data:
        raise LeadsStoreError(f"Couldn't {action}: the database didn't confirm it.")
    return response.data[0]


def save_research(db, lead_id, research, seen_urls, qualification):
    lead = get_lead(db, lead_id)
    changes = {
        "research": research,
        "research_sources": seen_urls,
        "researched_at": research.get("researched_at") or now(),
        "research_error": "",
        "qualification": qualification,
        "qualification_result": qualification["result"],
    }
    # Don't knock back a lead someone already approved or contacted.
    if lead["status"] not in PROTECTED_STATUSES and lead["status"] != "draft ready":
        changes["status"] = "researched"
    return update_lead(db, lead_id, changes, "save the research")


def save_research_failure(db, lead_id, error_message):
    return update_lead(
        db, lead_id,
        {"status": "research failed", "research_error": error_message[:500]},
        "record the failure",
    )


def drafts_are_protected(lead):
    """True if new drafts would overwrite someone's edits or an approved draft."""
    return bool(lead.get("drafts_edited_at")) or lead.get("status") in PROTECTED_STATUSES


def save_generated_drafts(db, lead_id, drafts, replace_protected=False):
    """Save AI drafts. Refuses to overwrite edited/approved drafts unless told to."""
    lead = get_lead(db, lead_id)
    if drafts_are_protected(lead) and not replace_protected:
        raise LeadsStoreError(
            "This lead has edited or approved drafts. Tick the box to replace them on purpose."
        )
    changes = {
        **drafts,
        "drafts_generated_at": now(),
        "drafts_edited_at": None,
    }
    if lead["status"] not in PROTECTED_STATUSES:
        changes["status"] = "draft ready"
    return update_lead(db, lead_id, changes, "save the drafts")


def save_draft_edits(db, lead_id, subject, body, linkedin_note):
    return update_lead(
        db, lead_id,
        {
            "email_subject": subject,
            "email_body": body,
            "linkedin_note": linkedin_note,
            "drafts_edited_at": now(),
        },
        "save your edits",
    )


def set_status(db, lead_id, status):
    if status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    return update_lead(db, lead_id, {"status": status}, "change the status")


def log_usage(db, kind, usage, lead_id=None):
    """Record one AI request. Failing to log never loses the research itself."""
    row = {
        "lead_id": lead_id,
        "kind": kind,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "web_searches": usage.web_searches,
        "estimated_cost_usd": usage.estimated_cost(),
    }
    try:
        db.table(USAGE).insert(row).execute()
        return True
    except Exception:
        return False


def usage_totals(db):
    response = _run(db.table(USAGE).select("*"), "load AI usage")
    rows = response.data or []
    costs = [float(r["estimated_cost_usd"]) for r in rows if r.get("estimated_cost_usd") is not None]
    return {
        "requests": len(rows),
        "web_searches": sum(r.get("web_searches") or 0 for r in rows),
        "input_tokens": sum(r.get("input_tokens") or 0 for r in rows),
        "output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
        "estimated_cost_usd": round(sum(costs), 2),
        "unpriced_requests": len(rows) - len(costs),
    }
