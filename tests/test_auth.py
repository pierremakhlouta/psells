"""Tests for auth.py and set_password.py, run against a real PostgreSQL.

Every time is a fixed moment passed in, so a session's two limits are tested to
the second at both edges without waiting for either.

Hashing is real Argon2 at its real cost, a fraction of a second each, because
a cheaper hasher here would be a different hasher from the one that runs.
"""

import datetime

import pytest
from argon2 import PasswordHasher

import auth
import set_password


T = datetime.datetime(2026, 9, 27, 9, 0, tzinfo=datetime.timezone.utc)
SECOND = datetime.timedelta(seconds=1)
HOUR = datetime.timedelta(hours=1)

USERNAME = "owner"
PASSWORD = "an invented passphrase"


@pytest.fixture
def user_id(db):
    return auth.set_password(db, USERNAME, PASSWORD)


def stored_hash(db):
    return db.execute("SELECT password_hash FROM users").fetchone()[
        "password_hash"]


def session_count(db):
    return db.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]


# Passwords ---------------------------------------------------------------------

def test_a_hash_is_argon2id_and_checks_only_its_own_password():
    stored = auth.hash_password(PASSWORD)

    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert auth.verify_password(stored, PASSWORD)
    assert not auth.verify_password(stored, PASSWORD + "!")


def test_the_same_password_hashes_differently_each_time():
    # A fresh salt every time, so two accounts with one password, or one
    # password set twice, cannot be spotted in the table.
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_a_damaged_hash_is_a_refusal_not_a_crash():
    assert not auth.verify_password("not a hash", PASSWORD)


@pytest.mark.parametrize("password, refused", [
    ("a" * 14, True),
    ("a" * 15, False),
    # Length is the only rule: no digits or symbols required.
    ("abcdefghijklmno", False),
    ("", True),
])
def test_a_password_needs_the_minimum_length_and_nothing_else(
        password, refused):
    assert (auth.password_problem(password) is not None) == refused


@pytest.mark.parametrize("username", ["", " owner", "owner ", "   "])
def test_a_blank_or_padded_username_is_refused(username):
    assert auth.username_problem(username) is not None


# Logging in --------------------------------------------------------------------

def test_the_right_password_logs_in(db, user_id):
    assert auth.check_login(db, USERNAME, PASSWORD) == user_id


@pytest.mark.parametrize("username, password", [
    (USERNAME, "the wrong passphrase"),
    (USERNAME, ""),
    (USERNAME.upper(), PASSWORD),
    ("someone else", PASSWORD),
])
def test_anything_else_does_not(db, user_id, username, password):
    assert auth.check_login(db, username, password) is None


def test_an_unknown_username_costs_the_same_argon2_check(db, monkeypatch):
    checked = []
    real_verify = auth.verify_password

    def recording_verify(stored, password):
        checked.append(stored)
        return real_verify(stored, password)

    monkeypatch.setattr(auth, "verify_password", recording_verify)

    assert auth.check_login(db, "nobody", PASSWORD) is None
    assert len(checked) == 1
    assert checked[0].startswith("$argon2id$")


def test_a_hash_made_with_weaker_settings_is_upgraded_at_login(db, user_id):
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    db.execute("UPDATE users SET password_hash = %s",
               (weak.hash(PASSWORD),))

    assert auth.check_login(db, USERNAME, PASSWORD) == user_id

    upgraded = stored_hash(db)
    assert not PasswordHasher().check_needs_rehash(upgraded)
    assert auth.verify_password(upgraded, PASSWORD)


def test_a_current_hash_is_left_as_it_is(db, user_id):
    before = stored_hash(db)

    auth.check_login(db, USERNAME, PASSWORD)

    assert stored_hash(db) == before


# Setting the password ------------------------------------------------------------

def test_setting_a_password_stores_a_hash_not_the_password(db, user_id):
    stored = stored_hash(db)

    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_changing_the_password_keeps_the_account(db, user_id):
    assert auth.set_password(db, USERNAME, "another invented one") == user_id

    assert auth.check_login(db, USERNAME, PASSWORD) is None
    assert auth.check_login(db, USERNAME, "another invented one") == user_id


def test_changing_the_password_ends_every_session(db, user_id):
    auth.start_session(db, user_id, T)
    auth.start_session(db, user_id, T)

    auth.set_password(db, USERNAME, "another invented one")

    assert session_count(db) == 0


def test_a_second_account_is_refused(db, user_id):
    with pytest.raises(auth.AccountError, match="already has the account"):
        auth.set_password(db, "someone else", "a different passphrase")

    usernames = db.execute("SELECT username FROM users").fetchall()
    assert usernames == [{"username": USERNAME}]


@pytest.mark.parametrize("username, password", [
    (USERNAME, "too short"),
    ("", PASSWORD),
    (" owner", PASSWORD),
])
def test_a_refused_account_writes_nothing(db, username, password):
    with pytest.raises(auth.AccountError):
        auth.set_password(db, username, password)

    assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0


# Sessions ----------------------------------------------------------------------

def test_a_session_is_stored_under_a_digest_never_the_cookie_value(
        db, user_id):
    cookie_value, form_token = auth.start_session(db, user_id, T)

    row = db.execute("SELECT * FROM sessions").fetchone()
    assert bytes(row["token_digest"]) == auth.digest(cookie_value)
    assert cookie_value.encode() not in bytes(row["token_digest"])
    assert row["form_token"] == form_token
    assert row["created_at"] == row["last_seen_at"] == T


def test_every_session_gets_its_own_values(db, user_id):
    first = auth.start_session(db, user_id, T)
    second = auth.start_session(db, user_id, T)

    assert len(set(first + second)) == 4
    assert all(len(value) >= 43 for value in first + second)


def test_a_session_is_found_by_its_cookie_value(db, user_id):
    cookie_value, form_token = auth.start_session(db, user_id, T)

    session = auth.find_session(db, cookie_value, T + SECOND)

    assert session == {"user_id": user_id, "form_token": form_token}


@pytest.mark.parametrize("cookie_value", ["", None, "made up"])
def test_a_missing_or_unknown_cookie_finds_nothing(db, user_id, cookie_value):
    auth.start_session(db, user_id, T)

    assert auth.find_session(db, cookie_value, T) is None


def test_a_session_ends_after_two_idle_hours(db, user_id):
    cookie_value, _ = auth.start_session(db, user_id, T)

    assert auth.find_session(db, cookie_value, T + 2 * HOUR - SECOND)

    # Now idle from T + 2h - 1s, so exactly two hours after that it is gone.
    later = T + 2 * HOUR - SECOND + 2 * HOUR
    assert auth.find_session(db, cookie_value, later - SECOND)
    assert auth.find_session(db, cookie_value, later - SECOND + 2 * HOUR) \
        is None


def test_two_idle_hours_exactly_is_too_long(db, user_id):
    cookie_value, _ = auth.start_session(db, user_id, T)

    assert auth.find_session(db, cookie_value, T + 2 * HOUR) is None


def test_using_a_session_keeps_it_alive_but_not_past_twelve_hours(
        db, user_id):
    cookie_value, _ = auth.start_session(db, user_id, T)

    for hour in range(1, 12):
        assert auth.find_session(db, cookie_value, T + hour * HOUR), hour

    assert auth.find_session(db, cookie_value, T + 12 * HOUR - SECOND)
    assert auth.find_session(db, cookie_value, T + 12 * HOUR) is None


def test_last_use_never_moves_backwards(db, user_id):
    cookie_value, _ = auth.start_session(db, user_id, T)
    auth.find_session(db, cookie_value, T + HOUR)

    # A clock that steps back, then the idle limit from the later time.
    auth.find_session(db, cookie_value, T + HOUR - 30 * 60 * SECOND)

    row = db.execute("SELECT last_seen_at FROM sessions").fetchone()
    assert row["last_seen_at"] == T + HOUR


def test_logging_out_ends_that_session_only(db, user_id):
    mine, _ = auth.start_session(db, user_id, T)
    other, _ = auth.start_session(db, user_id, T)

    auth.end_session(db, mine)

    assert auth.find_session(db, mine, T) is None
    assert auth.find_session(db, other, T)


def test_logging_out_without_a_cookie_does_nothing(db, user_id):
    auth.start_session(db, user_id, T)

    auth.end_session(db, None)
    auth.end_session(db, "")

    assert session_count(db) == 1


def test_a_login_clears_out_expired_sessions(db, user_id):
    auth.start_session(db, user_id, T)
    auth.start_session(db, user_id, T + HOUR)

    # At T + 2h the first has been idle for two hours and goes; the second has
    # been idle for one and stays, beside the new one.
    auth.start_session(db, user_id, T + 2 * HOUR)

    assert session_count(db) == 2


# Form tokens --------------------------------------------------------------------

def test_a_form_token_must_match_its_session(db, user_id):
    cookie_value, form_token = auth.start_session(db, user_id, T)
    session = auth.find_session(db, cookie_value, T)

    assert auth.form_token_matches(session, form_token)
    assert not auth.form_token_matches(session, form_token[:-1])
    assert not auth.form_token_matches(session, "")
    assert not auth.form_token_matches(session, None)
    assert not auth.form_token_matches(None, form_token)


def test_another_sessions_form_token_does_not_match(db, user_id):
    mine, _ = auth.start_session(db, user_id, T)
    _, other_token = auth.start_session(db, user_id, T)

    assert not auth.form_token_matches(auth.find_session(db, mine, T),
                                       other_token)


# set_password.py ---------------------------------------------------------------

def answers(*values):
    """A stand-in for input or getpass that gives these answers in order."""
    queue = list(values)
    return lambda prompt: queue.pop(0)


def test_the_script_creates_the_account(db, capsys):
    status = set_password.run(db, ask=answers(USERNAME),
                              ask_hidden=answers(PASSWORD, PASSWORD))

    assert status == 0
    assert auth.check_login(db, USERNAME, PASSWORD) is not None
    assert "logged out" in capsys.readouterr().out


@pytest.mark.parametrize("username, passwords, message", [
    (USERNAME, (PASSWORD, PASSWORD + "x"), "were different"),
    (USERNAME, ("too short",), "at least 15"),
    ("", (), "must not be blank"),
])
def test_the_script_refuses_and_changes_nothing(
        db, capsys, username, passwords, message):
    status = set_password.run(db, ask=answers(username),
                              ask_hidden=answers(*passwords))

    assert status == 1
    assert message in capsys.readouterr().out
    assert db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0


def test_the_script_says_why_a_second_account_is_refused(db, user_id, capsys):
    status = set_password.run(
        db, ask=answers("someone else"),
        ask_hidden=answers("a different passphrase", "a different passphrase"))

    assert status == 1
    assert "already has the account 'owner'" in capsys.readouterr().out
    assert auth.check_login(db, USERNAME, PASSWORD) == user_id
