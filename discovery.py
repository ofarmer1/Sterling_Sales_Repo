"""Find candidate companies with web search.

Discovery only suggests names. Each candidate says why it was suggested and
which pages back that up. Nobody is treated as qualified until it has been
researched and checked (research.py and qualification.py).
"""

from ai_client import object_schema
from research import normalize_url

MAX_DISCOVERY = 20  # most candidates we ask for at once, to keep costs down

DISCOVERY_SCHEMA = object_schema(
    {
        "companies": {
            "type": "array",
            "items": object_schema(
                {
                    "name": {"type": "string"},
                    "website": {"type": "string"},
                    "reason": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                }
            ),
        }
    }
)

INSTRUCTIONS = """You find candidate companies for a sales-training consultant.
Use web search. Only list real companies you found on real pages.
For each: official name, website, one-sentence reason it may fit, and the URLs
that support it. Prefer privately owned, owner-led companies with a sales team."""


def build_prompt(settings, count, exclude_names):
    industries = ", ".join(settings["preferred_industries"]) or "any"
    lines = [
        f"Find {count} companies headquartered in {settings['geography']}.",
        f"Industries: {industries}.",
        f"Revenue roughly ${settings['revenue_min']:,} to ${settings['revenue_max']:,} a year.",
        f"Likely to have {settings['sales_reps_min']} to {settings['sales_reps_max']} salespeople.",
        "Owner-led companies are best.",
    ]
    if settings["allow_non_tech"]:
        lines.append("Mostly the preferred industries, but strong fits outside them are fine (explain why).")
    if exclude_names:
        lines.append("Don't include these (already on the list): " + "; ".join(exclude_names))
    return "\n".join(lines)


def discover_companies(ai, settings, count, exclude_names=()):
    """Return (candidates, usage). Candidates without a confirmed source are dropped."""
    count = max(1, min(count, MAX_DISCOVERY))
    result = ai.ask_json(
        INSTRUCTIONS,
        build_prompt(settings, count, list(exclude_names)),
        DISCOVERY_SCHEMA,
        "company_candidates",
        web_search=True,
        max_searches=10,
    )
    seen = {normalize_url(url) for url in result.seen_urls}
    candidates = []
    for item in result.data.get("companies") or []:
        sources = [url for url in item.get("sources") or [] if normalize_url(url) in seen]
        if not item.get("name", "").strip() or not sources:
            continue
        candidates.append(
            {
                "name": item["name"].strip(),
                "website": item.get("website", "").strip(),
                "reason": item.get("reason", "").strip(),
                "sources": sources,
            }
        )
    return candidates, result.usage
