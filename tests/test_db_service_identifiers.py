import pytest

from db_service import BaseRepository, DatabaseConnectionPool


@pytest.fixture
def repository():
    pool = DatabaseConnectionPool(":memory:")
    pool.get_connection().execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
    )
    yield BaseRepository("users", pool)
    pool.close_all()


def test_repository_binds_values_and_limits(repository):
    created = repository.create(name="x' OR 1=1 --")

    assert repository.find(name="x' OR 1=1 --") == [created]
    assert repository.find(name="another value") == []
    assert repository.get_all(limit=0) == []


def test_repository_rejects_untrusted_sql_identifiers(repository):
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        BaseRepository("users; DROP TABLE users", repository.pool)

    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        repository.find(**{"name = 'x' OR 1=1 --": "x"})


def test_repository_rejects_non_integer_limit(repository):
    with pytest.raises(ValueError, match="non-negative integer"):
        repository.get_all(limit="0; DROP TABLE users")

    assert repository.count() == 0
