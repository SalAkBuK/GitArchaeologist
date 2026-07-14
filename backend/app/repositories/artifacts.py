from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.artifact import ArtifactModel
from app.schemas.artifact import ActorRef, ArtifactCreate, ArtifactRead


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_new(self, artifacts: list[ArtifactCreate]) -> tuple[int, int]:
        if not artifacts:
            return 0, 0

        repository_id = artifacts[0].repository_id
        source_type = artifacts[0].source_type
        external_ids = [artifact.external_id for artifact in artifacts]
        existing = set(
            self.session.scalars(
                select(ArtifactModel.external_id).where(
                    ArtifactModel.repository_id == repository_id,
                    ArtifactModel.source_type == source_type,
                    ArtifactModel.external_id.in_(external_ids),
                )
            )
        )
        candidates = [artifact for artifact in artifacts if artifact.external_id not in existing]

        inserted = 0
        if candidates:
            values = [
                {
                    "id": artifact.id,
                    "repository_id": artifact.repository_id,
                    "source_type": artifact.source_type,
                    "external_id": artifact.external_id,
                    "title": artifact.title,
                    "summary": artifact.summary,
                    "body": artifact.body,
                    "author_name": artifact.author_name,
                    "author_email": artifact.author_email,
                    "occurred_at": artifact.occurred_at,
                    "ingested_at": artifact.ingested_at,
                    "tags": artifact.tags,
                    "artifact_metadata": artifact.metadata,
                }
                for artifact in candidates
            ]
            statement = sqlite_insert(ArtifactModel).values(values).on_conflict_do_nothing(
                index_elements=["repository_id", "source_type", "external_id"]
            )
            execution = self.session.execute(statement)
            inserted = max(execution.rowcount or 0, 0)

        self.session.commit()
        skipped = len(artifacts) - inserted
        return inserted, skipped

    def list(
        self,
        *,
        repository_id: str | None = None,
        source_type: str | None = None,
    ) -> list[ArtifactRead]:
        statement = select(ArtifactModel)
        if repository_id is not None:
            statement = statement.where(ArtifactModel.repository_id == repository_id)
        if source_type is not None:
            statement = statement.where(ArtifactModel.source_type == source_type)
        statement = statement.order_by(ArtifactModel.occurred_at.desc(), ArtifactModel.id.asc())
        return [self._to_read_model(model) for model in self.session.scalars(statement)]

    @staticmethod
    def _to_read_model(model: ArtifactModel) -> ArtifactRead:
        return ArtifactRead(
            id=model.id,
            repositoryId=model.repository_id,
            sourceType=model.source_type,
            externalId=model.external_id,
            title=model.title,
            summary=model.summary,
            body=model.body,
            author=ActorRef(
                displayName=model.author_name,
                email=model.author_email,
            ),
            occurredAt=_as_utc(model.occurred_at),
            ingestedAt=_as_utc(model.ingested_at),
            tags=list(model.tags),
            metadata=dict(model.artifact_metadata),
        )
