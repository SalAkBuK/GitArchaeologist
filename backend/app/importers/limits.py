from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryImportLimits:
    max_commits: int = 100
    max_pull_requests: int = 10
    max_commits_per_pull_request: int = 50
    network_timeout_seconds: float = 15.0
    git_timeout_seconds: float = 60.0
    max_repository_bytes: int = 100 * 1024 * 1024
    max_git_log_bytes: int = 10 * 1024 * 1024
    temporary_directory: str | None = None

    def __post_init__(self) -> None:
        numeric_limits = {
            "max_commits": self.max_commits,
            "max_pull_requests": self.max_pull_requests,
            "max_commits_per_pull_request": self.max_commits_per_pull_request,
            "network_timeout_seconds": self.network_timeout_seconds,
            "git_timeout_seconds": self.git_timeout_seconds,
            "max_repository_bytes": self.max_repository_bytes,
            "max_git_log_bytes": self.max_git_log_bytes,
        }
        if any(value <= 0 for value in numeric_limits.values()):
            raise ValueError("Repository import limits must all be positive")

    @classmethod
    def from_environment(cls) -> RepositoryImportLimits:
        return cls(
            max_commits=int(os.getenv("GIT_IMPORT_MAX_COMMITS", "100")),
            max_pull_requests=int(os.getenv("GIT_IMPORT_MAX_PULL_REQUESTS", "10")),
            max_commits_per_pull_request=int(
                os.getenv("GIT_IMPORT_MAX_COMMITS_PER_PULL_REQUEST", "50")
            ),
            network_timeout_seconds=float(
                os.getenv("GIT_IMPORT_NETWORK_TIMEOUT_SECONDS", "15")
            ),
            git_timeout_seconds=float(os.getenv("GIT_IMPORT_TIMEOUT_SECONDS", "60")),
            max_repository_bytes=int(
                os.getenv("GIT_IMPORT_MAX_REPOSITORY_BYTES", str(100 * 1024 * 1024))
            ),
            max_git_log_bytes=int(
                os.getenv("GIT_IMPORT_MAX_LOG_BYTES", str(10 * 1024 * 1024))
            ),
            temporary_directory=os.getenv("GIT_IMPORT_TEMPORARY_DIRECTORY") or None,
        )
