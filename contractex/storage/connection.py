"""
PostgreSQL connection management with context managers.

Provides connection lifecycle management and will support connection pooling
when scaling to API serving.
"""

import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from contractex.storage.config import get_db_config

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Manages PostgreSQL database connections with context manager support.

    Usage:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents")
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize connection manager.

        Args:
            config: Optional database configuration dict.
                   If None, loads from get_db_config()
        """
        self.config = config or get_db_config()
        self.conn: Optional[psycopg2.extensions.connection] = None

    def __enter__(self):
        """Context manager entry - establish connection."""
        try:
            self.conn = psycopg2.connect(
                dbname=self.config["db_name"],
                user=self.config["user"],
                password=self.config["password"],
                host=self.config["host"],
                port=self.config["port"],
            )
            logger.debug(f"Connected to database: {self.config['db_name']}")
            return self.conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        if self.conn:
            if exc_type:
                # Rollback on exception
                self.conn.rollback()
                logger.warning("Transaction rolled back due to exception")
            else:
                # Commit on success
                self.conn.commit()
            self.conn.close()
            logger.debug("Database connection closed")
        # Don't suppress exceptions
        return False


@contextmanager
def get_connection(config: Optional[dict] = None):
    """
    Context manager for database connections.

    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents")

    Args:
        config: Optional database configuration dict
    """
    config = config or get_db_config()
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=config["db_name"],
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
        logger.debug(f"Connected to database: {config['db_name']}")
        yield conn
        conn.commit()
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.debug("Database connection closed")


@contextmanager
def get_cursor(dict_cursor: bool = False, config: Optional[dict] = None):
    """
    Context manager for database cursor with automatic connection management.

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM documents")
            results = cur.fetchall()

    Args:
        dict_cursor: If True, returns RealDictCursor for dict-like row access
        config: Optional database configuration dict
    """
    with get_connection(config) as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()


def test_connection(config: Optional[dict] = None) -> bool:
    """
    Test database connectivity.

    Args:
        config: Optional database configuration dict

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with get_connection(config) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            logger.info("Database connection test successful")
            return result is not None and result[0] == 1
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


def connect_to_postgres_server(config: Optional[dict] = None):
    """
    Connect to PostgreSQL server (not specific database).
    Used for database creation tasks.

    Args:
        config: Optional configuration dict with server connection info

    Returns:
        psycopg2 connection object to 'postgres' database
    """
    config = config or get_db_config()
    try:
        conn = psycopg2.connect(
            dbname="postgres",  # Connect to default postgres database
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
        conn.autocommit = True  # Required for CREATE DATABASE
        logger.info("Connected to PostgreSQL server")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to PostgreSQL server: {e}")
        raise


@contextmanager
def get_vector_cursor(dict_cursor: bool = False, config: Optional[dict] = None):
    """
    Context manager for database cursor with pgvector types registered.

    Use this instead of get_cursor() for any query that reads or writes
    VECTOR columns. Registers the pgvector psycopg2 adapter so plain
    Python list[float] values are accepted as query parameters.

    Usage:
        with get_vector_cursor() as cur:
            cur.execute("UPDATE clauses SET embedding = %s WHERE id = %s",
                        (embedding, clause_id))

    Raises:
        ContractExError: If pgvector Python package is not installed
    """
    try:
        from pgvector.psycopg2 import register_vector
    except ImportError as e:
        from contractex.exceptions import ContractExError

        raise ContractExError(
            "pgvector not installed. Install with: pip install pgvector"
        ) from e

    with get_connection(config) as conn:
        register_vector(conn)
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()


# TODO: Implement connection pooling when scaling to API serving
# from psycopg2 import pool
# connection_pool = psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=20, ...)
