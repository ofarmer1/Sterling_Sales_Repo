"""Decide whether a researched company fits John's criteria.

This is plain Python with no AI, so the rules are predictable and tested
(tests/test_qualification.py).

Each criterion gets one of:
    "supported"     - the research shows it fits
    "contradicted"  - the research shows it doesn't fit
    "unknown"       - we can't tell (missing, estimated, or unclear)

Overall result:
    "Does not meet criteria" - at least one criterion is contradicted
    "Meets criteria"         - every criterion is supported
    "Needs review"           - otherwise (something is unknown)

Unknown never counts as a pass, and a known mismatch always shows.
"""

MEETS = "Meets criteria"
DOES_NOT_MEET = "Does not meet criteria"
NEEDS_REVIEW = "Needs review"

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNKNOWN = "unknown"

# US state names to two-letter codes, for matching the Geography setting.
STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def target_states(geography):
    """Turn the Geography setting ('South Carolina', 'SC, NC') into state codes."""
    codes = set()
    for part in geography.replace(";", ",").split(","):
        part = part.strip().lower()
        if part in STATE_CODES:
            codes.add(STATE_CODES[part])
        elif len(part) == 2 and part.upper() in STATE_CODES.values():
            codes.add(part.upper())
    return codes


def _fact(research, name):
    return research.get(name) or {"value": None, "status": "unknown", "sources": []}


def _result(criterion, outcome, reason, fact=None):
    return {
        "criterion": criterion,
        "result": outcome,
        "reason": reason,
        "sources": list((fact or {}).get("sources") or []),
    }


def check_geography(research, settings):
    wanted = target_states(settings["geography"])
    state = _fact(research, "state")
    evidence = _fact(research, "south_carolina_evidence")
    label = f"Located in {settings['geography']}"

    if not wanted:
        return _result(label, UNKNOWN, "The Geography setting isn't a US state the app recognizes.")
    if state["status"] == "unknown" or not state["value"]:
        return _result(label, UNKNOWN, "Headquarters state not found.")
    code = state["value"].strip().upper()
    code = STATE_CODES.get(code.lower(), code)
    if code in wanted:
        if state["status"] == "verified":
            return _result(label, SUPPORTED, f"Headquartered in {code}.", state)
        return _result(label, UNKNOWN, f"Probably in {code}, but not verified.", state)
    # Based elsewhere, but verified local operations can still count as a lead to review.
    if evidence["status"] == "verified":
        return _result(
            label, UNKNOWN,
            f"Headquartered in {code}, with some {settings['geography']} presence: {evidence['value']}",
            evidence,
        )
    if state["status"] == "verified":
        return _result(label, CONTRADICTED, f"Headquartered in {code}.", state)
    return _result(label, UNKNOWN, f"Possibly headquartered in {code} (not verified).", state)


def check_industry(research, settings):
    tech = _fact(research, "is_tech_company")
    industry = _fact(research, "industry")
    label = "Tech/software company" + (" (or strong non-tech fit)" if settings["allow_non_tech"] else "")
    answer = (tech["value"] or "").strip().lower()

    if tech["status"] == "unknown" or answer not in ("yes", "no"):
        return _result(label, UNKNOWN, "Not clear whether it's a tech company.")
    if answer == "yes":
        if tech["status"] == "verified":
            return _result(label, SUPPORTED, f"Tech company ({industry['value'] or 'industry not stated'}).", tech)
        return _result(label, UNKNOWN, "Looks like a tech company, but not verified.", tech)
    # Not a tech company.
    if not settings["allow_non_tech"]:
        return _result(label, CONTRADICTED, f"Not a tech company ({industry['value'] or 'industry unknown'}).", tech)
    fit = _fact(research, "non_tech_fit_reason")
    if fit["status"] != "unknown" and fit["value"]:
        return _result(label, UNKNOWN, f"Not tech, but possible strong fit: {fit['value']}. A person should decide.", fit)
    return _result(label, UNKNOWN, f"Not a tech company ({industry['value'] or 'industry unknown'}), and no clear reason it's a strong fit.", tech)


def check_range(research, field_name, low_limit, high_limit, label, unit):
    """Compare a researched low/high range with the allowed min/max."""
    fact = _fact(research, field_name)
    low, high = fact.get("low"), fact.get("high")
    if fact["status"] == "unknown" or (low is None and high is None):
        return _result(label, UNKNOWN, f"{unit} not publicly available.")
    low = high if low is None else low
    high = low if high is None else high
    shown = _describe(low, high, unit)

    completely_inside = low >= low_limit and high <= high_limit
    completely_outside = high < low_limit or low > high_limit

    if completely_outside and fact["status"] == "verified":
        return _result(label, CONTRADICTED, f"{shown} is outside the target range.", fact)
    if completely_outside:
        return _result(label, UNKNOWN, f"Estimated {shown}, outside the target range, but only an estimate.", fact)
    if completely_inside and fact["status"] == "verified":
        return _result(label, SUPPORTED, f"{shown} is within the target range.", fact)
    if completely_inside:
        return _result(label, UNKNOWN, f"Estimated {shown}: inside the range, but only an estimate.", fact)
    return _result(label, UNKNOWN, f"{shown} overlaps the edge of the target range.", fact)


def _describe(low, high, unit):
    """E.g. 'Revenue $2.0M to $5.0M' or '4 to 8 salespeople'."""
    if unit == "Revenue":
        fmt = lambda n: f"${n / 1_000_000:,.1f}M"
    else:
        fmt = lambda n: f"{n:,.0f}"
    amount = fmt(low) if low == high else f"{fmt(low)} to {fmt(high)}"
    return f"Revenue {amount}" if unit == "Revenue" else f"{amount} salespeople"


def check_owner(research, settings):
    name = _fact(research, "owner_name")
    evidence = _fact(research, "ownership_evidence")
    label = f"{settings['target_role']} identified"
    if name["status"] == "unknown" or not name["value"]:
        return _result(label, UNKNOWN, "Owner not found.")
    if name["status"] == "verified" and evidence["status"] == "verified":
        return _result(label, SUPPORTED, f"{name['value']}: {evidence['value']}", evidence)
    return _result(label, UNKNOWN, f"{name['value']} may be the owner, but ownership isn't verified.", name)


def qualify(research, settings):
    """Check a researched company against the settings.

    Returns {"result": ..., "summary": ..., "criteria": [...]}.
    """
    criteria = [
        check_geography(research, settings),
        check_industry(research, settings),
        check_range(research, "annual_revenue", settings["revenue_min"], settings["revenue_max"],
                    "Annual revenue in range", "Revenue"),
        check_range(research, "sales_team_size", settings["sales_reps_min"], settings["sales_reps_max"],
                    "Sales team size in range", "Sales team size"),
        check_owner(research, settings),
    ]

    results = [c["result"] for c in criteria]
    if CONTRADICTED in results:
        result = DOES_NOT_MEET
    elif all(r == SUPPORTED for r in results):
        result = MEETS
    else:
        result = NEEDS_REVIEW

    counts = {r: results.count(r) for r in (SUPPORTED, CONTRADICTED, UNKNOWN)}
    summary = (
        f"{counts[SUPPORTED]} supported, {counts[CONTRADICTED]} contradicted, "
        f"{counts[UNKNOWN]} unknown."
    )
    return {"result": result, "summary": summary, "criteria": criteria}
