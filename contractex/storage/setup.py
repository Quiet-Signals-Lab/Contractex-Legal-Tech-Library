"""
Database setup and initialization script.

Orchestrates one-time initialization: database creation, extension installation,
schema execution, and initial data loading. Designed to be idempotent - safe to
run multiple times.

Usage:
    python -m dbase.setup
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

from contractex.storage.config import CUAD_TXT_DIR, LOG_FORMAT, LOG_LEVEL, get_db_config
from contractex.storage.connection import connect_to_postgres_server, test_connection
from contractex.storage.models import Document, ProcessingLog, ProcessingStage, ProcessingStatus
from contractex.storage.repository import DocumentRepository, ProcessingLogRepository

# Configure logging
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR / "schema.sql"


def create_database_if_not_exists() -> bool:
    """
    Create database if it doesn't exist.

    Returns:
        True if database was created, False if already exists
    """
    config = get_db_config()
    db_name = config["db_name"]

    try:
        # Connect to PostgreSQL server (not specific database)
        conn = connect_to_postgres_server(config)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone() is not None

        if not exists:
            # Create database
            cursor.execute(
                sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(db_name))
            )
            logger.info(f"Created database: {db_name}")
            created = True
        else:
            logger.info(f"Database already exists: {db_name}")
            created = False

        cursor.close()
        conn.close()
        return created

    except psycopg2.Error as e:
        logger.error(f"Failed to create database: {e}")
        raise


def setup_extensions() -> None:
    """
    Install required PostgreSQL extensions.

    Note: pgvector extension is commented out in schema as embeddings are deferred.
    Uncomment when ready to implement vector similarity search.
    """
    config = get_db_config()

    try:
        conn = psycopg2.connect(
            dbname=config["db_name"],
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # pgvector extension - deferred until embeddings needed
        # Uncomment when implementing vector similarity search
        # cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # logger.info("Installed pgvector extension")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Failed to setup extensions: {e}")
        raise


def setup_schema() -> None:
    """
    Execute schema.sql to create tables and indexes.
    Uses IF NOT EXISTS for idempotency.
    """
    config = get_db_config()

    if not SCHEMA_FILE.exists():
        logger.error(f"Schema file not found: {SCHEMA_FILE}")
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_FILE}")

    try:
        conn = psycopg2.connect(
            dbname=config["db_name"],
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Read and execute schema file
        with open(SCHEMA_FILE) as f:
            schema_sql = f.read()

        cursor.execute(schema_sql)
        logger.info("Schema created successfully")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Failed to setup schema: {e}")
        raise


def ingest_initial_data(limit: int | None = None) -> None:
    """
    Ingest initial documents from data directory.

    Args:
        limit: Optional limit on number of documents to ingest
    """
    # Check if CUAD data directory exists
    cuad_txt_path = Path(CUAD_TXT_DIR)
    if not cuad_txt_path.exists():
        logger.warning(f"CUAD text directory not found: {CUAD_TXT_DIR}")
        logger.info("Skipping initial data ingestion")
        return

    # Get all text files
    txt_files = list(cuad_txt_path.glob("*.txt"))
    if not txt_files:
        logger.warning("No .txt files found in CUAD directory")
        return

    if limit:
        txt_files = txt_files[:limit]

    logger.info(f"Found {len(txt_files)} text files to ingest")

    # Initialize repositories
    doc_repo = DocumentRepository()
    log_repo = ProcessingLogRepository()

    success_count = 0
    skip_count = 0
    error_count = 0

    for txt_file in txt_files:
        filename = txt_file.name

        try:
            # Check if already exists
            existing = doc_repo.get_by_filename(filename)
            if existing:
                logger.debug(f"Skipping existing document: {filename}")
                skip_count += 1
                continue

            # Read text content
            with open(txt_file, encoding="utf-8", errors="ignore") as f:
                text_content = f.read()

            # Create document object
            doc = Document(
                filename=filename,
                file_hash=None,  # No binary data for text files
                file_data=None,
                extracted_text=text_content,
                metadata={"source": "CUAD_v1", "file_type": "txt"},
            )

            # Insert document
            doc_id = doc_repo.insert(doc)

            # Log processing
            log = ProcessingLog(
                document_id=doc_id,
                processing_stage=ProcessingStage.UPLOADED,
                status=ProcessingStatus.COMPLETED,
            )
            log_repo.insert(log)

            success_count += 1

            if success_count % 10 == 0:
                logger.info(f"Progress: {success_count}/{len(txt_files)} documents ingested")

        except Exception as e:
            logger.error(f"Failed to ingest {filename}: {e}")
            error_count += 1
            continue

    logger.info(
        f"Ingestion complete: {success_count} inserted, {skip_count} skipped, {error_count} errors"
    )


def verify_setup() -> bool:
    """
    Verify database setup by testing connection and checking tables.

    Returns:
        True if setup verified successfully
    """
    try:
        # Test connection
        if not test_connection():
            logger.error("Connection test failed")
            return False

        config = get_db_config()
        conn = psycopg2.connect(
            dbname=config["db_name"],
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
        cursor = conn.cursor()

        # Check that core tables exist
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('documents', 'clauses', 'processing_log')
        """
        )
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = {"documents", "clauses", "processing_log"}
        if set(tables) == expected_tables:
            logger.info(f"All core tables exist: {tables}")

            # Get row counts
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result = cursor.fetchone()
                count = result[0] if result else 0
                logger.info(f"  {table}: {count} rows")

            cursor.close()
            conn.close()
            return True
        else:
            missing = expected_tables - set(tables)
            logger.error(f"Missing tables: {missing}")
            cursor.close()
            conn.close()
            return False

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False


def run_setup(ingest_data: bool = True, data_limit: int | None = None) -> None:
    """
    Run complete database setup process.

    Args:
        ingest_data: Whether to ingest initial data
        data_limit: Optional limit on documents to ingest
    """
    logger.info("=" * 70)
    logger.info("Starting database setup")
    logger.info("=" * 70)

    try:
        # Step 1: Create database
        logger.info("Step 1: Creating database...")
        create_database_if_not_exists()

        # Step 2: Setup extensions (deferred for now)
        logger.info("Step 2: Setting up extensions...")
        setup_extensions()

        # Step 3: Create schema
        logger.info("Step 3: Creating schema...")
        setup_schema()

        # Step 4: Ingest initial data
        if ingest_data:
            logger.info("Step 4: Ingesting initial data...")
            ingest_initial_data(limit=data_limit)
        else:
            logger.info("Step 4: Skipping initial data ingestion")

        # Step 5: Verify setup
        logger.info("Step 5: Verifying setup...")
        if verify_setup():
            logger.info("=" * 70)
            logger.info("Database setup completed successfully!")
            logger.info("=" * 70)
        else:
            logger.error("Setup verification failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Setup contract clause extraction database")
    parser.add_argument("--no-data", action="store_true", help="Skip initial data ingestion")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of documents to ingest (for testing)"
    )

    args = parser.parse_args()

    run_setup(ingest_data=not args.no_data, data_limit=args.limit)
