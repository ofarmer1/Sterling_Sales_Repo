"""Narrow down the list of leads (used by the Leads tab and its download).

Plain Python, no Streamlit, so it's tested in tests/test_lead_filters.py.

Revenue and sales-team filters only use numbers the research found. A company
with no known number is kept or hidden depending on `include_unknown`, so
missing data is never silently treated as a match.
"""


def _fact(lead, name):
    return ((lead.get("research") or {}).get(name)) or {}


def _text(lead, name):
    fact = _fact(lead, name)
    return str(fact.get("value") or "") if fact.get("status") != "unknown" else ""


def _range(lead, name):
    """(low, high) from research, or None if unknown."""
    fact = _fact(lead, name)
    low, high = fact.get("low"), fact.get("high")
    if fact.get("status") in (None, "unknown") or (low is None and high is None):
        return None
    low = high if low is None else low
    high = low if high is None else high
    return low, high


def _range_matches(lead, name, minimum, maximum, include_unknown):
    """True if the lead's range overlaps [minimum, maximum]."""
    if minimum is None and maximum is None:
        return True
    found = _range(lead, name)
    if found is None:
        return include_unknown
    low, high = found
    if minimum is not None and high < minimum:
        return False
    if maximum is not None and low > maximum:
        return False
    return True


def filter_leads(
    leads,
    search="",
    results=(),
    statuses=(),
    sources=(),
    industry="",
    location="",
    revenue_min=None,
    revenue_max=None,
    reps_min=None,
    reps_max=None,
    include_unknown=True,
    min_checks=0,
):
    """Return the leads that match every filter that's set. Empty filters match all."""
    search = search.strip().lower()
    industry = industry.strip().lower()
    location = location.strip().lower()
    matches = []
    for lead in leads:
        if search and search not in lead["name"].lower() and search not in _text(lead, "owner_name").lower():
            continue
        if results and (lead.get("qualification_result") or "Not checked") not in results:
            continue
        if statuses and lead["status"] not in statuses:
            continue
        if sources and lead["source"] not in sources:
            continue
        if industry and industry not in (_text(lead, "industry") + " " + _text(lead, "what_they_sell")).lower():
            continue
        if location and location not in (_text(lead, "headquarters") + " " + _text(lead, "state")).lower():
            continue
        if not _range_matches(lead, "annual_revenue", revenue_min, revenue_max, include_unknown):
            continue
        if not _range_matches(lead, "sales_team_size", reps_min, reps_max, include_unknown):
            continue
        if min_checks and _checks_met(lead) < min_checks:
            continue
        matches.append(lead)
    return matches


def _checks_met(lead):
    criteria = (lead.get("qualification") or {}).get("criteria") or []
    return sum(1 for c in criteria if c["result"] == "supported")
