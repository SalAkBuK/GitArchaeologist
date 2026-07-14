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
        inserted, skipped = self.repository.insert_new(parse_result.artifacts)
        return IngestionResult(
            repositoryId=normalized_repository_id,
            recordsParsed=len(parse_result.artifacts),
            recordsInserted=inserted,
            recordsSkippedAsDuplicates=skipped,
            recordsRejected=len(parse_result.errors),
            validationErrors=parse_result.errors,
        )
