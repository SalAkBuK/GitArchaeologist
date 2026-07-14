from __future__ import annotations

from sqlalchemy.orm import Session

from app.parsers.git_log import GitLogParser
from app.repositories.artifacts import ArtifactRepository
from app.schemas.ingestion import IngestionResult


class GitIngestionService:
    def __init__(self, session: Session, parser: GitLogParser | None = None) -> None:
        self.repository = ArtifactRepository(session)
        self.parser = parser or GitLogParser()

    def ingest(self, repository_id: str, content: str) -> IngestionResult:
        normalized_repository_id = repository_id.strip()
        parse_result = self.parser.parse(content, normalized_repository_id)
        reconciliation = self.repository.reconcile_snapshots(parse_result.artifacts)
        return IngestionResult(
            repositoryId=normalized_repository_id,
            recordsParsed=len(parse_result.artifacts),
            recordsInserted=reconciliation.inserted,
            recordsUpdated=reconciliation.updated,
            recordsDeleted=reconciliation.deleted,
            recordsSkippedAsDuplicates=reconciliation.unchanged,
            recordsRejected=len(parse_result.errors),
            validationErrors=parse_result.errors,
        )
