"""Export leads to a spreadsheet-friendly CSV file.

- Every cell is quoted, so commas, quotes and multi-line drafts stay intact.
- Cells that start with = + - @ (or a tab/return) get a leading apostrophe,
  so a spreadsheet won't run them as formulas. Research text comes from the
  web, so we never trust it.
- Saved as UTF-8 with a BOM so Excel shows accents and symbols correctly.
"""

import csv
import io

COLUMNS = [
    ("Company", lambda lead, r: lead["name"]),
    ("Website", lambda lead, r: lead["website"] or _value(r, "website")),
    ("Status", lambda lead, r: lead["status"]),
    ("Qualification", lambda lead, r: lead["qualification_result"]),
    ("Qualification reasons", lambda lead, r: _reasons(lead)),
    ("Headquarters", lambda lead, r: _value(r, "headquarters")),
    ("Industry", lambda lead, r: _value(r, "industry")),
    ("What they sell", lambda lead, r: _value(r, "what_they_sell")),
    ("Revenue", lambda lead, r: _range(r, "annual_revenue")),
    ("Sales team size", lambda lead, r: _range(r, "sales_team_size")),
    ("Owner", lambda lead, r: _value(r, "owner_name")),
    ("Owner title", lambda lead, r: _value(r, "owner_title")),
    ("Ownership evidence", lambda lead, r: _value(r, "ownership_evidence")),
    ("Owner LinkedIn", lambda lead, r: _value(r, "owner_linkedin_url")),
    ("Company LinkedIn", lambda lead, r: _value(r, "company_linkedin_url")),
    ("Public email", lambda lead, r: _value(r, "public_email")),
    ("Email warning", lambda lead, r: ((r or {}).get("public_email") or {}).get("unsuitable_reason", "")),
    ("Public phone", lambda lead, r: _value(r, "public_phone")),
    ("Email subject", lambda lead, r: lead["email_subject"]),
    ("Email body", lambda lead, r: lead["email_body"]),
    ("LinkedIn note", lambda lead, r: lead["linkedin_note"]),
    ("Source links", lambda lead, r: "\n".join(lead.get("research_sources") or [])),
    ("Found by", lambda lead, r: lead["source"]),
    ("Why it was found", lambda lead, r: lead["discovery_reason"]),
    ("Researched at", lambda lead, r: lead.get("researched_at") or ""),
    ("Research error", lambda lead, r: lead.get("research_error") or ""),
]

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _value(research, name):
    fact = (research or {}).get(name) or {}
    if fact.get("status") in (None, "unknown") or fact.get("value") in (None, ""):
        return "unknown"
    suffix = " (estimate)" if fact["status"] == "estimate" else " (cited)"
    return f"{fact['value']}{suffix}"


def _range(research, name):
    fact = (research or {}).get(name) or {}
    if fact.get("status") in (None, "unknown"):
        return "unknown"
    text = fact.get("value") or f"{fact.get('low')} to {fact.get('high')}"
    return f"{text} ({fact['status']})"


def _reasons(lead):
    criteria = (lead.get("qualification") or {}).get("criteria") or []
    return "\n".join(f"{c['criterion']}: {c['result']}. {c['reason']}" for c in criteria)


def safe_cell(value):
    """Turn a value into text a spreadsheet won't treat as a formula."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_STARTS):
        return "'" + text
    return text


def leads_to_csv(leads):
    """Return the CSV file contents as bytes."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow([name for name, _ in COLUMNS])
    for lead in leads:
        research = lead.get("research") or {}
        writer.writerow([safe_cell(get(lead, research)) for _, get in COLUMNS])
    return buffer.getvalue().encode("utf-8-sig")
