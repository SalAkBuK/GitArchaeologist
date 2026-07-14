from __future__ import annotations

from app.database.session import Database
from app.models.artifact import ArtifactModel
from app.services.git_ingestion import GitIngestionService
from tests.test_git_parser import HASH_ONE, HASH_TWO, commit_record


def test_duplicate_import_prevention_and_summary_counts(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()
    malformed = (
        f"commit {HASH_TWO}\n"
        "Author: Grace Hopper <grace@example.com>\n"
        "Date: not-a-date\n\n"
        "    Invalid timestamp\n"
    )

    with database.session_factory() as session:
        first = GitIngestionService(session).ingest(
            "acme/platform",
            commit_record(HASH_ONE) + "\n" + malformed,
        )
        second = GitIngestionService(session).ingest(
            "acme/platform",
            commit_record(HASH_ONE) + "\n" + malformed,
        )

        assert first.records_parsed == 1
        assert first.records_inserted == 1
        assert first.records_skipped_as_duplicates == 0
        assert first.records_rejected == 1
        assert len(first.validation_errors) == 1

        assert second.records_parsed == 1
        assert second.records_inserted == 0
        assert second.records_skipped_as_duplicates == 1
        assert second.records_rejected == 1
        assert session.query(ArtifactModel).count() == 1

    database.dispose()


def test_duplicate_import_prevention_includes_modified_files(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()

    with database.session_factory() as session:
        first = GitIngestionService(session).ingest(
            "acme/platform",
            commit_record(HASH_ONE, files=["A\tbackend/app/cache.py"]),
        )
        second = GitIngestionService(session).ingest(
            "acme/platform",
            commit_record(HASH_ONE, files=["A\tbackend/app/cache.py"]),
        )

        assert first.records_inserted == 2
        assert first.records_skipped_as_duplicates == 0
        assert second.records_inserted == 0
        assert second.records_skipped_as_duplicates == 2
        assert session.query(ArtifactModel).count() == 2

    database.dispose()
