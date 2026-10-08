"""Accounts, passwords and "keep me signed in" sessions.

- Passwords are stored as scrypt hashes (Python's built-in hashlib), never as
  plain text, and each has its own random salt.
- Two roles: "full" (everything) and "view" (look around only).
- Oliver's own login comes from secrets (ADMIN_USERNAME + APP_PASSWORD), so
  he can never be locked out. Everyone else is added by him in Settings.
- "Keep me signed in" gives the browser a random token (in a cookie). Only a
  hash of the token is saved in the database, with an expiry date, so a
  database leak doesn't hand out logins. Signing out deletes it.

No Streamlit code here, so it's tested in tests/test_auth.py.
"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

USERS = "app_users"
SESSIONS = "app_sessions"
INVITES = "app_invites"
INVITE_DAYS = 7
ROLES = {"full": "Full access", "view": "View only"}
REMEMBER_DAYS = 30
MIN_PASSWORD_LENGTH = 10
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,40}$")

# scrypt settings (memory-hard, so guessing passwords is slow).
_N, _R, _P = 2**14, 8, 1


class AuthError(Exception):
    """Raised for problems a person should see (bad input, database trouble)."""


# ---- Passwords --------------------------------------------------------------

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    encode = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_N}${_R}${_P}${encode(salt)}${encode(digest)}"


def verify_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def check_new_account(username, password, role):
    """Return a list of problems with a new account (empty if fine)."""
    problems = []
    if not USERNAME_PATTERN.match(username):
        problems.append("Usernames are 3 to 40 characters: lower-case letters, numbers, . _ or -.")
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    if role not in ROLES:
        problems.append("Pick Full access or View only.")
    return problems


# ---- Accounts ---------------------------------------------------------------

def _run(query, action):
    try:
        return query.execute()
    except Exception as error:
        raise AuthError(f"Couldn't {action}: {error}") from error


def list_users(db):
    return _run(db.table(USERS).select("username, role, created_at, last_login_at").order("username"), "load accounts").data or []


def create_user(db, username, password, role, admin_username):
    username = username.strip().lower()
    problems = check_new_account(username, password, role)
    if username == admin_username:
        problems.append("That username is Oliver's main login.")
    if problems:
        raise AuthError(" ".join(problems))
    if any(u["username"] == username for u in list_users(db)):
        raise AuthError("That username is already taken.")
    row = {"username": username, "password_hash": hash_password(password), "role": role}
    response = _run(db.table(USERS).insert(row), "add the account")
    if not response.data:
        raise AuthError("The database didn't confirm the new account.")


def set_password(db, username, password):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    response = _run(
        db.table(USERS).update({"password_hash": hash_password(password)}).eq("username", username),
        "change the password",
    )
    if not response.data:
        raise AuthError("The database didn't confirm the change.")
    end_all_sessions(db, username)  # old remembered logins stop working


def set_role(db, username, role):
    if role not in ROLES:
        raise AuthError("Pick Full access or View only.")
    response = _run(db.table(USERS).update({"role": role}).eq("username", username), "change the access")
    if not response.data:
        raise AuthError("The database didn't confirm the change.")
    end_all_sessions(db, username)


def delete_user(db, username):
    _run(db.table(USERS).delete().eq("username", username), "remove the account")
    end_all_sessions(db, username)


def authenticate(db, username, password, admin_username, admin_password):
    """Return the role ("full"/"view") if the username and password match, else None."""
    username = username.strip().lower()
    if not username or not password:
        return None
    if admin_password and username == admin_username:
        return "full" if hmac.compare_digest(password, admin_password) else None
    if db is None:
        return None
    rows = _run(db.table(USERS).select("*").eq("username", username).limit(1), "check the login").data
    if not rows or not verify_password(password, rows[0]["password_hash"]):
        return None
    try:
        db.table(USERS).update({"last_login_at": _now().isoformat()}).eq("username", username).execute()
    except Exception:
        pass  # not being able to note the time shouldn't block the login
    return rows[0]["role"]


# ---- Invites -------------------------------------------------------------------

def create_invite(db, role="view", note="", days=INVITE_DAYS):
    """Make a one-time invite. Returns the code to put in the link."""
    if role not in ROLES:
        raise AuthError("Pick Full access or View only.")
    code = secrets.token_urlsafe(24)
    row = {
        "code_hash": _hash_token(code),
        "role": role,
        "note": note.strip()[:100],
        "expires_at": (_now() + timedelta(days=days)).isoformat(),
    }
    response = _run(db.table(INVITES).insert(row), "create the invite")
    if not response.data:
        raise AuthError("The database didn't confirm the invite.")
    return code


def check_invite(db, code):
    """Return the invite if the code is valid, unused and not expired, else None."""
    if not code or db is None:
        return None
    try:
        rows = db.table(INVITES).select("*").eq("code_hash", _hash_token(code)).limit(1).execute().data
    except Exception:
        return None
    if not rows or rows[0].get("used_at"):
        return None
    expires = datetime.fromisoformat(str(rows[0]["expires_at"]).replace("Z", "+00:00"))
    return rows[0] if expires > _now() else None


def accept_invite(db, code, username, password, admin_username):
    """Create the account an invite allows, and use the invite up. Returns the role."""
    invite = check_invite(db, code)
    if invite is None:
        raise AuthError("This invite link isn't valid any more. Ask Oliver for a new one.")
    create_user(db, username, password, invite["role"], admin_username)
    _run(
        db.table(INVITES)
        .update({"used_at": _now().isoformat(), "used_by": username.strip().lower()})
        .eq("code_hash", invite["code_hash"]),
        "use up the invite",
    )
    return invite["role"]


def list_open_invites(db):
    rows = _run(db.table(INVITES).select("*").order("created_at"), "load invites").data or []
    now = _now()
    return [
        r for r in rows
        if not r.get("used_at")
        and datetime.fromisoformat(str(r["expires_at"]).replace("Z", "+00:00")) > now
    ]


def cancel_invite(db, code_hash):
    _run(db.table(INVITES).delete().eq("code_hash", code_hash), "cancel the invite")


# ---- Remembered sessions ----------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, username, role, days=REMEMBER_DAYS):
    """Save a remembered login. Returns the token to put in the browser cookie."""
    token = secrets.token_urlsafe(32)
    row = {
        "token_hash": _hash_token(token),
        "username": username,
        "role": role,
        "expires_at": (_now() + timedelta(days=days)).isoformat(),
    }
    response = _run(db.table(SESSIONS).insert(row), "remember the login")
    if not response.data:
        raise AuthError("The database didn't confirm the remembered login.")
    return token


def restore_session(db, token, admin_username):
    """Return (username, role) for a valid remembered token, else None."""
    if not token or db is None:
        return None
    try:
        rows = db.table(SESSIONS).select("*").eq("token_hash", _hash_token(token)).limit(1).execute().data
    except Exception:
        return None
    if not rows:
        return None
    session = rows[0]
    expires = datetime.fromisoformat(str(session["expires_at"]).replace("Z", "+00:00"))
    if expires <= _now():
        end_session(db, token)
        return None
    username = session["username"]
    if username == admin_username:
        return username, "full"
    # Use the account's current role; a removed account can't come back in.
    try:
        users = db.table(USERS).select("role").eq("username", username).limit(1).execute().data
    except Exception:
        return None
    if not users:
        end_session(db, token)
        return None
    return username, users[0]["role"]


def end_session(db, token):
    if not token or db is None:
        return
    try:
        db.table(SESSIONS).delete().eq("token_hash", _hash_token(token)).execute()
    except Exception:
        pass


def end_all_sessions(db, username):
    try:
        db.table(SESSIONS).delete().eq("username", username).execute()
    except Exception:
        pass
