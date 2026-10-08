"""The Companies and Drafts tabs."""

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
from contacts import best_contact, linkedin_links
from snapshot import RESULT_WORDS, buy_box_lines, checks_met, lead_snapshot, short_name, sort_by_checks

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


def no_math(text):
    """Escape $ signs: Streamlit treats text between two $ signs as a math formula."""
    return str(text).replace("$", "\\$")


def friendly_time(value):
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y %H:%M UTC")
    except (TypeError, ValueError):
        return value or ""


def flash(message):
    """Show a message after the page refreshes."""
    st.session_state["leads_message"] = message


def leads_tab(db, ai, settings, read_only=False):
    """The Companies tab: snapshot cards, sorted by buy-box checks met."""
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

    if not read_only:
        st.caption(no_math(
            f"AI usage so far: {usage['requests']} requests, {usage['web_searches']} web searches, "
            f"about ${usage['estimated_cost_usd']:.2f}"
            + (f" of the ${ai.budget_usd:.2f} budget" if ai is not None and getattr(ai, "budget_usd", None) else "")
            + ". (Estimate only; check OpenAI's billing page.)"
        ))

    buy_box_section(settings, read_only)

    if not leads:
        st.info("No companies yet. Add some in the Find tab.")
        return

    # Detail view: one company, opened from its card.
    open_id = st.session_state.get("open_lead")
    lead = next((item for item in leads if item["id"] == open_id), None)
    if lead is not None:
        if st.button("← Back to all companies"):
            st.session_state.pop("open_lead", None)
            st.rerun()
        show_lead(db, ai, settings, lead, read_only)
        return

    # List view: a snapshot card per company, best matches first.
    leads = sort_by_checks(filter_section(leads))
    if not leads:
        st.info("No companies match these filters.")
        return

    st.download_button(
        "Download spreadsheet (CSV)",
        data=leads_to_csv(leads),
        file_name="sterling-leads.csv",
        mime="text/csv",
    )
    for item in leads:
        snapshot_card(item)


FIT_COLORS = {"Fits": "green", "Check": "orange", "No fit": "red", "Not checked": "gray"}


def buy_box_section(settings, read_only=False):
    with st.expander("John's buy box (what a good lead looks like)"):
        for label, value in buy_box_lines(settings):
            st.markdown(no_math(f"**{label}:** {value}"))
        if read_only:
            st.caption("Ask Oliver if any of these should change.")
        else:
            st.caption("To change these, use the Settings tab.")


def snapshot_card(lead):
    snap = lead_snapshot(lead)
    with st.container(border=True):
        top, button = st.columns([5, 1])
        color = FIT_COLORS.get(snap["fit"], "gray")
        checks = f" &nbsp; {snap['checks']}" if snap["checks"] else ""
        top.markdown(no_math(f"**{snap['name']}** &nbsp; :{color}-badge[{snap['fit']}]{checks}"))
        if snap["place"]:
            top.caption(no_math(snap["place"]))
        if button.button("Open", key=f"open_{lead['id']}"):
            st.session_state["open_lead"] = lead["id"]
            st.rerun()
        st.markdown(no_math(f"**Owner:** {snap['owner']}"))
        st.markdown(no_math(email_line(snap["email"], snap["email_kind"], snap["email_label"])))
        st.markdown(no_math(snap["reason"]))
        st.caption(f"{snap['drafts']} · Status: {snap['status']}")
        for flag in snap["flags"]:
            st.markdown(no_math(f":red[⚠ {flag}]"))


def email_line(email, kind, label):
    if kind == "owner":
        return f"**Email:** {email} :green-badge[Owner]"
    if kind == "general":
        return f"**Email:** {email} :orange-badge[General inbox, not the owner]"
    return "**Email:** :gray-badge[None found]"


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
        sources = col1.multiselect("Found by", ["provided", "discovered"])
        min_checks = col2.slider("At least this many buy-box checks met", 0, 5, 0)
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
        min_checks=min_checks,
    )
    if len(leads) != len(all_leads):
        st.caption(f"Showing {len(leads)} of {len(all_leads)} companies. The download includes only these.")
    return leads


def show_lead(db, ai, settings, lead, read_only=False):
    snap = lead_snapshot(lead)
    color = FIT_COLORS.get(snap["fit"], "gray")
    st.subheader(lead["name"])
    st.markdown(no_math(f":{color}-badge[{snap['fit']}] &nbsp; {snap['checks']}"))
    if lead["website"]:
        st.write(lead["website"])

    contact_section(lead.get("research") or {}, snap)
    if lead.get("research"):
        drafts_section(db, ai, settings, lead, read_only)

    if read_only:
        st.markdown(f"**Review status:** {lead['status']}")
    else:
        status_section(db, lead)
    research_section(db, ai, settings, lead, read_only)

    if lead["source"] == "discovered":
        with st.expander("Why the search found this company"):
            st.caption(no_math(lead["discovery_reason"]))
            for url in lead.get("discovery_sources") or []:
                st.caption(f"- {url}")


def contact_section(research, snap):
    """Who to contact, up front."""
    with st.container(border=True):
        st.markdown("#### Contact")
        st.markdown(no_math(f"**Owner:** {snap['owner']}"))
        contact = best_contact(research)
        st.markdown(no_math(email_line(contact["email"], contact["kind"], contact["label"])))
        if contact["email"]:
            st.code(contact["email"], language=None)
        if contact["kind"] == "general":
            st.caption("This is a shared company inbox, not the owner's own address. Ask for the owner by name.")
        elif contact["kind"] is None and research:
            st.caption("No published email. Try the LinkedIn links or the company's contact form.")
        phone = (research.get("public_phone") or {}).get("value")
        if phone and (research.get("public_phone") or {}).get("status") != "unknown":
            st.markdown(f"**Phone:** {phone}")
        for label, url in linkedin_links(research):
            st.markdown(f"**{label}:** {url}")


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


def research_section(db, ai, settings, lead, read_only=False):
    st.markdown("### Research and buy box")
    if lead.get("research_error"):
        st.error(no_math(f"Last research attempt failed: {lead['research_error']}"))

    research = lead.get("research")
    if research:
        st.caption(f"Researched: {friendly_time(lead.get('researched_at'))}")
        show_qualification(lead)
        show_research(research, lead.get("research_sources") or [])
        if read_only:
            return
        again = st.checkbox(
            "Research again (uses AI credits; drafts are kept)", key=f"again_{lead['id']}"
        )
        if not again:
            return

    if read_only:
        st.info("Not researched yet.")
        return
    if ai is None:
        st.info(AI_SETUP_MESSAGE)
        return
    if st.button("Research this company", key=f"research_{lead['id']}", type="primary"):
        with st.spinner(f"Researching {lead['name']}... this can take a minute."):
            try:
                research_one(db, ai, settings, lead["id"])
            except Exception as error:
                st.error(no_math(f"Research failed: {error}"))
                return
        flash(f"Research saved for {lead['name']}.")
        st.rerun()


def show_qualification(lead):
    qualification = lead.get("qualification") or {}
    result = lead["qualification_result"]
    st.markdown("#### How it compares with John's buy box")
    message = no_math(f"**{result}**: {qualification.get('summary', '')}")
    if result == MEETS:
        st.success(message)
    elif result == DOES_NOT_MEET:
        st.error(message)
    else:
        st.warning(message)
    st.dataframe(
        [
            {
                "Buy box": short_name(c["criterion"]).capitalize(),
                "Result": f"{RESULT_ICONS[c['result']]} {RESULT_WORDS[c['result']]}",
                "Why": c["reason"],
                "Sources": "\n".join(c["sources"]),
            }
            for c in qualification.get("criteria", [])
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption("“Meets” means backed by a cited source. " + SOURCE_NOTE)


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

    news = research.get("recent_news") or []
    if news:
        st.markdown("**Recent news**")
        for item in news:
            when = f"{item['date']}: " if item.get("date") else ""
            st.markdown(no_math(f"- {when}{item['headline']} ({', '.join(item['sources'])})"))

    context = research.get("outreach_context") or []
    if context:
        st.markdown("**Useful context for outreach**")
        for item in context:
            st.markdown(no_math(f"- {item['fact']} ({', '.join(item['sources'])})"))

    with st.expander(f"Every page the search looked at ({len(seen_urls)})"):
        for url in seen_urls:
            st.write(url)


def drafts_section(db, ai, settings, lead, read_only=False):
    st.markdown("### Email draft")
    st.caption("Drafts are for you to review, copy and send yourself. Nothing is sent from here.")

    if read_only:
        if not lead.get("email_body"):
            st.info("No drafts yet.")
            return
        st.markdown("**Email subject**")
        st.code(lead["email_subject"], language=None)
        st.markdown("**Email**")
        st.code(lead["email_body"], language=None, wrap_lines=True)
        st.markdown("**LinkedIn note**")
        st.code(lead["linkedin_note"], language=None, wrap_lines=True)
        return

    has_drafts = bool(lead.get("email_body"))
    if has_drafts:
        if lead.get("drafts_edited_at"):
            st.caption(f"Edited {friendly_time(lead['drafts_edited_at'])}")
        elif lead.get("drafts_generated_at"):
            st.caption(f"Written by AI {friendly_time(lead['drafts_generated_at'])}")

        for warning in draft_warnings(lead, lead.get("research")):
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
                st.error(no_math(f"Couldn't write drafts: {error}"))
                return
        flash("New drafts saved.")
        st.rerun()


def drafts_tab(db, read_only=False):
    """Every draft in one place, waiting for approval first."""
    if db is None:
        st.warning("Connect the database first (see the Settings tab).")
        return
    if "drafts_message" in st.session_state:
        st.success(st.session_state.pop("drafts_message"))
    try:
        leads = [lead for lead in list_leads(db) if lead.get("email_body")]
    except LeadsStoreError as error:
        st.error(str(error))
        return
    if not leads:
        st.info("No drafts yet. Research a company and write drafts first.")
        return

    waiting = [l for l in leads if l["status"] not in ("approved", "manually contacted")]
    approved = [l for l in leads if l["status"] == "approved"]
    contacted = [l for l in leads if l["status"] == "manually contacted"]
    st.caption(
        f"{len(waiting)} waiting for approval · {len(approved)} approved · {len(contacted)} contacted. "
        "Nothing is sent from here: copy each approved email and send it yourself."
    )

    for title, group in [("Waiting for approval", waiting), ("Approved, ready to send by hand", approved), ("Contacted", contacted)]:
        if not group:
            continue
        st.markdown(f"### {title}")
        for lead in sort_by_checks(group):
            draft_card(db, lead, read_only)


def draft_card(db, lead, read_only):
    research = lead.get("research") or {}
    contact = best_contact(research)
    with st.container(border=True):
        st.markdown(no_math(f"**{lead['name']}** &nbsp; {checks_met(lead)[0]} of {checks_met(lead)[1]} checks met"))
        st.markdown(no_math("To: " + email_line(contact["email"], contact["kind"], contact["label"]).replace("**Email:** ", "")))
        st.markdown(no_math(f"**Subject:** {lead['email_subject']}"))
        st.code(lead["email_body"], language=None, wrap_lines=True)
        for warning in draft_warnings(lead, research):
            st.warning(warning)
        with st.expander("LinkedIn note"):
            st.code(lead["linkedin_note"], language=None, wrap_lines=True)
        if read_only:
            return
        col1, col2, col3 = st.columns(3)
        if lead["status"] not in ("approved", "manually contacted"):
            if col1.button("Approve", key=f"approve_{lead['id']}", type="primary"):
                _set(db, lead, "approved", f"Approved the draft for {lead['name']}.")
        if lead["status"] == "approved":
            if col1.button("I sent it", key=f"sent_{lead['id']}",
                           help="Marks it 'manually contacted' after you've sent it yourself."):
                _set(db, lead, "manually contacted", f"Marked {lead['name']} as contacted.")
        if col2.button("Edit in Companies", key=f"edit_{lead['id']}"):
            st.session_state["open_lead"] = lead["id"]
            st.session_state["drafts_message"] = f"{lead['name']} is open in the Companies tab."
            st.rerun()


def _set(db, lead, status, message):
    try:
        set_status(db, lead["id"], status)
    except LeadsStoreError as error:
        st.error(str(error))
        return
    st.session_state["drafts_message"] = message
    st.rerun()
