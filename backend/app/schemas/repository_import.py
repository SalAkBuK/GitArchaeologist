from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ingestion import IngestionResult
from app.schemas.pull_request import PullRequestIngestionResult


ImportWarningCode = Literal[
    "git_history_truncated",
    "pull_requests_truncated",
    "pull_request_commits_truncated",
]


class RepositoryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repository_url: str = Field(alias="repositoryUrl", min_length=1, max_length=2048)


class RepositoryImportWarning(BaseModel):
    code: ImportWarningCode
    message: str


class RepositoryImportLimitsRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_commits: int = Field(alias="maxCommits")
    max_pull_requests: int = Field(alias="maxPullRequests")
    max_commits_per_pull_request: int = Field(alias="maxCommitsPerPullRequest")
    max_repository_bytes: int = Field(alias="maxRepositoryBytes")


class RepositoryImportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repository_id: str = Field(alias="repositoryId")
    repository_url: str = Field(alias="repositoryUrl")
    selected_commit_sha: str = Field(alias="selectedCommitSha")
    git_ingestion: IngestionResult = Field(alias="gitIngestion")
    pull_request_ingestion: PullRequestIngestionResult = Field(
        alias="pullRequestIngestion"
    )
    warnings: list[RepositoryImportWarning]
    limits: RepositoryImportLimitsRead
