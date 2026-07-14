from __future__ import annotations

import pytest

from app.database.session import Database
from app.models.artifact import ArtifactModel
from app.repositories.artifacts import ArtifactRepository
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


def test_changed_reingestion_replaces_the_complete_commit_snapshot(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()

    with database.session_factory() as session:
        service = GitIngestionService(session)
        service.ingest(
            "acme/platform",
            commit_record(
                HASH_ONE,
                message="Old message",
                files=[
                    "M\tremoved.py",
                    "M\tstatus.py",
                    "R100\told-name.py\tfirst-name.py",
                    "M\tkeep.py",
                ],
            ),
        )
        result = service.ingest(
            "acme/platform",
            commit_record(
                HASH_ONE,
                message="New message",
                files=[
                    "A\tstatus.py",
                    "R100\told-name.py\tsecond-name.py",
                    "A\tnew.py",
                    "M\tkeep.py",
                ],
            ),
        )
        investigation = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/platform",
            commit_sha=HASH_ONE,
        )

        assert result.records_inserted == 3
        assert result.records_updated == 1
        assert result.records_deleted == 3
        assert result.records_skipped_as_duplicates == 1
        assert investigation is not None
        assert investigation.selected_commit.title == "New message"
        assert {
            (
                artifact.metadata["changeStatus"],
                artifact.metadata["previousPath"],
                artifact.metadata["path"],
            )
            for artifact in investigation.modified_files
        } == {
            ("added", None, "status.py"),
            ("renamed", "old-name.py", "second-name.py"),
            ("added", None, "new.py"),
            ("modified", None, "keep.py"),
        }
        assert {edge.to_artifact_id for edge in investigation.evidence_edges} == {
            artifact.id for artifact in investigation.modified_files
        }

    database.dispose()


def test_reconciliation_preserves_other_commits_and_repositories(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()

    with database.session_factory() as session:
        service = GitIngestionService(session)
        service.ingest(
            "acme/platform",
            commit_record(HASH_ONE, files=["M\tfirst.py"])
            + "\n"
            + commit_record(HASH_TWO, files=["M\tsecond.py"]),
        )
        service.ingest(
            "acme/other",
            commit_record(HASH_ONE, files=["M\tother.py"]),
        )
        service.ingest(
            "acme/platform",
            commit_record(HASH_ONE, message="Updated", files=["A\treplacement.py"]),
        )

        repository = ArtifactRepository(session)
        second = repository.build_commit_investigation(
            repository_id="acme/platform", commit_sha=HASH_TWO
        )
        other = repository.build_commit_investigation(
            repository_id="acme/other", commit_sha=HASH_ONE
        )
        assert second is not None
        assert [artifact.metadata["path"] for artifact in second.modified_files] == ["second.py"]
        assert other is not None
        assert [artifact.metadata["path"] for artifact in other.modified_files] == ["other.py"]

    database.dispose()


def test_multiple_commit_snapshots_reconcile_independently(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()

    with database.session_factory() as session:
        service = GitIngestionService(session)
        service.ingest(
            "acme/platform",
            commit_record(HASH_ONE, message="One old", files=["M\tone-old.py"])
            + "\n"
            + commit_record(HASH_TWO, message="Two old", files=["M\ttwo-old.py"]),
        )
        result = service.ingest(
            "acme/platform",
            commit_record(HASH_ONE, message="One new", files=["A\tone-new.py"])
            + "\n"
            + commit_record(HASH_TWO, message="Two new", files=["D\ttwo-new.py"]),
        )

        repository = ArtifactRepository(session)
        first = repository.build_commit_investigation(
            repository_id="acme/platform", commit_sha=HASH_ONE
        )
        second = repository.build_commit_investigation(
            repository_id="acme/platform", commit_sha=HASH_TWO
        )
        assert result.records_updated == 2
        assert result.records_inserted == 2
        assert result.records_deleted == 2
        assert first is not None and second is not None
        assert [artifact.metadata["path"] for artifact in first.modified_files] == ["one-new.py"]
        assert [artifact.metadata["path"] for artifact in second.modified_files] == ["two-new.py"]

    database.dispose()


def test_failed_reconciliation_rolls_back_the_entire_snapshot(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(database_url)
    database.create_schema()

    with database.session_factory() as session:
        GitIngestionService(session).ingest(
            "acme/platform",
            commit_record(HASH_ONE, message="Original", files=["M\toriginal.py"]),
        )

    with database.session_factory() as session:
        def fail_flush(*args: object, **kwargs: object) -> None:
            raise RuntimeError("forced reconciliation failure")

        monkeypatch.setattr(session, "flush", fail_flush)
        with pytest.raises(RuntimeError, match="forced reconciliation failure"):
            GitIngestionService(session).ingest(
                "acme/platform",
                commit_record(HASH_ONE, message="Changed", files=["A\tchanged.py"]),
            )

    with database.session_factory() as session:
        investigation = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/platform", commit_sha=HASH_ONE
        )
        assert investigation is not None
        assert investigation.selected_commit.title == "Original"
        assert [artifact.metadata["path"] for artifact in investigation.modified_files] == [
            "original.py"
        ]

    database.dispose()
