from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.parsers.git_log import FULL_HASH_RE
from app.schemas.ingestion import IngestionValidationError


PullRequestState = Literal["open", "closed", "merged"]


class PullRequestFixtureAuthor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1, max_length=255)

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class PullRequestFixtureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    body: str | None
    state: PullRequestState
    author: PullRequestFixtureAuthor
    created_at: AwareDatetime = Field(alias="createdAt")
    updated_at: AwareDatetime = Field(alias="updatedAt")
    merged_at: AwareDatetime | None = Field(alias="mergedAt")
    url: AnyHttpUrl | None
    base_branch: str = Field(alias="baseBranch", min_length=1, max_length=255)
    head_branch: str = Field(alias="headBranch", min_length=1, max_length=255)
    commit_shas: list[str] = Field(alias="commitShas")

    @field_validator("title", "base_branch", "head_branch")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("commit_shas")
    @classmethod
    def validate_commit_shas(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            commit_sha = value.strip().lower()
            if not FULL_HASH_RE.fullmatch(commit_sha):
                raise ValueError(
                    "commit SHAs must be full 40- or 64-character hexadecimal identifiers"
                )
            if commit_sha in seen:
                raise ValueError(f"duplicate commit SHA {commit_sha}")
            seen.add(commit_sha)
            normalized.append(commit_sha)
        return sorted(normalized)


class PullRequestFixtureEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    repository_id: str = Field(alias="repositoryId", min_length=1, max_length=255)
    pull_requests: list[dict[str, Any]] = Field(alias="pullRequests")

    @field_validator("repository_id")
    @classmethod
    def normalize_repository_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class PullRequestAuthorRead(BaseModel):
    login: str


class PullRequestRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    repository_id: str = Field(alias="repositoryId")
    number: int
    title: str
    body: str | None
    state: PullRequestState
    author: PullRequestAuthorRead
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    merged_at: datetime | None = Field(alias="mergedAt")
    url: str | None
    base_branch: str = Field(alias="baseBranch")
    head_branch: str = Field(alias="headBranch")
    commit_shas: list[str] = Field(alias="commitShas")


class UnresolvedCommitReferenceRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pull_request_id: str = Field(alias="pullRequestId")
    pull_request_number: int = Field(alias="pullRequestNumber")
    commit_sha: str = Field(alias="commitSha")


class PullRequestIngestionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repository_id: str = Field(alias="repositoryId")
    records_received: int = Field(alias="recordsReceived")
    records_inserted: int = Field(alias="recordsInserted")
    records_updated: int = Field(alias="recordsUpdated")
    records_skipped_as_duplicates: int = Field(alias="recordsSkippedAsDuplicates")
    records_rejected: int = Field(alias="recordsRejected")
    explicit_commit_references_resolved: int = Field(
        alias="explicitCommitReferencesResolved"
    )
    explicit_commit_references_unresolved: int = Field(
        alias="explicitCommitReferencesUnresolved"
    )
    validation_errors: list[IngestionValidationError] = Field(alias="validationErrors")
