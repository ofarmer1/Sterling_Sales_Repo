"""Tests for accounts, password hashing and remembered sign-ins (fake database)."""

from datetime import datetime, timedelta, timezone

import pytest

import auth
from tests.fake_database import FakeDatabase

ADMIN = "oliver"
ADMIN_PASSWORD = "admin-secret-password"


def test_hashes_are_salted_and_verify():
    first, second = auth.hash_password("correct horse"), auth.hash_password("correct horse")
    assert first != second  # different salt each time
    assert "correct horse" not in first
    assert auth.verify_password("correct horse", first)
    assert not auth.verify_password("wrong horse", first)
    assert not auth.verify_password("anything", "not-a-hash")


def test_new_account_rules():
    assert auth.check_new_account("john", "long-enough-1", "view") == []
    assert auth.check_new_account("Jo", "long-enough-1", "view")
    assert auth.check_new_account("john smith", "long-enough-1", "view")
    assert auth.check_new_account("john", "short", "view")
    assert auth.check_new_account("john", "long-enough-1", "admin")


def test_create_and_sign_in():
    db = FakeDatabase()
    auth.create_user(db, " John ", "john-password-1", "view", ADMIN)
    assert auth.authenticate(db, "john", "john-password-1", ADMIN, ADMIN_PASSWORD) == "view"
    assert auth.authenticate(db, "JOHN", "john-password-1", ADMIN, ADMIN_PASSWORD) == "view"
    assert auth.authenticate(db, "john", "wrong", ADMIN, ADMIN_PASSWORD) is None
    assert auth.authenticate(db, "nobody", "john-password-1", ADMIN, ADMIN_PASSWORD) is None
    assert db.tables["app_users"][1]["last_login_at"]


def test_admin_comes_from_secrets_and_cannot_be_taken():
    db = FakeDatabase()
    assert auth.authenticate(db, "oliver", ADMIN_PASSWORD, ADMIN, ADMIN_PASSWORD) == "full"
    assert auth.authenticate(db, "oliver", "guess", ADMIN, ADMIN_PASSWORD) is None
    with pytest.raises(auth.AuthError, match="main login"):
        auth.create_user(db, "oliver", "some-password-1", "view", ADMIN)


def test_duplicate_usernames_refused():
    db = FakeDatabase()
    auth.create_user(db, "john", "john-password-1", "view", ADMIN)
    with pytest.raises(auth.AuthError, match="taken"):
        auth.create_user(db, "john", "other-password-1", "full", ADMIN)


def test_remembered_session_round_trip():
    db = FakeDatabase()
    auth.create_user(db, "john", "john-password-1", "view", ADMIN)
    token = auth.create_session(db, "john", "view")
    assert auth.restore_session(db, token, ADMIN) == ("john", "view")
    # Only a hash of the token is stored.
    assert all(token not in str(row) for row in db.tables["app_sessions"].values())
    assert auth.restore_session(db, "made-up-token", ADMIN) is None
    assert auth.restore_session(db, None, ADMIN) is None


def test_expired_session_is_refused_and_removed():
    db = FakeDatabase()
    auth.create_user(db, "john", "john-password-1", "view", ADMIN)
    token = auth.create_session(db, "john", "view")
    for row in db.tables["app_sessions"].values():
        row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert auth.restore_session(db, token, ADMIN) is None
    assert not db.tables["app_sessions"]


def test_sign_out_ends_the_session():
    db = FakeDatabase()
    token = auth.create_session(db, ADMIN, "full")
    assert auth.restore_session(db, token, ADMIN) == (ADMIN, "full")
    auth.end_session(db, token)
    assert auth.restore_session(db, token, ADMIN) is None


def test_removed_user_cannot_come_back_with_old_session():
    db = FakeDatabase()
    auth.create_user(db, "john", "john-password-1", "view", ADMIN)
    token = auth.create_session(db, "john", "view")
    auth.delete_user(db, "john")
    assert auth.restore_session(db, token, ADMIN) is None


def test_role_change_and_new_password_end_old_sessions():
    db = FakeDatabase()
    auth.create_user(db, "john", "john-password-1", "view", ADMIN)
    token = auth.create_session(db, "john", "view")
    auth.set_role(db, "john", "full")
    assert auth.restore_session(db, token, ADMIN) is None
    token = auth.create_session(db, "john", "full")
    auth.set_password(db, "john", "brand-new-password")
    assert auth.restore_session(db, token, ADMIN) is None
    assert auth.authenticate(db, "john", "brand-new-password", ADMIN, ADMIN_PASSWORD) == "full"


def test_database_down_means_no_remembered_login():
    db = FakeDatabase()
    token = auth.create_session(db, ADMIN, "full")
    db.fail_with = ConnectionError("down")
    assert auth.restore_session(db, token, ADMIN) is None


# ---- Invites -------------------------------------------------------------------

def test_invite_creates_a_view_account_once():
    db = FakeDatabase()
    code = auth.create_invite(db, "view", "John")
    assert all(code not in str(row) for row in db.tables["app_invites"].values())  # only a hash stored
    assert auth.check_invite(db, code)["role"] == "view"
    role = auth.accept_invite(db, code, "John", "john-password-1", ADMIN)
    assert role == "view"
    assert auth.authenticate(db, "john", "john-password-1", ADMIN, ADMIN_PASSWORD) == "view"
    # Used up: can't make a second account with it.
    assert auth.check_invite(db, code) is None
    with pytest.raises(auth.AuthError, match="isn't valid"):
        auth.accept_invite(db, code, "someone", "other-password-1", ADMIN)


def test_expired_or_made_up_invites_fail():
    db = FakeDatabase()
    code = auth.create_invite(db, "view")
    for row in db.tables["app_invites"].values():
        row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert auth.check_invite(db, code) is None
    assert auth.check_invite(db, "made-up") is None
    assert auth.check_invite(db, "") is None


def test_bad_username_keeps_the_invite_usable():
    db = FakeDatabase()
    code = auth.create_invite(db, "view")
    with pytest.raises(auth.AuthError):
        auth.accept_invite(db, code, "x", "john-password-1", ADMIN)  # too short
    assert auth.check_invite(db, code) is not None


def test_open_invites_and_cancel():
    db = FakeDatabase()
    auth.create_invite(db, "view", "John")
    used = auth.create_invite(db, "view")
    auth.accept_invite(db, used, "jane", "jane-password-1", ADMIN)
    open_ones = auth.list_open_invites(db)
    assert [i["note"] for i in open_ones] == ["John"]
    auth.cancel_invite(db, open_ones[0]["code_hash"])
    assert auth.list_open_invites(db) == []
