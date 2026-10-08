"""Settings > Accounts: Oliver adds people and chooses what they can do."""

import streamlit as st

import auth


def accounts_section(db, admin_username):
    st.divider()
    st.subheader("Accounts")
    st.caption(
        f"Who can sign in. You sign in as **{admin_username}** with the app password "
        "from your secrets. Full access can do everything; View only can look around "
        "and download, but can't change anything or run searches."
    )
    if db is None:
        st.info("Connect the database first to add accounts.")
        return

    if "accounts_message" in st.session_state:
        st.success(st.session_state.pop("accounts_message"))

    try:
        users = auth.list_users(db)
    except auth.AuthError as error:
        st.error(f"{error}\n\nIf this is new, run supabase/schema.sql again in Supabase.")
        return

    if users:
        st.dataframe(
            [
                {
                    "Username": u["username"],
                    "Access": auth.ROLES.get(u["role"], u["role"]),
                    "Last signed in": (u.get("last_login_at") or "never")[:16].replace("T", " "),
                }
                for u in users
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No other accounts yet.")

    with st.expander("Add someone yourself (you choose their password)"):
        with st.form("add_account", clear_on_submit=True):
            username = st.text_input("Username (e.g. john)")
            password = st.text_input(
                f"Password (at least {auth.MIN_PASSWORD_LENGTH} characters)", type="password"
            )
            role = st.radio("Access", list(auth.ROLES), format_func=auth.ROLES.get, horizontal=True, index=1)
            if st.form_submit_button("Add account"):
                try:
                    auth.create_user(db, username, password, role, admin_username)
                except auth.AuthError as error:
                    st.error(str(error))
                else:
                    st.session_state["accounts_message"] = f"Added {username.strip().lower()}."
                    st.rerun()

    invites_section(db)

    if not users:
        return

    with st.expander("Change or remove someone"):
        names = [u["username"] for u in users]
        who = st.selectbox("Account", names)
        current = next(u for u in users if u["username"] == who)

        new_role = st.radio(
            "Access", list(auth.ROLES), format_func=auth.ROLES.get, horizontal=True,
            index=list(auth.ROLES).index(current["role"]), key="change_role",
        )
        if st.button("Save access") and new_role != current["role"]:
            _do(lambda: auth.set_role(db, who, new_role), f"{who} now has {auth.ROLES[new_role]}.")

        new_password = st.text_input("New password", type="password", key="new_password")
        if st.button("Set new password"):
            _do(lambda: auth.set_password(db, who, new_password), f"New password set for {who}.")

        confirm = st.checkbox(f"Yes, remove {who}", key="confirm_remove")
        if st.button("Remove account", disabled=not confirm):
            _do(lambda: auth.delete_user(db, who), f"Removed {who}.")


def _do(action, message):
    try:
        action()
    except auth.AuthError as error:
        st.error(str(error))
        return
    st.session_state["accounts_message"] = message
    st.rerun()


def invites_section(db):
    with st.expander("Invite someone (they choose their own username and password)", expanded=True):
        st.caption(
            f"Creates a link that works once and expires after {auth.INVITE_DAYS} days. "
            "Send it to the person yourself, e.g. by text or email."
        )
        col1, col2 = st.columns([2, 1])
        note = col1.text_input("Who is it for? (just a note for you)", placeholder="John")
        role = col2.radio("Access", list(auth.ROLES), format_func=auth.ROLES.get, index=1, key="invite_role")
        if st.button("Create invite link", type="primary"):
            try:
                code = auth.create_invite(db, role, note)
            except auth.AuthError as error:
                st.error(str(error))
            else:
                st.success("Invite link created. Copy it now; it won't be shown again.")
                st.code(invite_link(code), language=None)

        try:
            open_invites = auth.list_open_invites(db)
        except auth.AuthError:
            open_invites = []
        for invite in open_invites:
            col1, col2 = st.columns([4, 1])
            col1.caption(
                f"Open invite{' for ' + invite['note'] if invite['note'] else ''} "
                f"({auth.ROLES[invite['role']]}), expires {str(invite['expires_at'])[:10]}"
            )
            if col2.button("Cancel", key=f"cancel_{invite['code_hash'][:12]}"):
                auth.cancel_invite(db, invite["code_hash"])
                st.rerun()


def invite_link(code):
    """The app's own address with the invite code on the end."""
    base = (st.context.url or "").split("?")[0].rstrip("/")
    return f"{base}/?invite={code}"
