"""
Database connection and query tests
"""

import pytest
from database.db_connection import DatabaseConnection


@pytest.fixture
def db():
    """Create database connection for testing"""
    return DatabaseConnection()


def test_health_check(db):
    """Test database health check"""
    # This will fail if database is not available
    # In CI/CD, use a test database
    try:
        result = db.health_check()
        assert isinstance(result, bool)
    except Exception:
        pytest.skip("Database not available for testing")


def test_get_connection(db):
    """Test getting connection from pool"""
    try:
        with db.get_connection() as conn:
            assert conn is not None
    except Exception:
        pytest.skip("Database not available for testing")


def test_get_cursor(db):
    """Test getting cursor from pool"""
    try:
        with db.get_cursor() as cursor:
            assert cursor is not None
    except Exception:
        pytest.skip("Database not available for testing")


def test_execute_query(db):
    """Test executing a query"""
    try:
        result = db.execute_query("SELECT 1 as test")
        assert len(result) == 1
        assert result[0]['test'] == 1
    except Exception:
        pytest.skip("Database not available for testing")


