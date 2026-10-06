"""Research, qualify and draft for one lead or a batch of leads.

Each company is saved as soon as it's done, so if one fails (or the app
stops halfway) the finished ones are kept. Retrying only redoes the failed
ones; already-researched companies are skipped unless you ask to redo them.
"""

from drafting import generate_drafts
from leads_store import (
    BudgetExceeded,
    LeadsStoreError,
    check_budget,
    get_lead,
    log_usage,
    save_generated_drafts,
    save_research,
    save_research_failure,
)
from qualification import DOES_NOT_MEET, qualify
from research import research_company

MAX_BATCH = 15  # most companies processed in one go, to keep costs in check

# Statuses that still need research.
NEEDS_RESEARCH = {"new", "research failed"}


def needs_research(lead):
    return lead["status"] in NEEDS_RESEARCH or not lead.get("research")


def needs_drafts(lead):
    """Researched, might fit, and has no drafts yet (e.g. drafting failed last time)."""
    return (
        bool(lead.get("research"))
        and lead.get("qualification_result") != DOES_NOT_MEET
        and not lead.get("email_body")
    )


def needs_retry(lead):
    """Research failed, or research worked but the drafts never got written."""
    return lead["status"] == "research failed" or needs_drafts(lead)


def research_one(db, ai, settings, lead_id):
    """Research and qualify one lead and save it. Returns the saved lead.

    On failure, records the error on the lead and raises.
    """
    lead = get_lead(db, lead_id)
    check_budget(db, getattr(ai, "budget_usd", None))
    try:
        research, seen_urls, usage = research_company(ai, lead["name"], lead["website"], settings)
    except Exception as error:
        save_research_failure(db, lead_id, str(error))
        raise
    log_usage(db, "research", usage, lead_id)
    qualification = qualify(research, settings)
    return save_research(db, lead_id, research, seen_urls, qualification)


def draft_one(db, ai, settings, lead_id, replace_protected=False):
    """Write drafts for one researched lead and save them."""
    lead = get_lead(db, lead_id)
    if not lead.get("research"):
        raise LeadsStoreError("Research this company before writing drafts.")
    check_budget(db, getattr(ai, "budget_usd", None))
    drafts, usage = generate_drafts(ai, lead["name"], lead["research"], settings)
    log_usage(db, "drafts", usage, lead_id)
    return save_generated_drafts(db, lead_id, drafts, replace_protected)


def process_batch(db, ai, settings, lead_ids, write_drafts=True, redo=False, on_progress=None):
    """Research (and optionally draft) a list of leads, one at a time.

    Returns a summary: {"done": [...], "skipped": [...], "failed": [(name, error)]}.
    on_progress(done_count, total, message) is called after each company.
    """
    lead_ids = list(lead_ids)[:MAX_BATCH]
    summary = {"done": [], "skipped": [], "failed": []}

    for number, lead_id in enumerate(lead_ids, start=1):
        name = str(lead_id)
        try:
            lead = get_lead(db, lead_id)
            name = lead["name"]
            do_research = redo or needs_research(lead)
            if not do_research and not (write_drafts and needs_drafts(lead)):
                summary["skipped"].append(name)
                message = f"Skipped {name} (already done)"
            else:
                if do_research:
                    lead = research_one(db, ai, settings, lead_id)
                # Only spend money on drafts for companies that might fit.
                if write_drafts and needs_drafts(lead):
                    draft_one(db, ai, settings, lead_id)
                summary["done"].append(name)
                message = f"Finished {name}"
        except BudgetExceeded as error:
            # Out of budget: stop the whole batch rather than fail each company.
            summary["failed"].append((name, str(error)))
            if on_progress:
                on_progress(number, len(lead_ids), str(error))
            break
        except Exception as error:
            # Any problem with one company shouldn't stop the rest.
            summary["failed"].append((name, str(error)))
            message = f"Problem with {name}: {error}"
        if on_progress:
            on_progress(number, len(lead_ids), message)

    return summary
