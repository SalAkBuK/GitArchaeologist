from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.importers.errors import RepositoryImportError
from app.schemas.ingestion import IngestionResult
from app.schemas.pull_request import PullRequestIngestionResult
from app.schemas.repository_import import (
    RepositoryImportLimitsRead,
    RepositoryImportResponse,
    RepositoryImportWarning,
)
from app.services.repository_import import RepositoryImportService
from tests.test_git_parser import HASH_ONE


def successful_response() -> RepositoryImportResponse:
    return RepositoryImportResponse(
        repositoryId="acme/platform",
        repositoryUrl="https://github.com/acme/platform",
        selectedCommitSha=HASH_ONE,
        gitIngestion=IngestionResult(
            repositoryId="acme/platform",
            recordsParsed=2,
            recordsInserted=2,
            recordsUpdated=0,
            recordsDeleted=0,
            recordsSkippedAsDuplicates=0,
            recordsRejected=0,
            validationErrors=[],
        ),
        pullRequestIngestion=PullRequestIngestionResult(
            repositoryId="acme/platform",
            recordsReceived=1,
            recordsInserted=1,
            recordsUpdated=0,
            recordsSkippedAsDuplicates=0,
            recordsRejected=0,
            explicitCommitReferencesResolved=1,
            explicitCommitReferencesUnresolved=0,
            validationErrors=[],
        ),
        warnings=[
            RepositoryImportWarning(
                code="git_history_truncated",
                message="Git history import was limited to the newest 100 commits.",
            )
        ],
        limits=RepositoryImportLimitsRead(
            maxCommits=100,
            maxPullRequests=10,
            maxCommitsPerPullRequest=50,
            maxRepositoryBytes=100 * 1024 * 1024,
        ),
    )


def test_repository_import_endpoint_returns_stable_summary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_urls: list[str] = []

    def import_repository(
        self: RepositoryImportService,
        repository_url: str,
    ) -> RepositoryImportResponse:
        seen_urls.append(repository_url)
        return successful_response()

    monkeypatch.setattr(RepositoryImportService, "import_repository", import_repository)
    response = client.post(
        "/api/repositories/import",
        json={"repositoryUrl": "https://github.com/Acme/Platform.git"},
    )

    assert response.status_code == 200
    assert seen_urls == ["https://github.com/Acme/Platform.git"]
    assert response.json() == {
        "repositoryId": "acme/platform",
        "repositoryUrl": "https://github.com/acme/platform",
        "selectedCommitSha": HASH_ONE,
        "gitIngestion": {
            "repositoryId": "acme/platform",
            "recordsParsed": 2,
            "recordsInserted": 2,
            "recordsUpdated": 0,
            "recordsDeleted": 0,
            "recordsSkippedAsDuplicates": 0,
            "recordsRejected": 0,
            "validationErrors": [],
        },
        "pullRequestIngestion": {
            "repositoryId": "acme/platform",
            "recordsReceived": 1,
            "recordsInserted": 1,
            "recordsUpdated": 0,
            "recordsSkippedAsDuplicates": 0,
            "recordsRejected": 0,
            "explicitCommitReferencesResolved": 1,
            "explicitCommitReferencesUnresolved": 0,
            "validationErrors": [],
        },
        "warnings": [
            {
                "code": "git_history_truncated",
                "message": "Git history import was limited to the newest 100 commits.",
            }
        ],
        "limits": {
            "maxCommits": 100,
            "maxPullRequests": 10,
            "maxCommitsPerPullRequest": 50,
            "maxRepositoryBytes": 104857600,
        },
    }


def test_repository_import_endpoint_rejects_invalid_url_without_external_work(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/repositories/import",
        json={"repositoryUrl": "git@github.com:acme/platform.git"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "invalid_repository_url",
        "message": "Only HTTPS GitHub repository URLs are supported",
    }


@pytest.mark.parametrize(
    ("code", "message", "status_code"),
    [
        (
            "repository_not_found_or_inaccessible",
            "Public GitHub repository was not found or is inaccessible",
            404,
        ),
        ("git_timeout", "Git repository import timed out", 504),
        ("repository_too_large", "Repository exceeds the configured import size limit", 413),
        ("github_api_timeout", "GitHub API request timed out", 504),
        ("github_api_rate_limited", "GitHub API rate limit was reached", 429),
        ("malformed_github_response", "GitHub API response is missing required fields", 502),
    ],
)
def test_repository_import_endpoint_maps_stable_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    message: str,
    status_code: int,
) -> None:
    def fail(self: RepositoryImportService, repository_url: str) -> RepositoryImportResponse:
        raise RepositoryImportError(code=code, message=message, status_code=status_code)

    monkeypatch.setattr(RepositoryImportService, "import_repository", fail)
    response = client.post(
        "/api/repositories/import",
        json={"repositoryUrl": "https://github.com/acme/platform"},
    )

    assert response.status_code == status_code
    assert response.json()["detail"] == {"code": code, "message": message}


def test_repository_import_endpoint_sanitizes_unexpected_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(self: RepositoryImportService, repository_url: str) -> RepositoryImportResponse:
        raise RuntimeError("secret path C:/temporary/repository and raw upstream payload")

    monkeypatch.setattr(RepositoryImportService, "import_repository", fail)
    response = client.post(
        "/api/repositories/import",
        json={"repositoryUrl": "https://github.com/acme/platform"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "repository_import_failed",
        "message": "Repository import failed",
    }
    assert "temporary" not in response.text


def test_repository_import_request_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/api/repositories/import",
        json={
            "repositoryUrl": "https://github.com/acme/platform",
            "token": "must-not-be-accepted",
        },
    )

    assert response.status_code == 422
