"""Find candidate companies with web search.

Discovery only suggests names. Each candidate says why it was suggested and
which pages back that up. Nobody is treated as qualified until it has been
researched and checked (research.py and qualification.py).
"""

from ai_client import object_schema
from research import normalize_url

MAX_DISCOVERY = 20  # most candidates we ask for at once, to keep costs down

_urls = {"type": "array", "items": {"type": "string"}}

DISCOVERY_SCHEMA = object_schema(
    {
        "companies": {
            "type": "array",
            "items": object_schema(
                {
                    "name": {"type": "string"},
                    "website": {"type": "string"},
                    "reason": {"type": "string"},
                    "sources": _urls,
                    "owner_name": {"type": ["string", "null"]},
                    "owner_role": {"type": ["string", "null"]},
                    "owner_sources": _urls,
                    "size_evidence": {"type": ["string", "null"]},
                    "size_sources": _urls,
                    "likely_exceeds_limits": {"type": "boolean"},
                    "exceeds_evidence": {"type": ["string", "null"]},
                }
            ),
        }
    }
)

INSTRUCTIONS = """You find candidate companies for a sales-training consultant.
Use web search. Only list real companies you found on real pages.

Prefer small, founder-led or owner-led, privately held companies where a page
publicly names the current owner or founder AND supports that they still hold
that role today. Prefer companies with evidence they fit the size limits.

For each company give:
- name, website, a one-sentence reason it may fit, and the URLs supporting it;
- owner_name, owner_role and owner_sources: only if a page you saw names them
  and supports their current role; otherwise null and [];
- size_evidence and size_sources: public signs of size (e.g. a stated revenue,
  a stated number of salespeople), or null and [] if none;
- likely_exceeds_limits: true only if there is credible evidence the company is
  bigger than the revenue or sales-team limits, with exceeds_evidence saying what.

Rules: total employee count is not sales-team size. Number of products is not
proof of revenue. Missing information is unknown, not a reason to exclude."""


def build_prompt(settings, count, exclude_names):
    industries = ", ".join(settings["preferred_industries"]) or "any"
    lines = [
        f"Find {count} companies headquartered in {settings['geography']}.",
        f"Industries: {industries}.",
        f"Revenue limits: ${settings['revenue_min']:,} to ${settings['revenue_max']:,} a year.",
        f"Sales-team limits: {settings['sales_reps_min']} to {settings['sales_reps_max']} salespeople.",
        "Small, founder-led companies with a publicly named owner are best.",
    ]
    if settings["allow_non_tech"]:
        lines.append("Mostly the preferred industries, but strong fits outside them are fine (explain why).")
    if exclude_names:
        lines.append("Don't include these (already on the list): " + "; ".join(exclude_names))
    return "\n".join(lines)


def _confirmed(urls, seen):
    return [url for url in urls or [] if normalize_url(url) in seen]


def describe_candidate(candidate):
    """One readable paragraph: why it was found, the owner, and size evidence."""
    parts = [candidate["reason"]]
    if candidate["owner_name"]:
        role = f" ({candidate['owner_role']})" if candidate["owner_role"] else ""
        parts.append(f"Owner/founder: {candidate['owner_name']}{role}.")
    else:
        parts.append("Owner/founder: not named by a source yet (needs review).")
    if candidate["size_evidence"]:
        parts.append(f"Size: {candidate['size_evidence'].rstrip('.')}.")
    else:
        parts.append("Size: no public evidence yet (unknown).")
    return " ".join(parts)


def discover_companies(ai, settings, count, exclude_names=()):
    """Return (candidates, usage), best first.

    - Candidates without a confirmed source are dropped.
    - Candidates with sourced evidence that they're over the limits are dropped.
    - Owner and size details only count if their sources were really seen.
    - Candidates with a sourced owner come first, then those with size evidence.
    """
    count = max(1, min(count, MAX_DISCOVERY))
    # Ask for a few extra so there's room to drop poor fits.
    asked = min(count * 2, MAX_DISCOVERY)
    result = ai.ask_json(
        INSTRUCTIONS,
        build_prompt(settings, asked, list(exclude_names)),
        DISCOVERY_SCHEMA,
        "company_candidates",
        web_search=True,
        max_searches=10,
    )
    seen = {normalize_url(url) for url in result.seen_urls}
    candidates = []
    for item in result.data.get("companies") or []:
        sources = _confirmed(item.get("sources"), seen)
        if not item.get("name", "").strip() or not sources:
            continue
        if item.get("likely_exceeds_limits") and _confirmed(item.get("size_sources"), seen):
            continue  # credible, sourced evidence it's too big
        owner_sources = _confirmed(item.get("owner_sources"), seen)
        size_sources = _confirmed(item.get("size_sources"), seen)
        candidate = {
            "name": item["name"].strip(),
            "website": (item.get("website") or "").strip(),
            "reason": (item.get("reason") or "").strip(),
            "owner_name": (item.get("owner_name") or "").strip() if owner_sources else "",
            "owner_role": (item.get("owner_role") or "").strip() if owner_sources else "",
            "size_evidence": (item.get("size_evidence") or "").strip() if size_sources else "",
        }
        candidate["sources"] = list(dict.fromkeys(sources + owner_sources + size_sources))
        candidate["reason"] = describe_candidate(candidate)
        candidates.append(candidate)

    candidates.sort(key=lambda c: (not c["owner_name"], not c["size_evidence"]))
    return candidates[:count], result.usage
