from __future__ import annotations

from sqlalchemy.orm import Session

from app.parsers.pull_request_fixture import PullRequestFixtureParser
from app.repositories.artifacts import ArtifactRepository
from app.schemas.pull_request import PullRequestIngestionResult


class PullRequestIngestionService:
    def __init__(
        self,
        session: Session,
        parser: PullRequestFixtureParser | None = None,
    ) -> None:
        self.repository = ArtifactRepository(session)
        self.parser = parser or PullRequestFixtureParser()

    def ingest(self, repository_id: str, content: str) -> PullRequestIngestionResult:
        normalized_repository_id = repository_id.strip()
        parse_result = self.parser.parse(content, normalized_repository_id)
        reconciliation = self.repository.reconcile_pull_requests(parse_result.artifacts)

        known_commit_shas = {
            artifact.external_id
            for artifact in self.repository.list(
                repository_id=normalized_repository_id,
                source_type="git_commit",
            )
        }
        references = [
            commit_sha
            for artifact in parse_result.artifacts
            for commit_sha in artifact.metadata["commitShas"]
        ]
        resolved = sum(commit_sha in known_commit_shas for commit_sha in references)

        return PullRequestIngestionResult(
            repositoryId=normalized_repository_id,
            recordsReceived=parse_result.records_received,
            recordsInserted=reconciliation.inserted,
            recordsUpdated=reconciliation.updated,
            recordsSkippedAsDuplicates=reconciliation.unchanged,
            recordsRejected=parse_result.records_rejected,
            explicitCommitReferencesResolved=resolved,
            explicitCommitReferencesUnresolved=len(references) - resolved,
            validationErrors=parse_result.errors,
        )
