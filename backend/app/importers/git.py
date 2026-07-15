from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.importers.errors import RepositoryImportError
from app.importers.github import GitHubRepositoryReference
from app.importers.limits import RepositoryImportLimits
from app.parsers.git_log import COMMIT_HEADER_RE, FULL_HASH_RE


RunSubprocess = Callable[..., subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class GitHistoryAcquisition:
    log_content: str
    selected_commit_sha: str
    truncated: bool


class GitRepositoryAcquirer:
    def __init__(
        self,
        limits: RepositoryImportLimits,
        *,
        runner: RunSubprocess = subprocess.run,
        git_executable: str | None = None,
    ) -> None:
        self.limits = limits
        self.runner = runner
        self.git_executable = git_executable

    def acquire(self, repository: GitHubRepositoryReference) -> GitHistoryAcquisition:
        git = self.git_executable or shutil.which("git")
        if git is None:
            raise RepositoryImportError(
                code="git_unavailable",
                message="Git executable is unavailable",
                status_code=500,
            )

        with tempfile.TemporaryDirectory(dir=self.limits.temporary_directory) as temporary:
            root = Path(temporary)
            clone_path = root / "repository"
            hooks_path = root / "disabled-hooks"
            hooks_path.mkdir()
            global_config = root / "empty-gitconfig"
            global_config.write_text("", encoding="utf-8")
            environment = self._git_environment(global_config)
            common = [
                git,
                "-c",
                "credential.helper=",
                "-c",
                "credential.interactive=never",
                "-c",
                "http.extraHeader=",
                "-c",
                f"core.hooksPath={hooks_path}",
            ]
            self._run(
                [
                    *common,
                    "clone",
                    "--depth",
                    str(self.limits.max_commits + 1),
                    "--single-branch",
                    "--no-tags",
                    "--filter=blob:none",
                    "--no-checkout",
                    repository.canonical_url,
                    str(clone_path),
                ],
                environment,
            )
            if self._directory_size(clone_path) > self.limits.max_repository_bytes:
                raise RepositoryImportError(
                    code="repository_too_large",
                    message="Repository exceeds the configured import size limit",
                    status_code=413,
                )

            hashes_result = self._run(
                [
                    *common,
                    "-C",
                    str(clone_path),
                    "rev-list",
                    f"--max-count={self.limits.max_commits + 1}",
                    "HEAD",
                ],
                environment,
            )
            hashes = self._decode(hashes_result.stdout).splitlines()
            if not hashes or not all(FULL_HASH_RE.fullmatch(item.strip()) for item in hashes):
                raise RepositoryImportError(
                    code="empty_repository",
                    message="Repository does not contain valid importable commits",
                    status_code=422,
                )
            log_result = self._run(
                [
                    *common,
                    "-C",
                    str(clone_path),
                    "-c",
                    "core.quotepath=false",
                    "log",
                    f"--max-count={self.limits.max_commits}",
                    "--date=iso-strict",
                    "--name-status",
                    "--diff-filter=AMDR",
                    "--pretty=format:commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n",
                ],
                environment,
            )
            if len(log_result.stdout) > self.limits.max_git_log_bytes:
                raise RepositoryImportError(
                    code="repository_too_large",
                    message="Generated Git history exceeds the configured import size limit",
                    status_code=413,
                )
            if self._directory_size(clone_path) > self.limits.max_repository_bytes:
                raise RepositoryImportError(
                    code="repository_too_large",
                    message="Repository exceeds the configured import size limit",
                    status_code=413,
                )
            log_content = self._decode(log_result.stdout)
            first_imported_commit = COMMIT_HEADER_RE.search(log_content)
            if first_imported_commit is None:
                raise RepositoryImportError(
                    code="empty_repository",
                    message="Repository does not contain valid importable commits",
                    status_code=422,
                )
            return GitHistoryAcquisition(
                log_content=log_content,
                selected_commit_sha=first_imported_commit.group(1).strip().lower(),
                truncated=len(hashes) > self.limits.max_commits,
            )

    def _run(
        self,
        arguments: list[str],
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return self.runner(
                arguments,
                check=True,
                capture_output=True,
                timeout=self.limits.git_timeout_seconds,
                env=environment,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryImportError(
                code="git_timeout",
                message="Git repository import timed out",
                status_code=504,
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RepositoryImportError(
                code="git_command_failed",
                message="Git could not import the public repository",
                status_code=502,
            ) from exc

    @staticmethod
    def _decode(value: bytes) -> str:
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryImportError(
                code="git_command_failed",
                message="Git returned output that was not valid UTF-8",
                status_code=502,
            ) from exc

    @staticmethod
    def _directory_size(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    @staticmethod
    def _git_environment(global_config: Path) -> dict[str, str]:
        environment = dict(os.environ)
        unsafe_exact = {
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_CONFIG_COUNT",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
        }
        for key in list(environment):
            if key in unsafe_exact or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
                environment.pop(key)
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(global_config),
            }
        )
        return environment
