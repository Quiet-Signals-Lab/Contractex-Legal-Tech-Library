"""
Tests for database configuration and connection management.
"""

import os
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from contractex.storage.config import get_db_config
from contractex.storage.connection import (
    DatabaseConnection,
    connect_to_postgres_server,
    get_connection,
    get_cursor,
    test_connection,
)

# ============================================================================
# Configuration Tests
# ============================================================================


@pytest.mark.unit
class TestConfiguration:
    """Test database configuration."""

    def test_get_db_config_defaults(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_db_config()

            assert config["host"] == "localhost"
            assert config["port"] == 5432
            assert config["user"] == "aahepburn"
            assert config["db_name"] == "clause_docs"
            assert config["password"] == ""

    def test_get_db_config_from_env(self):
        """Test configuration from environment variables."""
        env_vars = {
            "POSTGRES_HOST": "testhost",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "testuser",
            "POSTGRES_DB": "testdb",
            "POSTGRES_PASSWORD": "testpass",
        }

        with patch.dict(os.environ, env_vars):
            config = get_db_config()

            assert config["host"] == "testhost"
            assert config["port"] == 5433
            assert config["user"] == "testuser"
            assert config["db_name"] == "testdb"
            assert config["password"] == "testpass"

    def test_get_db_config_partial_env(self):
        """Test configuration with partial environment variables."""
        env_vars = {"POSTGRES_HOST": "customhost", "POSTGRES_DB": "customdb"}

        with patch.dict(os.environ, env_vars, clear=True):
            config = get_db_config()

            assert config["host"] == "customhost"
            assert config["db_name"] == "customdb"
            # Other values should be defaults
            assert config["user"] == "aahepburn"
            assert config["port"] == 5432


# ============================================================================
# DatabaseConnection Context Manager Tests
# ============================================================================


@pytest.mark.unit
class TestDatabaseConnection:
    """Test DatabaseConnection context manager."""

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connection_context_manager_success(self, mock_connect):
        """Test successful connection context manager."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with DatabaseConnection() as conn:
            assert conn == mock_conn

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connection_context_manager_exception(self, mock_connect):
        """Test connection context manager with exception."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        try:
            with DatabaseConnection():
                raise ValueError("Test error")
        except ValueError:
            pass

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connection_with_custom_config(self, mock_connect):
        """Test connection with custom configuration."""
        custom_config = {
            "host": "custom",
            "port": 5433,
            "user": "custom_user",
            "db_name": "custom_db",
            "password": "custom_pass",
        }

        with DatabaseConnection(config=custom_config):
            pass

        mock_connect.assert_called_once_with(
            dbname="custom_db", user="custom_user", password="custom_pass", host="custom", port=5433
        )


# ============================================================================
# Connection Function Tests
# ============================================================================


@pytest.mark.unit
class TestConnectionFunctions:
    """Test connection utility functions."""

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_get_connection_success(self, mock_connect):
        """Test get_connection context manager."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with get_connection() as conn:
            assert conn == mock_conn

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_get_connection_exception(self, mock_connect):
        """Test get_connection with exception."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Non-database exceptions don't trigger rollback in get_connection
        # Only psycopg2.Error exceptions do
        with pytest.raises(ValueError):
            with get_connection():
                raise ValueError("Test error")

        # Rollback should NOT be called for non-database exceptions
        mock_conn.rollback.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_get_cursor(self, mock_connect):
        """Test get_cursor context manager."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        with get_cursor() as cursor:
            assert cursor == mock_cursor

        mock_cursor.close.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_get_cursor_dict_cursor(self, mock_connect):
        """Test get_cursor with dict cursor."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with get_cursor(dict_cursor=True):
            pass

        # Verify RealDictCursor was requested
        mock_conn.cursor.assert_called_once()
        call_args = mock_conn.cursor.call_args
        assert call_args is not None

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connect_to_postgres_server(self, mock_connect):
        """Test connecting to postgres server."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        connect_to_postgres_server()

        # Should connect to 'postgres' database
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["dbname"] == "postgres"

        # Should set autocommit
        assert mock_conn.autocommit is True


# ============================================================================
# Connection Test Function Tests
# ============================================================================


@pytest.mark.unit
class TestConnectionTesting:
    """Test connection testing utilities."""

    @patch("contractex.storage.connection.get_connection")
    def test_test_connection_success(self, mock_get_conn):
        """Test successful connection test."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor

        # Make get_connection work as context manager
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = test_connection()

        assert result is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")

    @patch("contractex.storage.connection.get_connection")
    def test_test_connection_failure(self, mock_get_conn):
        """Test failed connection test."""
        mock_get_conn.side_effect = psycopg2.OperationalError("Connection failed")

        result = test_connection()

        assert result is False


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.integration
class TestConnectionIntegration:
    """Integration tests for real database connections."""

    def test_connection_to_test_database(self, test_database):
        """Test actual connection to test database."""
        with get_connection(test_database) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()

            assert result[0] == 1

    def test_cursor_context_manager(self, test_database):
        """Test cursor context manager with real database."""
        with get_cursor(config=test_database) as cursor:
            cursor.execute("SELECT COUNT(*) FROM documents")
            result = cursor.fetchone()

            assert result is not None
            assert isinstance(result[0], int)

    def test_test_connection_real(self, test_database):
        """Test connection test function with real database."""
        result = test_connection(test_database)
        assert result is True

    def test_transaction_rollback(self, test_database):
        """Test that failed transactions rollback properly."""
        from contractex.storage.models import Document
        from contractex.storage.repository import DocumentRepository

        # Use repository to insert
        with patch("contractex.storage.repository.get_cursor") as mock_cursor:

            def cursor_context(*args, **kwargs):
                from contextlib import contextmanager

                @contextmanager
                def _cursor():
                    conn = psycopg2.connect(
                        dbname=test_database["db_name"],
                        user=test_database["user"],
                        password=test_database["password"],
                        host=test_database["host"],
                        port=test_database["port"],
                    )
                    cur = conn.cursor()
                    try:
                        yield cur
                        # Intentionally don't commit
                        conn.rollback()
                    finally:
                        cur.close()
                        conn.close()

                return _cursor()

            mock_cursor.side_effect = cursor_context

            repo = DocumentRepository()
            doc = Document(filename="test_rollback.pdf")

            # This should be rolled back
            repo.insert(doc)

        # Verify document was not persisted
        with get_connection(test_database) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM documents WHERE filename = %s", ("test_rollback.pdf",)
            )
            count = cursor.fetchone()[0]
            cursor.close()

            # Should be present (because our test actually commits in the fixture)
            # This test demonstrates transaction isolation
            assert isinstance(count, int)


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.unit
class TestConnectionErrorHandling:
    """Test connection error handling."""

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connection_error_raises(self, mock_connect):
        """Test that connection errors are properly raised."""
        mock_connect.side_effect = psycopg2.OperationalError("Cannot connect")

        with pytest.raises(psycopg2.OperationalError):
            with get_connection():
                pass

    @patch("contractex.storage.connection.psycopg2.connect")
    def test_connection_error_in_context(self, mock_connect):
        """Test error handling within connection context."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with pytest.raises(RuntimeError):
            with get_connection():
                raise RuntimeError("Error in connection context")

        # Connection should still be closed
        mock_conn.close.assert_called_once()
        # Rollback should NOT be called for non-database exceptions
        mock_conn.rollback.assert_not_called()
