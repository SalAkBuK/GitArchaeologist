from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.importers.errors import RepositoryImportError
from app.importers.git import GitRepositoryAcquirer
from app.importers.github import (
    GitHubPublicRepositoryClient,
    normalize_github_repository_url,
)
from app.importers.limits import RepositoryImportLimits
from tests.test_git_parser import HASH_ONE, HASH_TWO, commit_record


@pytest.mark.parametrize(
    ("url", "repository_id", "canonical_url"),
    [
        (
            "https://github.com/Owner/Repository",
            "owner/repository",
            "https://github.com/owner/repository",
        ),
        (
            "https://github.com/owner/repository/",
            "owner/repository",
            "https://github.com/owner/repository",
        ),
        (
            "https://github.com/owner/repository.git",
            "owner/repository",
            "https://github.com/owner/repository",
        ),
    ],
)
def test_normalizes_supported_github_urls(
    url: str,
    repository_id: str,
    canonical_url: str,
) -> None:
    result = normalize_github_repository_url(url)

    assert result.repository_id == repository_id
    assert result.canonical_url == canonical_url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://gitlab.com/owner/repository", "unsupported_repository_host"),
        ("git@github.com:owner/repository.git", "invalid_repository_url"),
        ("ssh://git@github.com/owner/repository.git", "invalid_repository_url"),
        ("C:/repositories/local", "invalid_repository_url"),
        ("https://user:secret@github.com/owner/repository", "invalid_repository_url"),
        ("https://github.com/owner/repository/issues", "invalid_repository_url"),
        ("https://github.com/owner/repository?tab=readme", "invalid_repository_url"),
        ("https://github.com/owner/repository#readme", "invalid_repository_url"),
    ],
)
def test_rejects_unsupported_repository_urls(url: str, code: str) -> None:
    with pytest.raises(RepositoryImportError) as raised:
        normalize_github_repository_url(url)

    assert raised.value.code == code
    assert raised.value.status_code == 422


def test_git_acquisition_uses_safe_bounded_commands_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_DIR", "unsafe-directory")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "http.extraHeader")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "Authorization: secret")
    calls: list[tuple[list[str], dict[str, Any]]] = []
    clone_root: Path | None = None

    def runner(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal clone_root
        calls.append((arguments, kwargs))
        if "clone" in arguments:
            clone_path = Path(arguments[-1])
            clone_root = clone_path.parent
            (clone_path / ".git").mkdir(parents=True)
            (clone_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
            stdout = b""
        elif "rev-list" in arguments:
            stdout = f"{HASH_ONE}\n{HASH_TWO}\n".encode()
        else:
            stdout = commit_record(
                HASH_ONE,
                files=["M\tbackend/app/main.py"],
            ).encode()
        return subprocess.CompletedProcess(arguments, 0, stdout=stdout, stderr=b"")

    limits = RepositoryImportLimits(
        max_commits=1,
        max_repository_bytes=1024,
        temporary_directory=str(tmp_path),
    )
    repository = normalize_github_repository_url("https://github.com/acme/platform")
    result = GitRepositoryAcquirer(
        limits,
        runner=runner,
        git_executable="git",
    ).acquire(repository)

    clone_arguments, clone_kwargs = calls[0]
    assert result.selected_commit_sha == HASH_ONE
    assert result.truncated is True
    assert "--depth" in clone_arguments
    assert clone_arguments[clone_arguments.index("--depth") + 1] == "2"
    assert "--single-branch" in clone_arguments
    assert "--no-tags" in clone_arguments
    assert "--no-checkout" in clone_arguments
    assert "--recurse-submodules" not in clone_arguments
    assert clone_arguments[-2] == "https://github.com/acme/platform"
    assert clone_kwargs["shell"] is False
    assert clone_kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert clone_kwargs["env"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert clone_kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GIT_DIR" not in clone_kwargs["env"]
    assert "GIT_CONFIG_COUNT" not in clone_kwargs["env"]
    assert "GIT_CONFIG_KEY_0" not in clone_kwargs["env"]
    assert "GIT_CONFIG_VALUE_0" not in clone_kwargs["env"]
    assert all(call[1]["timeout"] == limits.git_timeout_seconds for call in calls)
    assert clone_root is not None and not clone_root.exists()


def test_git_acquisition_selects_first_commit_emitted_for_ingestion(
    tmp_path: Path,
) -> None:
    def runner(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if "clone" in arguments:
            clone_path = Path(arguments[-1])
            (clone_path / ".git").mkdir(parents=True)
            stdout = b""
        elif "rev-list" in arguments:
            # A merge HEAD can be excluded from name-status output by --diff-filter.
            stdout = f"{HASH_ONE}\n".encode()
        else:
            stdout = commit_record(
                HASH_TWO,
                files=["M\tbackend/app/main.py"],
            ).encode()
        return subprocess.CompletedProcess(arguments, 0, stdout=stdout, stderr=b"")

    result = GitRepositoryAcquirer(
        RepositoryImportLimits(max_commits=1, temporary_directory=str(tmp_path)),
        runner=runner,
        git_executable="git",
    ).acquire(normalize_github_repository_url("https://github.com/acme/platform"))

    assert result.selected_commit_sha == HASH_TWO


def test_git_timeout_and_size_failure_clean_temporary_directories(tmp_path: Path) -> None:
    timed_out_root: Path | None = None

    def timeout_runner(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal timed_out_root
        timed_out_root = Path(arguments[-1]).parent
        raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])

    limits = RepositoryImportLimits(temporary_directory=str(tmp_path))
    repository = normalize_github_repository_url("https://github.com/acme/platform")
    with pytest.raises(RepositoryImportError, match="timed out") as timeout_error:
        GitRepositoryAcquirer(
            limits,
            runner=timeout_runner,
            git_executable="git",
        ).acquire(repository)
    assert timeout_error.value.code == "git_timeout"
    assert timed_out_root is not None and not timed_out_root.exists()

    oversized_root: Path | None = None

    def oversized_runner(
        arguments: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal oversized_root
        clone_path = Path(arguments[-1])
        oversized_root = clone_path.parent
        clone_path.mkdir(parents=True)
        (clone_path / "large.pack").write_bytes(b"x" * 11)
        return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

    with pytest.raises(RepositoryImportError) as size_error:
        GitRepositoryAcquirer(
            RepositoryImportLimits(
                max_repository_bytes=10,
                temporary_directory=str(tmp_path),
            ),
            runner=oversized_runner,
            git_executable="git",
        ).acquire(repository)
    assert size_error.value.code == "repository_too_large"
    assert oversized_root is not None and not oversized_root.exists()


def pull_request_payload(number: int) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Pull request {number}",
        "body": "Explicit rationale",
        "state": "closed",
        "user": {"login": "developer"},
        "created_at": "2026-07-10T10:00:00Z",
        "updated_at": "2026-07-11T12:00:00Z",
        "merged_at": "2026-07-11T12:00:00Z",
        "html_url": f"https://github.com/acme/platform/pull/{number}",
        "base": {"ref": "main"},
        "head": {"ref": f"feature/pr-{number}"},
    }


def test_github_api_is_bounded_and_emits_truncation_warnings() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/acme/platform":
            return httpx.Response(200, json={"full_name": "Acme/Platform", "private": False})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[pull_request_payload(2), pull_request_payload(1)],
            )
        if request.url.path.endswith("/pulls/2/commits"):
            return httpx.Response(200, json=[{"sha": HASH_ONE}, {"sha": HASH_TWO}])
        raise AssertionError(f"Unexpected request {request.url}")

    limits = RepositoryImportLimits(max_pull_requests=1, max_commits_per_pull_request=1)
    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.test",
    ) as client:
        result = GitHubPublicRepositoryClient(limits, client=client).fetch(
            normalize_github_repository_url("https://github.com/acme/platform")
        )

    fixture = json.loads(result.fixture_content)
    assert fixture["repositoryId"] == "acme/platform"
    assert fixture["pullRequests"][0]["number"] == 2
    assert fixture["pullRequests"][0]["state"] == "merged"
    assert fixture["pullRequests"][0]["commitShas"] == [HASH_ONE]
    assert [warning.code for warning in result.warnings] == [
        "pull_requests_truncated",
        "pull_request_commits_truncated",
    ]
    pull_request_call = next(request for request in requests if request.url.path.endswith("/pulls"))
    assert pull_request_call.url.params["per_page"] == "2"
    assert pull_request_call.url.params["page"] == "1"


@pytest.mark.parametrize(
    ("response_status", "headers", "expected_code", "expected_status"),
    [
        (404, {}, "repository_not_found_or_inaccessible", 404),
        (403, {"x-ratelimit-remaining": "0"}, "github_api_rate_limited", 429),
        (429, {}, "github_api_rate_limited", 429),
    ],
)
def test_github_api_maps_unavailable_and_rate_limit_responses(
    response_status: int,
    headers: dict[str, str],
    expected_code: str,
    expected_status: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(response_status, headers=headers, request=request)

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.test",
    ) as client:
        with pytest.raises(RepositoryImportError) as raised:
            GitHubPublicRepositoryClient(
                RepositoryImportLimits(),
                client=client,
            ).fetch(normalize_github_repository_url("https://github.com/acme/platform"))

    assert raised.value.code == expected_code
    assert raised.value.status_code == expected_status


def test_github_api_maps_timeout_and_malformed_payload() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    repository = normalize_github_repository_url("https://github.com/acme/platform")
    with httpx.Client(
        transport=httpx.MockTransport(timeout_handler),
        base_url="https://api.github.test",
    ) as client:
        with pytest.raises(RepositoryImportError) as timeout_error:
            GitHubPublicRepositoryClient(
                RepositoryImportLimits(),
                client=client,
            ).fetch(repository)
    assert timeout_error.value.code == "github_api_timeout"

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"private": False}, request=request)

    with httpx.Client(
        transport=httpx.MockTransport(malformed_handler),
        base_url="https://api.github.test",
    ) as client:
        with pytest.raises(RepositoryImportError) as malformed_error:
            GitHubPublicRepositoryClient(
                RepositoryImportLimits(),
                client=client,
            ).fetch(repository)
    assert malformed_error.value.code == "malformed_github_response"
