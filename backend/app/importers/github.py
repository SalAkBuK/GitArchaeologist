from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import AnyHttpUrl, AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.importers.errors import RepositoryImportError
from app.importers.limits import RepositoryImportLimits
from app.parsers.git_log import FULL_HASH_RE
from app.schemas.repository_import import RepositoryImportWarning


OWNER_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,39}(?<!-)$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
ModelType = TypeVar("ModelType", bound=BaseModel)


@dataclass(frozen=True)
class GitHubRepositoryReference:
    owner: str
    repository: str

    @property
    def repository_id(self) -> str:
        return f"{self.owner}/{self.repository}"

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}"


def normalize_github_repository_url(value: str) -> GitHubRepositoryReference:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="repositoryUrl must be a valid public GitHub HTTPS repository URL",
            status_code=422,
        ) from exc

    if parsed.scheme.lower() != "https":
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="Only HTTPS GitHub repository URLs are supported",
            status_code=422,
        )
    if parsed.hostname is None or parsed.hostname.lower() != "github.com":
        raise RepositoryImportError(
            code="unsupported_repository_host",
            message="Only github.com repository URLs are supported",
            status_code=422,
        )
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="Repository URLs must not contain credentials or a port",
            status_code=422,
        )
    if parsed.query or parsed.fragment:
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="Repository URLs must not contain a query string or fragment",
            status_code=422,
        )

    parts = parsed.path.rstrip("/").split("/")
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="Repository URL path must contain exactly an owner and repository name",
            status_code=422,
        )
    owner = parts[1]
    repository = parts[2][:-4] if parts[2].lower().endswith(".git") else parts[2]
    if (
        not OWNER_RE.fullmatch(owner)
        or not REPOSITORY_RE.fullmatch(repository)
        or repository in {".", ".."}
    ):
        raise RepositoryImportError(
            code="invalid_repository_url",
            message="Repository URL contains an invalid owner or repository name",
            status_code=422,
        )
    return GitHubRepositoryReference(owner=owner.lower(), repository=repository.lower())


class _RepositoryMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str
    private: bool


class _Author(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login: str = Field(min_length=1)


class _Branch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str = Field(min_length=1)


class _PullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int = Field(gt=0)
    title: str = Field(min_length=1)
    body: str | None
    state: Literal["open", "closed"]
    user: _Author
    created_at: AwareDatetime
    updated_at: AwareDatetime
    merged_at: AwareDatetime | None
    html_url: AnyHttpUrl
    base: _Branch
    head: _Branch


class _CommitReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha: str


@dataclass(frozen=True)
class GitHubPullRequestAcquisition:
    fixture_content: str
    warnings: list[RepositoryImportWarning]


class GitHubPublicRepositoryClient:
    def __init__(
        self,
        limits: RepositoryImportLimits,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.limits = limits
        self.client = client

    def fetch(
        self, repository: GitHubRepositoryReference
    ) -> GitHubPullRequestAcquisition:
        if self.client is not None:
            return self._fetch_with_client(repository, self.client)
        with httpx.Client(
            base_url="https://api.github.com",
            timeout=self.limits.network_timeout_seconds,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "GitArchaeologist-local-import",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            follow_redirects=False,
        ) as client:
            return self._fetch_with_client(repository, client)

    def _fetch_with_client(
        self,
        repository: GitHubRepositoryReference,
        client: httpx.Client,
    ) -> GitHubPullRequestAcquisition:
        metadata_payload = self._get_json(
            client, f"/repos/{repository.owner}/{repository.repository}"
        )
        metadata = self._validate(_RepositoryMetadata, metadata_payload)
        if metadata.private or metadata.full_name.lower() != repository.repository_id:
            raise RepositoryImportError(
                code="repository_not_found_or_inaccessible",
                message="Public GitHub repository was not found or is inaccessible",
                status_code=404,
            )

        pull_payloads, pull_requests_truncated = self._paginate(
            client,
            f"/repos/{repository.owner}/{repository.repository}/pulls",
            self.limits.max_pull_requests,
            params={"state": "all", "sort": "updated", "direction": "desc"},
        )
        warnings: list[RepositoryImportWarning] = []
        if pull_requests_truncated:
            warnings.append(
                RepositoryImportWarning(
                    code="pull_requests_truncated",
                    message=(
                        f"Pull request import was limited to the newest "
                        f"{self.limits.max_pull_requests} records."
                    ),
                )
            )

        records: list[dict[str, Any]] = []
        for payload in pull_payloads:
            pull_request = self._validate(_PullRequest, payload)
            commit_payloads, commits_truncated = self._paginate(
                client,
                (
                    f"/repos/{repository.owner}/{repository.repository}/pulls/"
                    f"{pull_request.number}/commits"
                ),
                self.limits.max_commits_per_pull_request,
            )
            commit_shas = []
            for commit_payload in commit_payloads:
                commit = self._validate(_CommitReference, commit_payload)
                normalized_sha = commit.sha.strip().lower()
                if not FULL_HASH_RE.fullmatch(normalized_sha):
                    self._malformed_response()
                commit_shas.append(normalized_sha)
            if commits_truncated:
                warnings.append(
                    RepositoryImportWarning(
                        code="pull_request_commits_truncated",
                        message=(
                            f"Pull request #{pull_request.number} commit references were "
                            f"limited to {self.limits.max_commits_per_pull_request}."
                        ),
                    )
                )
            state = "merged" if pull_request.merged_at is not None else pull_request.state
            records.append(
                {
                    "number": pull_request.number,
                    "title": pull_request.title,
                    "body": pull_request.body,
                    "state": state,
                    "author": {"login": pull_request.user.login},
                    "createdAt": pull_request.created_at.isoformat(),
                    "updatedAt": pull_request.updated_at.isoformat(),
                    "mergedAt": (
                        pull_request.merged_at.isoformat()
                        if pull_request.merged_at is not None
                        else None
                    ),
                    "url": str(pull_request.html_url),
                    "baseBranch": pull_request.base.ref,
                    "headBranch": pull_request.head.ref,
                    "commitShas": commit_shas,
                }
            )

        return GitHubPullRequestAcquisition(
            fixture_content=json.dumps(
                {
                    "schemaVersion": 1,
                    "repositoryId": repository.repository_id,
                    "pullRequests": records,
                }
            ),
            warnings=warnings,
        )

    def _paginate(
        self,
        client: httpx.Client,
        path: str,
        maximum: int,
        *,
        params: dict[str, str] | None = None,
    ) -> tuple[list[Any], bool]:
        items: list[Any] = []
        page = 1
        target = maximum + 1
        while len(items) < target:
            page_size = min(100, target - len(items))
            request_params: dict[str, str | int] = {
                **(params or {}),
                "per_page": page_size,
                "page": page,
            }
            payload = self._get_json(client, path, params=request_params)
            if not isinstance(payload, list):
                self._malformed_response()
            items.extend(payload)
            if len(payload) < page_size:
                break
            page += 1
        return items[:maximum], len(items) > maximum

    def _get_json(
        self,
        client: httpx.Client,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        try:
            response = client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise RepositoryImportError(
                code="github_api_timeout",
                message="GitHub API request timed out",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise RepositoryImportError(
                code="github_api_unavailable",
                message="GitHub API is unavailable",
                status_code=502,
            ) from exc

        if response.status_code in {429} or (
            response.status_code == 403
            and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise RepositoryImportError(
                code="github_api_rate_limited",
                message="GitHub API rate limit was reached",
                status_code=429,
            )
        if response.status_code in {403, 404}:
            raise RepositoryImportError(
                code="repository_not_found_or_inaccessible",
                message="Public GitHub repository was not found or is inaccessible",
                status_code=404,
            )
        if response.status_code >= 400:
            raise RepositoryImportError(
                code="github_api_failure",
                message="GitHub API request failed",
                status_code=502,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise RepositoryImportError(
                code="malformed_github_response",
                message="GitHub API returned malformed JSON",
                status_code=502,
            ) from exc

    @staticmethod
    def _validate(model: type[ModelType], payload: Any) -> ModelType:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise RepositoryImportError(
                code="malformed_github_response",
                message="GitHub API response is missing required fields",
                status_code=502,
            ) from exc

    @staticmethod
    def _malformed_response() -> None:
        raise RepositoryImportError(
            code="malformed_github_response",
            message="GitHub API response contains an invalid commit SHA",
            status_code=502,
        )
