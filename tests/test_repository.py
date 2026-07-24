from __future__ import annotations

import pytest

from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import close_trip, create_trip, get_open_trip, list_trips
from fairsharebot.db.users_repo import get_user, resolve_username, upsert_chat_user, upsert_user
from fairsharebot.errors import NoOpenTripError, TripAlreadyOpenError


def test_upsert_user_and_get(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="Alice", display_name="Alice A")

    with get_connection(db_path) as conn:
        user = get_user(conn, 1)

    assert user is not None
    assert user.username == "alice"
    assert user.display_name == "Alice A"


def test_resolve_username_scoped_to_chat(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="bob", display_name="Bob")
        upsert_chat_user(conn, chat_id=100, user_id=1)

    with get_connection(db_path) as conn:
        found = resolve_username(conn, chat_id=100, username="@Bob")
        not_found_wrong_chat = resolve_username(conn, chat_id=200, username="bob")
        not_found_unknown = resolve_username(conn, chat_id=100, username="carol")

    assert found is not None and found.id == 1
    assert not_found_wrong_chat is None
    assert not_found_unknown is None


def test_create_trip_and_get_open_trip(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        trip = create_trip(conn, chat_id=100, name="Ski trip", created_by=1)

    with get_connection(db_path) as conn:
        open_trip = get_open_trip(conn, 100)

    assert open_trip is not None
    assert open_trip.id == trip.id
    assert open_trip.status == "open"


def test_create_trip_rejects_second_open_trip(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        create_trip(conn, chat_id=100, name="Trip A", created_by=1)

    with get_connection(db_path) as conn:
        with pytest.raises(TripAlreadyOpenError):
            create_trip(conn, chat_id=100, name="Trip B", created_by=1)


def test_create_trip_allows_reopen_in_different_chat(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        create_trip(conn, chat_id=100, name="Trip A", created_by=1)
        other_chat_trip = create_trip(conn, chat_id=200, name="Trip B", created_by=1)

    assert other_chat_trip.chat_id == 200


def test_close_trip(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        create_trip(conn, chat_id=100, name="Trip A", created_by=1)

    with get_connection(db_path) as conn:
        closed = close_trip(conn, 100)

    assert closed.status == "closed"
    assert closed.closed_at is not None

    with get_connection(db_path) as conn:
        assert get_open_trip(conn, 100) is None


def test_close_trip_without_open_trip_raises(db_path):
    with get_connection(db_path) as conn:
        with pytest.raises(NoOpenTripError):
            close_trip(conn, 999)


def test_list_trips_orders_newest_first(db_path):
    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        create_trip(conn, chat_id=100, name="Trip A", created_by=1)
        close_trip(conn, 100)
        create_trip(conn, chat_id=100, name="Trip B", created_by=1)

    with get_connection(db_path) as conn:
        trips = list_trips(conn, 100)

    assert [t.name for t in trips] == ["Trip B", "Trip A"]
