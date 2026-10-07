"""PostgreSQL boundary for the same single-workspace transaction contract as SQLite."""
from contextlib import contextmanager


class MappingRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, cursor):
        self.cursor = cursor
        self.rowcount = cursor.rowcount

    def _row(self, row):
        if row is None:
            return None
        return MappingRow(zip((column.name for column in self.cursor.description), row))

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=None):
        # All SQL is owned by this application; values remain bound parameters.
        return Result(self.connection.execute(query.replace("?", "%s"), parameters))


@contextmanager
def postgres_transaction(url):
    import psycopg

    with psycopg.connect(url, connect_timeout=15, prepare_threshold=None) as connection:
        connection.execute("SET LOCAL statement_timeout = '15s'")
        # Match BEGIN IMMEDIATE's serialization of this single workspace. No external
        # network/model call holds this lock. This also protects cross-process dedup,
        # budgets, leases and version-bound reviews without database-specific forks.
        connection.execute("SELECT pg_advisory_xact_lock(734809172)")
        yield PostgresConnection(connection)


def postgres_schema(schema):
    return schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY").replace(
        "REAL", "DOUBLE PRECISION")
