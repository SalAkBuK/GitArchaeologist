from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.database.session import Database
from app.models.artifact import ArtifactModel
from app.services.pull_request_ingestion import PullRequestIngestionService
from tests.test_git_parser import HASH_ONE, HASH_TWO
from tests.test_pull_request_ingestion_api import pull_request


def fixture(records: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "schemaVersion": 1,
            "repositoryId": "acme/platform",
            "pullRequests": records,
        }
    )


def test_successful_ingestion_is_idempotent_and_partial_upsert_preserves_omitted_records(
    database_url: str,
) -> None:
    database = Database(database_url)
    database.create_schema()
    with database.session_factory() as session:
        service = PullRequestIngestionService(session)
        first = service.ingest(
            "acme/platform",
            fixture([pull_request(22), pull_request(23, commit_shas=[])]),
        )
        duplicate = service.ingest(
            "acme/platform",
            fixture([pull_request(22), pull_request(23, commit_shas=[])]),
        )
        changed = service.ingest(
            "acme/platform",
            fixture(
                [
                    pull_request(
                        22,
                        title="Updated metadata",
                        body=None,
                        commit_shas=[HASH_TWO],
                    )
                ]
            ),
        )

        assert first.records_inserted == 2
        assert duplicate.records_skipped_as_duplicates == 2
        assert changed.records_updated == 1

    with database.session_factory() as session:
        artifacts = list(session.scalars(select(ArtifactModel)))
        by_number = {artifact.external_id: artifact for artifact in artifacts}
        assert set(by_number) == {"22", "23"}
        assert by_number["22"].title == "Updated metadata"
        assert by_number["22"].artifact_metadata["body"] is None
        assert by_number["22"].artifact_metadata["commitShas"] == [HASH_TWO]

    database.dispose()


def test_persistence_failure_rolls_back_all_fixture_changes(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(database_url)
    database.create_schema()
    with database.session_factory() as session:
        PullRequestIngestionService(session).ingest(
            "acme/platform",
            fixture([pull_request(22, title="Original")]),
        )

    with database.session_factory() as session:
        original_flush = session.flush
        failed = False

        def flush_then_fail(*args: object, **kwargs: object) -> None:
            nonlocal failed
            original_flush(*args, **kwargs)
            if not failed:
                failed = True
                raise RuntimeError("forced persistence failure")

        monkeypatch.setattr(session, "flush", flush_then_fail)
        with pytest.raises(RuntimeError, match="forced persistence failure"):
            PullRequestIngestionService(session).ingest(
                "acme/platform",
                fixture(
                    [
                        pull_request(22, title="Changed"),
                        pull_request(23, title="New record"),
                    ]
                ),
            )

    with database.session_factory() as session:
        artifacts = list(session.scalars(select(ArtifactModel)))
        assert [(artifact.external_id, artifact.title) for artifact in artifacts] == [
            ("22", "Original")
        ]

    database.dispose()
