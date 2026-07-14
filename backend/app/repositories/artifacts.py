from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import select
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


@dataclass(frozen=True)
class ReconciliationResult:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def reconcile_snapshots(self, artifacts: list[ArtifactCreate]) -> ReconciliationResult:
        if not artifacts:
            return ReconciliationResult()

        commits: dict[tuple[str, str], ArtifactCreate] = {}
        files_by_commit: dict[tuple[str, str], list[ArtifactCreate]] = {}
        duplicate_inputs = 0
        for artifact in artifacts:
            if artifact.source_type == "git_commit":
                key = (artifact.repository_id, artifact.external_id.lower())
                duplicate_inputs += int(key in commits)
                commits[key] = artifact
                continue
            commit_hash = artifact.metadata.get("commitHash")
            if not isinstance(commit_hash, str):
                raise ValueError("Modified-file artifact is missing commitHash metadata")
            files_by_commit.setdefault((artifact.repository_id, commit_hash.lower()), []).append(
                artifact
            )

        orphaned = set(files_by_commit) - set(commits)
        if orphaned:
            raise ValueError("Modified-file artifacts must belong to an incoming commit snapshot")

        inserted = updated = deleted = unchanged = 0
        try:
            for key, commit in commits.items():
                repository_id, commit_hash = key
                existing_commit = self.session.scalar(
                    select(ArtifactModel).where(
                        ArtifactModel.repository_id == repository_id,
                        ArtifactModel.source_type == "git_commit",
                        ArtifactModel.external_id == commit_hash,
                    )
                )
                if existing_commit is None:
                    self.session.add(self._to_model(commit))
                    inserted += 1
                elif self._matches(existing_commit, commit):
                    unchanged += 1
                else:
                    self._apply(existing_commit, commit)
                    updated += 1

                incoming_file_list = files_by_commit.get(key, [])
                incoming_files: dict[str, ArtifactCreate] = {}
                for file_artifact in incoming_file_list:
                    duplicate_inputs += int(file_artifact.external_id in incoming_files)
                    incoming_files[file_artifact.external_id] = file_artifact

                existing_files = {
                    model.external_id: model
                    for model in self.session.scalars(
                        select(ArtifactModel).where(
                            ArtifactModel.repository_id == repository_id,
                            ArtifactModel.source_type == "modified_file",
                        )
                    )
                    if model.artifact_metadata.get("commitHash") == commit_hash
                }

                for external_id, file_artifact in incoming_files.items():
                    existing_file = existing_files.get(external_id)
                    if existing_file is None:
                        self.session.add(self._to_model(file_artifact))
                        inserted += 1
                    elif self._matches(existing_file, file_artifact):
                        unchanged += 1
                    else:
                        self._apply(existing_file, file_artifact)
                        updated += 1

                for external_id, existing_file in existing_files.items():
                    if external_id not in incoming_files:
                        self.session.delete(existing_file)
                        deleted += 1

            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return ReconciliationResult(
            inserted=inserted,
            updated=updated,
            deleted=deleted,
            unchanged=unchanged + duplicate_inputs,
        )

    @staticmethod
    def _to_model(artifact: ArtifactCreate) -> ArtifactModel:
        return ArtifactModel(
            id=artifact.id,
            repository_id=artifact.repository_id,
            source_type=artifact.source_type,
            external_id=artifact.external_id,
            title=artifact.title,
            summary=artifact.summary,
            body=artifact.body,
            author_name=artifact.author_name,
            author_email=artifact.author_email,
            occurred_at=artifact.occurred_at,
            ingested_at=artifact.ingested_at,
            tags=list(artifact.tags),
            artifact_metadata=dict(artifact.metadata),
        )

    @staticmethod
    def _matches(model: ArtifactModel, artifact: ArtifactCreate) -> bool:
        return (
            model.title == artifact.title
            and model.summary == artifact.summary
            and model.body == artifact.body
            and model.author_name == artifact.author_name
            and model.author_email == artifact.author_email
            and _as_utc(model.occurred_at) == _as_utc(artifact.occurred_at)
            and list(model.tags) == artifact.tags
            and dict(model.artifact_metadata) == artifact.metadata
        )

    @staticmethod
    def _apply(model: ArtifactModel, artifact: ArtifactCreate) -> None:
        model.title = artifact.title
        model.summary = artifact.summary
        model.body = artifact.body
        model.author_name = artifact.author_name
        model.author_email = artifact.author_email
        model.occurred_at = artifact.occurred_at
        model.ingested_at = artifact.ingested_at
        model.tags = list(artifact.tags)
        model.artifact_metadata = dict(artifact.metadata)

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
