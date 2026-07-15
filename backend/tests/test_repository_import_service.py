from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.database.session import Database
from app.importers.errors import RepositoryImportError
from app.importers.git import GitHistoryAcquisition
from app.importers.github import (
    GitHubPullRequestAcquisition,
    GitHubRepositoryReference,
)
from app.importers.limits import RepositoryImportLimits
from app.models.artifact import ArtifactModel
from app.repositories.artifacts import ArtifactRepository
from app.schemas.repository_import import RepositoryImportWarning
from app.services.git_ingestion import GitIngestionService
from app.services.repository_import import RepositoryImportService
from tests.test_git_parser import HASH_ONE, HASH_TWO, commit_record
from tests.test_pull_request_ingestion_api import pull_request


@dataclass
class FakeGitAcquirer:
    content: str
    selected_sha: str = HASH_ONE
    truncated: bool = False
    error: RepositoryImportError | None = None

    def acquire(self, repository: GitHubRepositoryReference) -> GitHistoryAcquisition:
        if self.error is not None:
            raise self.error
        return GitHistoryAcquisition(
            log_content=self.content,
            selected_commit_sha=self.selected_sha,
            truncated=self.truncated,
        )


@dataclass
class FakeGitHubClient:
    records: list[dict[str, object]]
    warnings: list[RepositoryImportWarning] | None = None
    error: RepositoryImportError | None = None

    def fetch(
        self, repository: GitHubRepositoryReference
    ) -> GitHubPullRequestAcquisition:
        if self.error is not None:
            raise self.error
        return GitHubPullRequestAcquisition(
            fixture_content=json.dumps(
                {
                    "schemaVersion": 1,
                    "repositoryId": repository.repository_id,
                    "pullRequests": self.records,
                }
            ),
            warnings=self.warnings or [],
        )


def make_service(
    session: object,
    *,
    git_content: str | None = None,
    pull_requests: list[dict[str, object]] | None = None,
    truncated: bool = False,
) -> RepositoryImportService:
    limits = RepositoryImportLimits(max_commits=2)
    return RepositoryImportService(
        session,  # type: ignore[arg-type]
        limits=limits,
        git_acquirer=FakeGitAcquirer(
            git_content
            or commit_record(
                HASH_ONE,
                files=["M\tbackend/app/main.py"],
            ),
            truncated=truncated,
        ),  # type: ignore[arg-type]
        github_client=FakeGitHubClient(
            pull_requests
            if pull_requests is not None
            else [pull_request(22, commit_shas=[HASH_ONE, HASH_TWO])]
        ),  # type: ignore[arg-type]
    )


def test_import_reuses_normalized_artifacts_and_creates_only_explicit_edges(
    database_url: str,
) -> None:
    database = Database(database_url)
    database.create_schema()
    with database.session_factory() as session:
        result = make_service(session, truncated=True).import_repository(
            "https://github.com/Acme/Platform.git"
        )
        investigation = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/platform",
            commit_sha=HASH_ONE,
        )

        assert result.repository_id == "acme/platform"
        assert result.repository_url == "https://github.com/acme/platform"
        assert result.selected_commit_sha == HASH_ONE
        assert result.git_ingestion.records_inserted == 2
        assert result.pull_request_ingestion.records_inserted == 1
        assert result.pull_request_ingestion.explicit_commit_references_resolved == 1
        assert result.pull_request_ingestion.explicit_commit_references_unresolved == 1
        assert [warning.code for warning in result.warnings] == [
            "git_history_truncated"
        ]
        assert investigation is not None
        assert {edge.relation_type for edge in investigation.evidence_edges} == {
            "contains",
            "modifies",
        }
        contains = next(
            edge for edge in investigation.evidence_edges if edge.relation_type == "contains"
        )
        modifies = next(
            edge for edge in investigation.evidence_edges if edge.relation_type == "modifies"
        )
        assert contains.from_artifact_id == investigation.linked_pull_requests[0].id
        assert contains.to_artifact_id == investigation.selected_commit.id
        assert modifies.from_artifact_id == investigation.selected_commit.id
        assert modifies.to_artifact_id == investigation.modified_files[0].id
        assert session.scalar(
            select(ArtifactModel).where(
                ArtifactModel.repository_id == "acme/platform",
                ArtifactModel.source_type == "git_commit",
                ArtifactModel.external_id == HASH_TWO,
            )
        ) is None

    database.dispose()


def test_repeated_import_is_idempotent_and_changed_pr_snapshot_reconciles(
    database_url: str,
) -> None:
    database = Database(database_url)
    database.create_schema()
    records = [pull_request(22, body="Original rationale", commit_shas=[HASH_ONE])]
    with database.session_factory() as session:
        service = make_service(session, pull_requests=records)
        first = service.import_repository("https://github.com/acme/platform")
        second = service.import_repository("https://github.com/acme/platform")

        assert first.git_ingestion.records_inserted == 2
        assert first.pull_request_ingestion.records_inserted == 1
        assert second.git_ingestion.records_inserted == 0
        assert second.git_ingestion.records_skipped_as_duplicates == 2
        assert second.pull_request_ingestion.records_skipped_as_duplicates == 1

        service.github_client = FakeGitHubClient(
            [pull_request(22, body="Changed rationale", commit_shas=[])]
        )  # type: ignore[assignment]
        changed = service.import_repository("https://github.com/acme/platform")
        investigation = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/platform",
            commit_sha=HASH_ONE,
        )

        assert changed.pull_request_ingestion.records_updated == 1
        assert investigation is not None
        assert investigation.linked_pull_requests == []
        assert all(edge.relation_type != "contains" for edge in investigation.evidence_edges)

    database.dispose()


def test_import_does_not_mutate_unrelated_repository(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()
    with database.session_factory() as session:
        GitIngestionService(session).ingest(
            "acme/other",
            commit_record(HASH_ONE, message="Other repository", files=["A\tother.py"]),
        )
        make_service(session).import_repository("https://github.com/acme/platform")

    with database.session_factory() as session:
        other = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/other",
            commit_sha=HASH_ONE,
        )
        imported = ArtifactRepository(session).build_commit_investigation(
            repository_id="acme/platform",
            commit_sha=HASH_ONE,
        )
        assert other is not None and imported is not None
        assert other.selected_commit.title == "Other repository"
        assert other.modified_files[0].metadata["path"] == "other.py"
        assert other.linked_pull_requests == []
        assert imported.linked_pull_requests[0].repository_id == "acme/platform"

    database.dispose()


def test_upstream_failure_creates_no_database_records(database_url: str) -> None:
    database = Database(database_url)
    database.create_schema()
    failure = RepositoryImportError(
        code="github_api_timeout",
        message="GitHub API request timed out",
        status_code=504,
    )
    with database.session_factory() as session:
        service = RepositoryImportService(
            session,
            limits=RepositoryImportLimits(),
            git_acquirer=FakeGitAcquirer(commit_record()),  # type: ignore[arg-type]
            github_client=FakeGitHubClient([], error=failure),  # type: ignore[arg-type]
        )
        with pytest.raises(RepositoryImportError):
            service.import_repository("https://github.com/acme/platform")
        assert list(session.scalars(select(ArtifactModel))) == []

    database.dispose()


def test_outer_commit_failure_rolls_back_git_and_pr_flushes(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(database_url)
    database.create_schema()
    with database.session_factory() as session:
        original_commit = session.commit
        commit_calls = 0

        def fail_commit() -> None:
            nonlocal commit_calls
            commit_calls += 1
            raise RuntimeError("forced outer commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="forced outer commit failure"):
            make_service(session).import_repository("https://github.com/acme/platform")
        assert commit_calls == 1
        monkeypatch.setattr(session, "commit", original_commit)

    with database.session_factory() as session:
        assert list(session.scalars(select(ArtifactModel))) == []

    database.dispose()
