from __future__ import annotations

from sqlalchemy.orm import Session

from app.importers.errors import RepositoryImportError
from app.importers.git import GitRepositoryAcquirer
from app.importers.github import (
    GitHubPublicRepositoryClient,
    normalize_github_repository_url,
)
from app.importers.limits import RepositoryImportLimits
from app.schemas.repository_import import (
    RepositoryImportLimitsRead,
    RepositoryImportResponse,
    RepositoryImportWarning,
)
from app.services.git_ingestion import GitIngestionService
from app.services.pull_request_ingestion import PullRequestIngestionService


class RepositoryImportService:
    def __init__(
        self,
        session: Session,
        *,
        limits: RepositoryImportLimits | None = None,
        git_acquirer: GitRepositoryAcquirer | None = None,
        github_client: GitHubPublicRepositoryClient | None = None,
    ) -> None:
        self.session = session
        self.limits = limits or RepositoryImportLimits.from_environment()
        self.git_acquirer = git_acquirer or GitRepositoryAcquirer(self.limits)
        self.github_client = github_client or GitHubPublicRepositoryClient(self.limits)

    def import_repository(self, repository_url: str) -> RepositoryImportResponse:
        repository = normalize_github_repository_url(repository_url)

        # External work completes before the first database query or flush.
        github = self.github_client.fetch(repository)
        git = self.git_acquirer.acquire(repository)
        warnings = list(github.warnings)
        if git.truncated:
            warnings.insert(
                0,
                RepositoryImportWarning(
                    code="git_history_truncated",
                    message=(
                        f"Git history import was limited to the newest "
                        f"{self.limits.max_commits} commits."
                    ),
                ),
            )

        try:
            git_ingestion = GitIngestionService(self.session).ingest(
                repository.repository_id,
                git.log_content,
                commit=False,
            )
            if git_ingestion.records_rejected > 0:
                raise RepositoryImportError(
                    code="git_output_invalid",
                    message="Generated Git history could not be normalized",
                    status_code=502,
                )
            pull_request_ingestion = PullRequestIngestionService(self.session).ingest(
                repository.repository_id,
                github.fixture_content,
                commit=False,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return RepositoryImportResponse(
            repositoryId=repository.repository_id,
            repositoryUrl=repository.canonical_url,
            selectedCommitSha=git.selected_commit_sha,
            gitIngestion=git_ingestion,
            pullRequestIngestion=pull_request_ingestion,
            warnings=warnings,
            limits=RepositoryImportLimitsRead(
                maxCommits=self.limits.max_commits,
                maxPullRequests=self.limits.max_pull_requests,
                maxCommitsPerPullRequest=self.limits.max_commits_per_pull_request,
                maxRepositoryBytes=self.limits.max_repository_bytes,
            ),
        )
