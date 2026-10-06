import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

import bot


@pytest.fixture
def migration_db(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.sqlite3"
    monkeypatch.setattr(bot, "DB_PATH", str(db_path))
    monkeypatch.setattr(bot, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(bot, "db_pool", None)

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT,
            xp INTEGER,
            level INTEGER,
            language TEXT,
            is_banned BOOLEAN,
            ban_reason TEXT,
            daily_requests INTEGER
        );
        CREATE TABLE requests (
            request_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            text TEXT,
            response TEXT,
            created_at TEXT
        );
        CREATE TABLE feedback (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            rating INTEGER
        );
        CREATE TABLE cache (
            cache_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            cache_key TEXT,
            cached_response TEXT,
            ttl_seconds INTEGER,
            created_at TEXT
        );
        CREATE TABLE user_progress (
            user_id INTEGER,
            course_id INTEGER,
            lesson_id INTEGER
        );
        """
    )
    connection.execute(
        """
        INSERT INTO users (
            user_id, username, first_name, created_at, xp, level, language,
            is_banned, ban_reason, daily_requests
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (42, "satoshi", "Satoshi", "2024-01-02 03:04:05", 875, 8, "uk", 1, "review", 17),
    )
    connection.commit()
    connection.close()
    return db_path


def test_migrate_database_preserves_existing_user_fields(migration_db):
    bot.migrate_database()

    connection = sqlite3.connect(migration_db)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        row = connection.execute(
            """
            SELECT user_id, username, first_name, created_at, xp, level, language,
                   is_banned, ban_reason, daily_requests
            FROM users WHERE user_id = 42
            """
        ).fetchone()
    finally:
        connection.close()

    assert {
        "user_id",
        "username",
        "first_name",
        "created_at",
        "total_requests",
        "last_request_at",
        "is_banned",
        "ban_reason",
        "daily_requests",
        "daily_reset_at",
        "knowledge_level",
        "xp",
        "level",
        "badges",
        "requests_today",
        "last_request_date",
        "language",
    } <= columns
    assert row == (
        42,
        "satoshi",
        "Satoshi",
        "2024-01-02 03:04:05",
        875,
        8,
        "uk",
        1,
        "review",
        17,
    )


def test_migrate_database_transitions_legacy_conversation_history(migration_db):
    connection = sqlite3.connect(migration_db)
    connection.execute(
        """
        CREATE TABLE conversation_history (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            message_type TEXT,
            content TEXT,
            intent TEXT,
            created_at TEXT
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO conversation_history
            (id, user_id, message_type, content, intent, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 42, "bot", "Bot response", "answer", "2024-02-03 04:05:06"),
            (2, 42, "user", "User prompt", "question", "2024-02-03 04:06:07"),
        ],
    )
    connection.commit()
    connection.close()

    bot.migrate_database()

    connection = sqlite3.connect(migration_db)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(conversation_history)"
            ).fetchall()
        }
        rows = connection.execute(
            """
            SELECT id, user_id, role, content, intent, message_length,
                   timestamp, tokens_estimate
            FROM conversation_history ORDER BY id
            """
        ).fetchall()
        old_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_history_old'"
        ).fetchone()
    finally:
        connection.close()

    assert columns == {
        "id",
        "user_id",
        "role",
        "content",
        "intent",
        "timestamp",
        "message_length",
        "tokens_estimate",
    }
    assert [row[:6] + row[7:] for row in rows] == [
        (1, 42, "assistant", "Bot response", "answer", 12, None),
        (2, 42, "user", "User prompt", "question", 11, None),
    ]
    assert all(row[6] is not None for row in rows)
    assert old_table is None


def test_startup_backup_precedes_schema_rebuild(migration_db, monkeypatch):
    monkeypatch.setattr(bot, "ensure_conversation_history_columns", lambda: None)
    monkeypatch.setattr(bot, "init_database", bot.migrate_database)

    bot.initialize_database_with_backup()

    backups = list((migration_db.parent / "backups").glob("rvx_bot_backup_*.db"))
    assert len(backups) == 1

    backup_connection = sqlite3.connect(backups[0])
    try:
        columns = {
            row[1]
            for row in backup_connection.execute("PRAGMA table_info(users)").fetchall()
        }
        user = backup_connection.execute(
            "SELECT user_id, username, first_name, xp FROM users WHERE user_id = 42"
        ).fetchone()
    finally:
        backup_connection.close()

    assert columns == {
        "user_id", "username", "first_name", "created_at", "xp", "level",
        "language", "is_banned", "ban_reason", "daily_requests",
    }
    assert user == (42, "satoshi", "Satoshi", 875)


def test_startup_stops_if_pre_migration_backup_fails(
    migration_db, monkeypatch
):
    startup_steps = []

    def fail_backup(_source_connection):
        raise OSError("backup destination is unavailable")

    monkeypatch.setattr(bot, "_create_database_backup_file", fail_backup)
    monkeypatch.setattr(
        bot, "ensure_conversation_history_columns", lambda: startup_steps.append("ensure")
    )
    monkeypatch.setattr(bot, "init_database", lambda: startup_steps.append("init"))

    with pytest.raises(OSError, match="backup destination is unavailable"):
        bot.initialize_database_with_backup()

    assert startup_steps == []

    connection = sqlite3.connect(migration_db)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        user = connection.execute(
            "SELECT user_id, username, first_name, xp FROM users WHERE user_id = 42"
        ).fetchone()
    finally:
        connection.close()

    assert columns == {
        "user_id", "username", "first_name", "created_at", "xp", "level",
        "language", "is_banned", "ban_reason", "daily_requests",
    }
    assert user == (42, "satoshi", "Satoshi", 875)


def test_sqlite_backup_includes_committed_wal_data(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "BACKUP_DIR", str(tmp_path / "backups"))
    source_path = tmp_path / "wal_source.sqlite3"
    source_connection = sqlite3.connect(source_path)
    try:
        source_connection.execute("PRAGMA journal_mode=WAL")
        source_connection.execute("PRAGMA wal_autocheckpoint=0")
        source_connection.execute("CREATE TABLE wal_records (value TEXT NOT NULL)")
        source_connection.execute("INSERT INTO wal_records VALUES ('committed-in-wal')")
        source_connection.commit()

        wal_path = Path(f"{source_path}-wal")
        assert wal_path.exists()
        assert wal_path.stat().st_size > 0

        backup_path = bot._create_database_backup_file(source_connection)
    finally:
        source_connection.close()

    backup_connection = sqlite3.connect(backup_path)
    try:
        value = backup_connection.execute("SELECT value FROM wal_records").fetchone()
    finally:
        backup_connection.close()

    assert value == ("committed-in-wal",)


def test_migrate_database_rolls_back_after_user_rows_are_copied(
    migration_db, monkeypatch
):
    original_get_db = bot.get_db
    operations = []

    def fail_when_dropping_old_users(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_INSERT and table == "users":
            operations.append("copy-user")
        if action == sqlite3.SQLITE_DROP_TABLE and table == "users_old":
            operations.append("drop-old-table")
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    @contextmanager
    def get_db_with_late_failure():
        with original_get_db() as connection:
            connection.set_authorizer(fail_when_dropping_old_users)
            yield connection

    monkeypatch.setattr(bot, "get_db", get_db_with_late_failure)

    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        bot.migrate_database()

    assert operations.index("copy-user") < operations.index("drop-old-table")

    connection = sqlite3.connect(migration_db)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        user = connection.execute("SELECT * FROM users WHERE user_id = 42").fetchone()
        old_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users_old'"
        ).fetchone()
    finally:
        connection.close()

    assert columns == {
        "user_id", "username", "first_name", "created_at", "xp", "level",
        "language", "is_banned", "ban_reason", "daily_requests",
    }
    assert user == (
        42,
        "satoshi",
        "Satoshi",
        "2024-01-02 03:04:05",
        875,
        8,
        "uk",
        1,
        "review",
        17,
    )
    assert old_table is None
