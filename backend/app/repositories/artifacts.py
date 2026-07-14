from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.artifact import ArtifactModel
from app.schemas.artifact import ActorRef, ArtifactCreate, ArtifactRead
from app.schemas.investigation import (
    CommitInvestigationRead,
    EvidenceEdgeRead,
    EvidenceStatusRead,
    MissingContextWarningRead,
)


EDGE_ID_NAMESPACE = UUID("2d3d740c-3c6f-4430-b602-0c098a1a0acf")


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

        keys = {
            (artifact.repository_id, artifact.source_type, artifact.external_id)
            for artifact in artifacts
        }
        existing = set(
            (
                model.repository_id,
                model.source_type,
                model.external_id,
            )
            for model in self.session.scalars(select(ArtifactModel))
            if (model.repository_id, model.source_type, model.external_id) in keys
        )
        candidates = [
            artifact
            for artifact in artifacts
            if (artifact.repository_id, artifact.source_type, artifact.external_id) not in existing
        ]

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

    def get_commit(self, *, repository_id: str, commit_sha: str) -> ArtifactRead | None:
        statement = select(ArtifactModel).where(
            ArtifactModel.repository_id == repository_id,
            ArtifactModel.source_type == "git_commit",
            ArtifactModel.external_id == commit_sha.lower(),
        )
        model = self.session.scalar(statement)
        return self._to_read_model(model) if model else None

    def list_modified_files_for_commit(
        self,
        *,
        repository_id: str,
        commit_sha: str,
    ) -> list[ArtifactRead]:
        statement = (
            select(ArtifactModel)
            .where(
                ArtifactModel.repository_id == repository_id,
                ArtifactModel.source_type == "modified_file",
            )
            .order_by(ArtifactModel.title.asc(), ArtifactModel.id.asc())
        )
        files = [
            self._to_read_model(model)
            for model in self.session.scalars(statement)
            if model.artifact_metadata.get("commitHash") == commit_sha.lower()
        ]
        return files

    def build_commit_investigation(
        self,
        *,
        repository_id: str,
        commit_sha: str,
    ) -> CommitInvestigationRead | None:
        commit = self.get_commit(repository_id=repository_id, commit_sha=commit_sha)
        if commit is None:
            return None

        modified_files = self.list_modified_files_for_commit(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        edges = [
            EvidenceEdgeRead(
                id=self._edge_id(repository_id, commit.id, file_artifact.id),
                fromArtifactId=commit.id,
                toArtifactId=file_artifact.id,
                relationType="modifies",
                label="Commit modifies file",
                explanation=(
                    "This edge is direct evidence from the parsed Git name-status record."
                ),
                confidence=1.0,
                direct=True,
            )
            for file_artifact in modified_files
        ]
        evidence_status = [
            EvidenceStatusRead(
                label="Selected commit is verified from the uploaded Git log.",
                artifactIds=[commit.id],
            )
        ]
        if modified_files:
            evidence_status.append(
                EvidenceStatusRead(
                    label="Modified files are verified from Git name-status records.",
                    artifactIds=[file_artifact.id for file_artifact in modified_files],
                    edgeIds=[edge.id for edge in edges],
                )
            )

        warnings = [
            MissingContextWarningRead(
                code="missing_pull_request",
                message="No linked pull request has been ingested for this commit.",
            ),
            MissingContextWarningRead(
                code="missing_issue",
                message="No linked issue has been ingested for this commit.",
            ),
            MissingContextWarningRead(
                code="missing_human_rationale",
                message="No human rationale is available beyond the commit message.",
            ),
        ]
        if not modified_files:
            warnings.append(
                MissingContextWarningRead(
                    code="missing_modified_files",
                    message="The uploaded Git-log input did not contain modified-file records for this commit.",
                )
            )

        return CommitInvestigationRead(
            repositoryId=repository_id,
            commitSha=commit_sha.lower(),
            selectedCommit=commit,
            modifiedFiles=modified_files,
            evidenceEdges=edges,
            evidenceStatus=evidence_status,
            missingContextWarnings=warnings,
        )

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

    @staticmethod
    def _edge_id(repository_id: str, commit_artifact_id: str, file_artifact_id: str) -> str:
        identity = f"{repository_id}:modifies:{commit_artifact_id}:{file_artifact_id}"
        return str(uuid5(EDGE_ID_NAMESPACE, identity))
