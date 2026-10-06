"""The Find leads tab: add companies, discover new ones, and process a batch."""

import streamlit as st

from batch import MAX_BATCH, needs_drafts, needs_research, needs_retry, process_batch
from discovery import MAX_DISCOVERY, discover_companies
from leads_store import LeadsStoreError, add_companies, check_budget, list_leads, log_usage
from leads_view import AI_SETUP_MESSAGE, flash, no_math

# Rough cost per company, used only for the estimate shown before a batch.
ESTIMATED_COST_PER_COMPANY = 0.15


def parse_company_lines(text):
    """Turn lines like 'Acme Software, acme.com' into company dicts."""
    companies = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, _, website = line.partition(",")
        companies.append({"name": name.strip(), "website": website.strip()})
    return companies


def find_tab(db, ai, settings):
    if db is None:
        st.warning("Connect the database first (see the Settings tab).")
        return

    if "find_message" in st.session_state:
        st.success(st.session_state.pop("find_message"))

    add_section(db)
    st.divider()
    discover_section(db, ai, settings)
    st.divider()
    batch_section(db, ai, settings)


def add_section(db):
    st.markdown("### Add companies you already know")
    with st.form("add_companies", clear_on_submit=True):
        text = st.text_area(
            "One company per line: name, then a comma and the website (optional)",
            placeholder="Acme Software, acmesoftware.com\nPalmetto Data Co",
        )
        submitted = st.form_submit_button("Add companies")
    if not submitted:
        return
    companies = parse_company_lines(text)
    if not companies:
        st.warning("Type at least one company name.")
        return
    try:
        added, skipped = add_companies(db, companies, source="provided")
    except LeadsStoreError as error:
        st.error(f"{error}\n\nNothing was added.")
        return
    message = f"Added {len(added)} companies."
    if skipped:
        message += f" Skipped duplicates: {', '.join(skipped)}."
    st.session_state["find_message"] = message
    st.rerun()


def discover_section(db, ai, settings):
    st.markdown("### Find new companies")
    st.caption(
        f"Searches the web for companies in {settings['geography']} that may fit. "
        "These are only candidates until they're researched."
    )
    if ai is None:
        st.info(AI_SETUP_MESSAGE)
        return
    count = st.number_input("How many to look for", 1, MAX_DISCOVERY, 5)
    run_all = st.checkbox(
        "Then research them and write drafts right away (one click, start to finish)",
        value=True,
    )
    if not st.button("Search for companies"):
        return
    try:
        check_budget(db, getattr(ai, "budget_usd", None))
        existing = [lead["name"] for lead in list_leads(db)]
        with st.spinner("Searching... this can take a minute."):
            candidates, usage = discover_companies(ai, settings, int(count), existing)
        log_usage(db, "discovery", usage)
        added, skipped = add_companies(db, candidates, source="discovered")
    except Exception as error:
        st.error(no_math(f"Search failed: {error}"))
        return

    st.success(f"Found {len(candidates)} candidates. Added {len(added)} new; {len(skipped)} were already on the list.")
    for company in candidates:
        st.markdown(no_math(f"**{company['name']}** {company['website']}  \n{company['reason']}"))
        for url in company["sources"]:
            st.caption(f"- {url}")

    if run_all and added:
        run_batch(db, ai, settings, [row["id"] for row in added], write_drafts=True, redo=False)


def run_batch(db, ai, settings, lead_ids, write_drafts, redo):
    """Process leads with a progress bar and show the outcome."""
    progress = st.progress(0.0, text="Starting...")

    def on_progress(done, total, message):
        progress.progress(done / total, text=f"{done} of {total}: {message}")

    summary = process_batch(
        db, ai, settings, lead_ids,
        write_drafts=write_drafts, redo=redo, on_progress=on_progress,
    )
    text = f"Done: {len(summary['done'])} finished, {len(summary['skipped'])} skipped, {len(summary['failed'])} failed."
    if summary["failed"]:
        st.warning(text)
        for name, error in summary["failed"]:
            st.error(no_math(f"{name}: {error}"))
        st.caption("Finished companies are saved. Use 'Retry failed or missing drafts' to try the others again.")
    else:
        st.success(text + " Open the Leads tab to review the drafts.")


def batch_section(db, ai, settings):
    st.markdown("### Research a batch")
    try:
        leads = list_leads(db)
    except LeadsStoreError as error:
        st.error(error)
        return
    if not leads:
        st.info("Add or find some companies first.")
        return

    names = {lead["id"]: f"{lead['name']} ({lead['status']})" for lead in leads}
    waiting = [lead["id"] for lead in leads if needs_research(lead) or needs_drafts(lead)]
    failed = [lead["id"] for lead in leads if needs_retry(lead)]

    chosen = st.multiselect(
        f"Companies to process (up to {MAX_BATCH} at a time)",
        list(names),
        default=waiting[:MAX_BATCH],
        format_func=names.get,
        max_selections=MAX_BATCH,
    )
    write_drafts = st.checkbox("Also write drafts for companies that might fit", value=True)
    redo = st.checkbox("Redo companies that are already researched (costs more)")
    by_id = {lead["id"]: lead for lead in leads}
    to_run = [i for i in chosen if redo or needs_research(by_id[i])]
    st.caption(no_math(
        f"{len(to_run)} will be researched (others only get missing drafts). Rough cost: about "
        f"${len(to_run) * ESTIMATED_COST_PER_COMPANY:.2f}."
    ))

    if ai is None:
        st.info(AI_SETUP_MESSAGE)
        return

    col1, col2 = st.columns(2)
    run = col1.button("Process selected", type="primary", disabled=not chosen)
    retry = col2.button(f"Retry failed or missing drafts ({len(failed)})", disabled=not failed)
    if not (run or retry):
        return

    lead_ids = failed if retry else chosen
    run_batch(db, ai, settings, lead_ids, write_drafts=write_drafts or retry, redo=redo and not retry)
