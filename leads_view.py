"""The Leads tab: a list of companies, and a detail view for one of them."""

from datetime import datetime

import streamlit as st

from batch import draft_one, research_one
from drafting import LINKEDIN_LIMIT, draft_warnings
from export import leads_to_csv
from lead_filters import filter_leads
from leads_store import (
    STATUSES,
    LeadsStoreError,
    drafts_are_protected,
    list_leads,
    save_draft_edits,
    set_status,
    usage_totals,
)
from qualification import DOES_NOT_MEET, MEETS, NEEDS_REVIEW
from research import FACT_FIELDS, RANGE_FIELDS

AI_SETUP_MESSAGE = (
    "AI research isn't set up yet. Add OPENAI_API_KEY to .streamlit/secrets.toml "
    "(see the README), then restart the app."
)

STATUS_ICONS = {"verified": "✅ cited", "estimate": "🟡 estimate", "unknown": "⬜ unknown"}
SOURCE_NOTE = (
    "“Cited” means the AI named a source and the web search really opened that page. "
    "The app doesn't check that the page says it, so open the link before relying on it."
)
RESULT_ICONS = {"supported": "✅", "contradicted": "❌", "unknown": "❔"}


def friendly_time(value):
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y %H:%M UTC")
    except (TypeError, ValueError):
        return value or ""


def flash(message):
    """Show a message after the page refreshes."""
    st.session_state["leads_message"] = message


def leads_tab(db, ai, settings):
    if db is None:
        st.warning("Connect the database first (see the Settings tab).")
        return

    if "leads_message" in st.session_state:
        st.success(st.session_state.pop("leads_message"))

    try:
        leads = list_leads(db)
        usage = usage_totals(db)
    except LeadsStoreError as error:
        st.error(f"{error}\n\nIf this is new, run supabase/schema.sql again in Supabase.")
        return

    st.caption(
        f"AI usage so far: {usage['requests']} requests, {usage['web_searches']} web searches, "
        f"about ${usage['estimated_cost_usd']:.2f}"
        + (f" of the ${ai.budget_usd:.2f} budget" if ai is not None and getattr(ai, "budget_usd", None) else "")
        + ". (Estimate only; check OpenAI's billing page.)"
    )

    if not leads:
        st.info("No companies yet. Add some in the Find leads tab.")
        return

    leads = filter_section(leads)
    if not leads:
        st.info("No companies match these filters.")
        return

    st.dataframe(
        [
            {
                "Company": lead["name"],
                "Status": lead["status"],
                "Qualification": lead["qualification_result"] or "not checked",
                "Owner": ((lead.get("research") or {}).get("owner_name") or {}).get("value") or "",
                "Found by": lead["source"],
            }
            for lead in leads
        ],
        hide_index=True,
        width="stretch",
    )

    st.download_button(
        "Download spreadsheet (CSV)",
        data=leads_to_csv(leads),
        file_name="sterling-leads.csv",
        mime="text/csv",
    )

    st.divider()
    names = {lead["id"]: f"{lead['name']} ({lead['status']})" for lead in leads}
    lead_id = st.selectbox("Open a company", list(names), format_func=names.get)
    lead = next(item for item in leads if item["id"] == lead_id)
    show_lead(db, ai, settings, lead)


def filter_section(all_leads):
    """Show the filter controls and return the leads that match."""
    with st.expander("Filter companies"):
        search = st.text_input("Search company or owner name")
        col1, col2 = st.columns(2)
        results = col1.multiselect(
            "Qualification", [MEETS, NEEDS_REVIEW, DOES_NOT_MEET, "Not checked"]
        )
        statuses = col2.multiselect("Review status", STATUSES)
        industry = col1.text_input("Industry or product contains")
        location = col2.text_input("City or state contains")
        revenue_min = col1.number_input("Revenue at least ($M)", min_value=0.0, value=None, step=1.0)
        revenue_max = col2.number_input("Revenue at most ($M)", min_value=0.0, value=None, step=1.0)
        reps_min = col1.number_input("Salespeople at least", min_value=0, value=None, step=1)
        reps_max = col2.number_input("Salespeople at most", min_value=0, value=None, step=1)
        sources = st.multiselect("Found by", ["provided", "discovered"])
        include_unknown = st.checkbox(
            "Keep companies whose revenue or sales team is unknown", value=True
        )

    millions = lambda value: None if value is None else value * 1_000_000
    leads = filter_leads(
        all_leads,
        search=search,
        results=results,
        statuses=statuses,
        sources=sources,
        industry=industry,
        location=location,
        revenue_min=millions(revenue_min),
        revenue_max=millions(revenue_max),
        reps_min=reps_min,
        reps_max=reps_max,
        include_unknown=include_unknown,
    )
    if len(leads) != len(all_leads):
        st.caption(f"Showing {len(leads)} of {len(all_leads)} companies. The download includes only these.")
    return leads


def show_lead(db, ai, settings, lead):
    st.subheader(lead["name"])
    if lead["website"]:
        st.write(lead["website"])
    if lead["source"] == "discovered":
        st.caption(f"Found by search: {lead['discovery_reason']}")
        for url in lead.get("discovery_sources") or []:
            st.caption(f"- {url}")

    status_section(db, lead)
    research_section(db, ai, settings, lead)
    if lead.get("research"):
        drafts_section(db, ai, settings, lead)


def status_section(db, lead):
    col1, col2 = st.columns([3, 1])
    new_status = col1.selectbox(
        "Review status",
        STATUSES,
        index=STATUSES.index(lead["status"]),
        key=f"status_{lead['id']}",
        help="'Manually contacted' means a person sent the message themselves. The app never sends anything.",
    )
    col2.write("")
    if col2.button("Save status", key=f"save_status_{lead['id']}"):
        try:
            set_status(db, lead["id"], new_status)
        except LeadsStoreError as error:
            st.error(error)
            return
        flash(f"Status saved: {new_status}.")
        st.rerun()


def research_section(db, ai, settings, lead):
    st.markdown("### Research")
    if lead.get("research_error"):
        st.error(f"Last research attempt failed: {lead['research_error']}")

    research = lead.get("research")
    if research:
        st.caption(f"Researched: {friendly_time(lead.get('researched_at'))}")
        show_qualification(lead)
        show_research(research, lead.get("research_sources") or [])
        again = st.checkbox(
            "Research again (uses AI credits; drafts are kept)", key=f"again_{lead['id']}"
        )
        if not again:
            return

    if ai is None:
        st.info(AI_SETUP_MESSAGE)
        return
    if st.button("Research this company", key=f"research_{lead['id']}", type="primary"):
        with st.spinner(f"Researching {lead['name']}... this can take a minute."):
            try:
                research_one(db, ai, settings, lead["id"])
            except Exception as error:
                st.error(f"Research failed: {error}")
                return
        flash(f"Research saved for {lead['name']}.")
        st.rerun()


def show_qualification(lead):
    qualification = lead.get("qualification") or {}
    result = lead["qualification_result"]
    message = f"**{result}**: {qualification.get('summary', '')}"
    if result == MEETS:
        st.success(message)
    elif result == DOES_NOT_MEET:
        st.error(message)
    else:
        st.warning(message)
    st.dataframe(
        [
            {
                "Criterion": c["criterion"],
                "Result": f"{RESULT_ICONS[c['result']]} {c['result']}",
                "Why": c["reason"],
                "Sources": "\n".join(c["sources"]),
            }
            for c in qualification.get("criteria", [])
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption("“Supported” means backed by a cited source. " + SOURCE_NOTE)


def show_research(research, seen_urls):
    rows = []
    for name in list(FACT_FIELDS) + list(RANGE_FIELDS):
        fact = research.get(name) or {}
        value = fact.get("value")
        if name in RANGE_FIELDS and not value and fact.get("low") is not None:
            value = f"{fact.get('low'):,.0f} to {fact.get('high'):,.0f}"
        rows.append(
            {
                "Fact": name.replace("_", " ").capitalize(),
                "Value": value or "",
                "Status": STATUS_ICONS.get(fact.get("status"), "⬜ unknown"),
                "Sources": "\n".join(fact.get("sources") or []),
                "Note": fact.get("note", ""),
            }
        )
    with st.expander("All research facts", expanded=False):
        st.caption(SOURCE_NOTE)
        st.dataframe(rows, hide_index=True, width="stretch")

    context = research.get("outreach_context") or []
    if context:
        st.markdown("**Useful context for outreach**")
        for item in context:
            st.markdown(f"- {item['fact']} ({', '.join(item['sources'])})")

    with st.expander(f"Every page the search looked at ({len(seen_urls)})"):
        for url in seen_urls:
            st.write(url)


def drafts_section(db, ai, settings, lead):
    st.markdown("### Drafts")
    st.caption("Drafts are for you to review, copy and send yourself. Nothing is sent from here.")

    has_drafts = bool(lead.get("email_body"))
    if has_drafts:
        if lead.get("drafts_edited_at"):
            st.caption(f"Edited {friendly_time(lead['drafts_edited_at'])}")
        elif lead.get("drafts_generated_at"):
            st.caption(f"Written by AI {friendly_time(lead['drafts_generated_at'])}")

        for warning in draft_warnings(lead):
            st.warning(warning)

        with st.form(f"drafts_{lead['id']}"):
            subject = st.text_input("Email subject", lead["email_subject"])
            body = st.text_area("Email body", lead["email_body"], height=260)
            note = st.text_area("LinkedIn note", lead["linkedin_note"], height=110)
            st.caption(f"LinkedIn note: {len(note)} of {LINKEDIN_LIMIT} characters")
            if st.form_submit_button("Save edits"):
                try:
                    save_draft_edits(db, lead["id"], subject, body, note)
                except LeadsStoreError as error:
                    st.error(f"{error}\n\nYour edits were not saved. Copy them somewhere safe.")
                    return
                flash("Edits saved.")
                st.rerun()

        with st.expander("Copy the drafts (use the copy icon in each box)"):
            st.code(lead["email_subject"], language=None)
            st.code(lead["email_body"], language=None, wrap_lines=True)
            st.code(lead["linkedin_note"], language=None, wrap_lines=True)

        st.button(
            "Save to mailbox drafts",
            disabled=True,
            key=f"mailbox_{lead['id']}",
            help="Pending setup: no mailbox is connected yet. Copy the email instead.",
        )
        st.caption("Saving to a mailbox: pending setup (no mailbox connected yet).")

    if ai is None:
        st.info(AI_SETUP_MESSAGE)
        return

    replace = True
    if has_drafts and drafts_are_protected(lead):
        replace = st.checkbox(
            "Replace my edited or approved drafts with new ones",
            key=f"replace_{lead['id']}",
        )
    label = "Write new drafts" if has_drafts else "Write drafts"
    if st.button(label, key=f"draft_{lead['id']}", disabled=not replace):
        with st.spinner("Writing drafts..."):
            try:
                draft_one(db, ai, settings, lead["id"], replace_protected=replace)
            except Exception as error:
                st.error(f"Couldn't write drafts: {error}")
                return
        flash("New drafts saved.")
        st.rerun()
