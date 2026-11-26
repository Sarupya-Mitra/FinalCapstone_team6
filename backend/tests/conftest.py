"""Shared fixtures for the backend unit tests.

These are unit tests: no PostgreSQL server or AI provider is needed.
The database is replaced with FakeConnection/FakeCursor, which return
queued rows and record every SQL statement that was executed.
"""
import os

# app.core.config.Settings() runs at import time and requires these.
# Set them before any app module is imported so tests never depend on
# a developer's real .env values (and never hit a real database).
os.environ["DB_HOST"] = "test-db-host"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "test_db"
os.environ["DB_USER"] = "test_user"
os.environ["DB_PASSWORD"] = "test_password"
os.environ["JWT_SECRET_KEY"] = "unit-test-secret-key-that-is-long-enough-32b"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

import pymupdf
import pytest


class FakeCursor:
    """Minimal stand-in for a psycopg2 cursor."""

    def __init__(self, conn):
        self.conn = conn
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.conn.executed.append((" ".join(query.split()), params))
        if self.conn.errors:
            error = self.conn.errors.pop(0)
            if error is not None:
                raise error
        if self.conn.descriptions:
            self.description = [(name,) for name in self.conn.descriptions.pop(0)]

    def fetchone(self):
        return self.conn.results.pop(0) if self.conn.results else None

    def fetchall(self):
        return self.conn.results.pop(0) if self.conn.results else []


class FakeConnection:
    """Stand-in for a psycopg2 connection.

    results:      values returned, in order, by fetchone()/fetchall()
    descriptions: column-name lists set as cursor.description, in order
    errors:       exceptions raised by execute(), in order (None = no error)
    """

    def __init__(self, results=None, descriptions=None, errors=None):
        self.results = list(results or [])
        self.descriptions = list(descriptions or [])
        self.errors = list(errors or [])
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_db(monkeypatch):
    """Patch get_connection_db in a router module to return a FakeConnection.

    Usage:
        conn = fake_db("app.routers.vendors", results=[...])
    """

    def install(module_path, **kwargs):
        conn = FakeConnection(**kwargs)
        monkeypatch.setattr(f"{module_path}.get_connection_db", lambda: conn)
        return conn

    return install


def make_pdf(pages=1, text="Invoice INV-001\nTotal: 100.00"):
    """Build a small, valid PDF in memory."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_bytes():
    return make_pdf()
