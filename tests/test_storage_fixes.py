"""Storage layer: duplicates, transactions, logging, lookups and the v1 → v2 migration."""

from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

import contractex.storage
from contractex.exceptions import ContractExError
from contractex.storage import (
    Clause,
    ClauseRepository,
    Document,
    DocumentRepository,
    get_connection,
)

STORAGE_DIR = Path(contractex.storage.__file__).parent
SECRET = "Jane Roe, SSN 123-45-6789"


def _count(conn, table: str = "documents") -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


# ============================================================================
# No database needed
# ============================================================================


def test_import_without_psycopg2_names_the_extra(monkeypatch):
    for name in [m for m in sys.modules if m.startswith("contractex.storage")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "psycopg2", None)  # makes "import psycopg2" fail
    with pytest.raises(ImportError, match=r"pip install 'contractex\[storage\]'"):
        importlib.import_module("contractex.storage")


def test_setup_module_does_not_configure_logging_on_import(monkeypatch):
    monkeypatch.delitem(sys.modules, "contractex.storage.setup", raising=False)
    with patch("logging.basicConfig") as basic_config:
        setup = importlib.import_module("contractex.storage.setup")
    basic_config.assert_not_called()
    assert callable(setup.main)


def test_sql_files_agree_on_the_vector_size():
    sizes = {
        sql_file.name: set(re.findall(r"vector\((\d+)\)", sql_file.read_text(), re.IGNORECASE))
        for sql_file in STORAGE_DIR.rglob("*.sql")
    }
    assert {size for found in sizes.values() for size in found} == {"384"}, sizes


def test_connection_error_log_leaves_out_row_values(caplog):
    error = psycopg2.errors.NotNullViolation(
        'null value in column "filename" violates not-null constraint\n'
        f"DETAIL:  Failing row contains (5, null, null, null, {SECRET}, {{}})."
    )
    with patch("contractex.storage.connection.psycopg2.connect", return_value=MagicMock()):
        with caplog.at_level(logging.ERROR), pytest.raises(psycopg2.Error):
            with get_connection(
                {"db_name": "d", "user": "u", "password": "", "host": "h", "port": 1}
            ):
                raise error
    assert "not-null constraint" in caplog.text
    assert "123-45-6789" not in caplog.text


# ============================================================================
# Against PostgreSQL
# ============================================================================


@pytest.mark.integration
class TestDuplicateFilename:
    def test_different_content_under_the_same_filename_is_refused(self, doc_repo):
        from contractex.storage import DuplicateDocumentError

        first = doc_repo.insert(
            Document(filename="contract.pdf", file_hash="aaa", extracted_text="Client A NDA")
        )
        with pytest.raises(DuplicateDocumentError, match="contract.pdf") as raised:
            doc_repo.insert(
                Document(filename="contract.pdf", file_hash="bbb", extracted_text="Client B lease")
            )
        assert isinstance(raised.value, ContractExError)
        assert "Client" not in str(raised.value)
        assert doc_repo.get_by_id(first).extracted_text == "Client A NDA"
        assert doc_repo.count() == 1

    def test_different_text_without_hashes_is_refused(self, doc_repo):
        from contractex.storage import DuplicateDocumentError

        doc_repo.insert(Document(filename="a.txt", extracted_text="one"))
        with pytest.raises(DuplicateDocumentError):
            doc_repo.insert(Document(filename="a.txt", extracted_text="two"))

    def test_same_document_again_returns_the_existing_id(self, doc_repo):
        first = doc_repo.insert(Document(filename="a.pdf", file_hash="aaa", extracted_text="x"))
        # same file, text not extracted yet
        assert doc_repo.insert(Document(filename="a.pdf", file_hash="aaa")) == first
        text_only = doc_repo.insert(Document(filename="b.txt", extracted_text="same"))
        assert doc_repo.insert(Document(filename="b.txt", extracted_text="same")) == text_only


@pytest.mark.integration
class TestCallerConnection:
    def test_writes_run_on_the_given_connection_and_are_not_committed(self, clean_db):
        repo = DocumentRepository(connection=clean_db)
        doc_id = repo.insert(Document(filename="atomic.pdf", extracted_text="x"))
        assert repo.get_by_id(doc_id).filename == "atomic.pdf"

        clean_db.rollback()

        assert not clean_db.closed
        assert _count(clean_db) == 0

    def test_document_and_clauses_roll_back_together(self, clean_db):
        docs, clauses = DocumentRepository(clean_db), ClauseRepository(clean_db)
        with pytest.raises(psycopg2.Error):
            doc_id = docs.insert(Document(filename="atomic.pdf", extracted_text="x"))
            clauses.insert_batch(
                [
                    Clause(document_id=doc_id, clause_text="ok"),
                    Clause(document_id=doc_id, clause_text=None),  # violates NOT NULL
                ]
            )
        clean_db.rollback()
        assert _count(clean_db) == 0
        assert _count(clean_db, "clauses") == 0

    def test_committed_by_the_caller(self, clean_db):
        DocumentRepository(clean_db).insert(Document(filename="kept.pdf"))
        clean_db.commit()
        clean_db.rollback()
        assert _count(clean_db) == 1


@pytest.mark.integration
class TestLogging:
    def test_failed_insert_does_not_log_the_row(self, clean_db, caplog):
        with caplog.at_level(logging.DEBUG), pytest.raises(psycopg2.Error):
            DocumentRepository(clean_db).insert(Document(filename=None, extracted_text=SECRET))
        clean_db.rollback()
        assert "Failed to insert document" in caplog.text
        assert "not-null constraint" in caplog.text
        assert "123-45-6789" not in caplog.text

    def test_connection_log_does_not_contain_the_row(self, test_database, caplog):
        with caplog.at_level(logging.DEBUG), pytest.raises(psycopg2.Error):
            with get_connection(test_database) as conn:
                conn.cursor().execute(
                    "INSERT INTO documents (filename, extracted_text) VALUES (NULL, %s)", (SECRET,)
                )
        assert "Database error" in caplog.text
        assert "123-45-6789" not in caplog.text


@pytest.mark.integration
class TestMissingRows:
    def test_update_of_a_missing_document_raises(self, doc_repo, caplog):
        from contractex.storage import DocumentNotFoundError

        with caplog.at_level(logging.INFO):
            with pytest.raises(DocumentNotFoundError, match="99999"):
                doc_repo.update_metadata(99999, {"reviewed": True})
            with pytest.raises(DocumentNotFoundError, match="99999"):
                doc_repo.update_extracted_text(99999, "text")
        assert "Updated" not in caplog.text

    def test_delete_says_whether_a_row_was_deleted(self, doc_repo, caplog):
        doc_id = doc_repo.insert(Document(filename="a.pdf"))
        with caplog.at_level(logging.INFO):
            assert doc_repo.delete(99999) is False
            assert "Deleted document 99999" not in caplog.text
            assert doc_repo.delete(doc_id) is True


@pytest.mark.integration
class TestMetadata:
    def test_update_metadata_merges_so_two_writers_keep_each_others_keys(self, doc_repo):
        doc_id = doc_repo.insert(Document(filename="race.pdf", metadata={"contract_type": "NDA"}))
        a, b = doc_repo.get_by_id(doc_id), doc_repo.get_by_id(doc_id)  # two workers read

        a.update_metadata(parties=["Acme"])
        doc_repo.update_metadata(doc_id, a.metadata)
        b.update_metadata(governing_law="DE", contract_type="MSA")
        doc_repo.update_metadata(doc_id, b.metadata)

        assert doc_repo.get_by_id(doc_id).metadata == {
            "contract_type": "MSA",
            "parties": ["Acme"],
            "governing_law": "DE",
        }

    def test_search_with_no_filters_returns_every_document(self, doc_repo, multiple_documents):
        for doc in multiple_documents:
            doc_repo.insert(doc)
        assert len(doc_repo.search_by_metadata({})) == len(multiple_documents)

    def test_search_by_non_string_values(self, doc_repo):
        doc_repo.insert(Document(filename="a.pdf", metadata={"page_count": 3, "reviewed": True}))
        doc_repo.insert(Document(filename="b.pdf", metadata={"page_count": 30, "reviewed": False}))

        assert [d.filename for d in doc_repo.search_by_metadata({"page_count": 3})] == ["a.pdf"]
        assert [d.filename for d in doc_repo.search_by_metadata({"reviewed": False})] == ["b.pdf"]
        # a string still matches the stored value's text, as before
        assert [d.filename for d in doc_repo.search_by_metadata({"page_count": "30"})] == ["b.pdf"]


@pytest.mark.integration
class TestLimitsAndEmbeddings:
    def test_limit_zero_returns_nothing(self, doc_repo, clause_repo):
        doc_id = doc_repo.insert(Document(filename="a.pdf"))
        clause_repo.insert(Clause(document_id=doc_id, clause_text="x", clause_type="payment"))
        assert doc_repo.get_all(limit=0) == []
        assert clause_repo.search_by_type("payment", limit=0) == []
        assert len(doc_repo.get_all(limit=1)) == 1

    def test_get_unembedded_without_the_embedding_column_says_what_to_run(self, clause_repo):
        # schema.sql alone has no clauses.embedding; migrations/add_embeddings.sql adds it
        with pytest.raises(ContractExError, match="add_embeddings.sql"):
            clause_repo.get_unembedded()


@pytest.mark.integration
def test_v1_to_v2_migration_keeps_each_documents_clauses(test_db_config, db_schema_sql):
    """Runs in its own database: the migration renames the v1 tables."""
    server = {
        "user": test_db_config["user"],
        "password": test_db_config["password"],
        "host": test_db_config["host"],
        "port": test_db_config["port"],
    }
    admin = psycopg2.connect(dbname="postgres", **server)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT count(*) FROM pg_available_extensions WHERE name IN ('vector', 'pgcrypto')")
    if cur.fetchone()[0] < 2:
        admin.close()
        pytest.skip("migration needs the pgcrypto and vector extensions on the server")

    db_name = "clause_docs_migration_test"
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.execute(f"CREATE DATABASE {db_name} ENCODING 'UTF8'")
    try:
        conn = psycopg2.connect(dbname=db_name, **server)
        conn.autocommit = True
        try:
            db = conn.cursor()
            db.execute(db_schema_sql)
            # Three NDAs without a file hash, as setup.py ingests .txt files, and one PDF
            for name, file_hash in [("alpha", None), ("beta", None), ("gamma", None), ("d", "h")]:
                db.execute(
                    "INSERT INTO documents (filename, file_hash, metadata) "
                    'VALUES (%s, %s, \'{"contract_type": "NDA"}\') RETURNING id',
                    (f"{name}.txt", file_hash),
                )
                db.execute(
                    "INSERT INTO clauses (document_id, clause_text, clause_type, metadata) "
                    "VALUES (%s, %s, 'confidentiality', '{\"section_number\": \"7.1\"}')",
                    (db.fetchone()[0], f"{name} clause"),
                )

            db.execute((STORAGE_DIR / "migrations" / "v1_to_v2.sql").read_text())

            db.execute(
                "SELECT ld.metadata->>'filename', ef.field_value->>'text', "
                "ef.field_value->>'section_number' "
                "FROM extracted_fields ef JOIN legal_docs ld USING (doc_id) ORDER BY 1, 2"
            )
            assert db.fetchall() == [
                ("alpha.txt", "alpha clause", "7.1"),
                ("beta.txt", "beta clause", "7.1"),
                ("d.txt", "d clause", "7.1"),
                ("gamma.txt", "gamma clause", "7.1"),
            ]
        finally:
            conn.close()
    finally:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        admin.close()
