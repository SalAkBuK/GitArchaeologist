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
from app.schemas.pull_request import (
    PullRequestAuthorRead,
    PullRequestRead,
    UnresolvedCommitReferenceRead,
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


def _metadata_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Persisted timestamp metadata must be a string or null")
    return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def reconcile_snapshots(
        self,
        artifacts: list[ArtifactCreate],
        *,
        commit: bool = True,
    ) -> ReconciliationResult:
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
            if commit:
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

    def reconcile_pull_requests(
        self,
        artifacts: list[ArtifactCreate],
        *,
        commit: bool = True,
    ) -> ReconciliationResult:
        if not artifacts:
            return ReconciliationResult()
        if any(artifact.source_type != "github_pull_request" for artifact in artifacts):
            raise ValueError("Pull request reconciliation accepts only pull request artifacts")

        inserted = updated = unchanged = 0
        try:
            for artifact in artifacts:
                existing = self.session.scalar(
                    select(ArtifactModel).where(
                        ArtifactModel.repository_id == artifact.repository_id,
                        ArtifactModel.source_type == "github_pull_request",
                        ArtifactModel.external_id == artifact.external_id,
                    )
                )
                if existing is None:
                    self.session.add(self._to_model(artifact))
                    inserted += 1
                elif self._matches(existing, artifact):
                    unchanged += 1
                else:
                    self._apply(existing, artifact)
                    updated += 1

            self.session.flush()
            if commit:
                self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return ReconciliationResult(
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
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

    def list_linked_pull_request_models(
        self,
        *,
        repository_id: str,
        commit_sha: str,
    ) -> list[ArtifactModel]:
        models = [
            model
            for model in self.session.scalars(
                select(ArtifactModel).where(
                    ArtifactModel.repository_id == repository_id,
                    ArtifactModel.source_type == "github_pull_request",
                )
            )
            if commit_sha.lower() in model.artifact_metadata.get("commitShas", [])
        ]
        return sorted(
            models,
            key=lambda model: (int(model.artifact_metadata["number"]), model.id),
        )

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
        linked_pull_request_models = self.list_linked_pull_request_models(
            repository_id=repository_id,
            commit_sha=commit_sha,
        )
        linked_pull_requests = [
            self._to_pull_request_read(model) for model in linked_pull_request_models
        ]
        known_commit_shas = set(
            self.session.scalars(
                select(ArtifactModel.external_id).where(
                    ArtifactModel.repository_id == repository_id,
                    ArtifactModel.source_type == "git_commit",
                )
            )
        )
        unresolved_references = sorted(
            [
                UnresolvedCommitReferenceRead(
                    pullRequestId=model.id,
                    pullRequestNumber=int(model.artifact_metadata["number"]),
                    commitSha=referenced_sha,
                )
                for model in linked_pull_request_models
                for referenced_sha in model.artifact_metadata.get("commitShas", [])
                if referenced_sha not in known_commit_shas
            ],
            key=lambda item: (item.pull_request_number, item.commit_sha),
        )

        pull_request_edges = [
            EvidenceEdgeRead(
                id=self._edge_id(repository_id, "contains", model.id, commit.id),
                fromArtifactId=model.id,
                toArtifactId=commit.id,
                relationType="contains",
                label="Pull request contains commit",
                explanation=(
                    "The imported pull request fixture explicitly lists this full commit SHA."
                ),
                confidence=1.0,
                direct=True,
            )
            for model in linked_pull_request_models
        ]
        modified_file_edges = [
            EvidenceEdgeRead(
                id=self._edge_id(
                    repository_id,
                    "modifies",
                    commit.id,
                    file_artifact.id,
                ),
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
        edges = [*pull_request_edges, *modified_file_edges]
        evidence_status = [
            EvidenceStatusRead(
                label="Selected commit is verified from the uploaded Git log.",
                artifactIds=[commit.id],
            )
        ]
        if linked_pull_requests:
            evidence_status.append(
                EvidenceStatusRead(
                    label=(
                        "Linked pull requests are verified from explicit fixture commit SHAs."
                    ),
                    artifactIds=[pull_request.id for pull_request in linked_pull_requests],
                    edgeIds=[edge.id for edge in pull_request_edges],
                )
            )
        rationale_pull_requests = [
            pull_request
            for pull_request in linked_pull_requests
            if pull_request.body is not None and pull_request.body.strip()
        ]
        if rationale_pull_requests:
            evidence_status.append(
                EvidenceStatusRead(
                    label="Human rationale is available in a linked pull request description.",
                    artifactIds=[pull_request.id for pull_request in rationale_pull_requests],
                )
            )
        if modified_files:
            evidence_status.append(
                EvidenceStatusRead(
                    label="Modified files are verified from Git name-status records.",
                    artifactIds=[file_artifact.id for file_artifact in modified_files],
                    edgeIds=[edge.id for edge in modified_file_edges],
                )
            )

        warnings: list[MissingContextWarningRead] = []
        if not linked_pull_requests:
            warnings.append(
                MissingContextWarningRead(
                    code="missing_pull_request",
                    message=(
                        "No imported pull request explicitly references this commit."
                    ),
                )
            )
        pull_requests_without_body = [
            pull_request
            for pull_request in linked_pull_requests
            if pull_request.body is None or not pull_request.body.strip()
        ]
        if pull_requests_without_body:
            warnings.append(
                MissingContextWarningRead(
                    code="missing_pull_request_body",
                    message=(
                        "A linked pull request does not include a description explaining the change."
                    ),
                )
            )
        warnings.append(
            MissingContextWarningRead(
                code="missing_issue",
                message="No issue evidence has been imported for this investigation.",
            )
        )
        if not rationale_pull_requests:
            warnings.append(
                MissingContextWarningRead(
                    code="missing_human_rationale",
                    message=(
                        "No imported human rationale is available beyond the commit message."
                    ),
                )
            )
        if unresolved_references:
            warnings.append(
                MissingContextWarningRead(
                    code="unresolved_pull_request_commit",
                    message=(
                        "A linked pull request explicitly references a commit that has not been ingested."
                    ),
                )
            )
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
            linkedPullRequests=linked_pull_requests,
            modifiedFiles=modified_files,
            evidenceEdges=edges,
            evidenceStatus=evidence_status,
            missingContextWarnings=warnings,
            unresolvedCommitReferences=unresolved_references,
        )

    @staticmethod
    def _to_pull_request_read(model: ArtifactModel) -> PullRequestRead:
        metadata = model.artifact_metadata
        updated_at = _metadata_datetime(metadata.get("updatedAt"))
        if updated_at is None:
            raise ValueError("Persisted pull request is missing updatedAt")
        return PullRequestRead(
            id=model.id,
            repositoryId=model.repository_id,
            number=int(metadata["number"]),
            title=model.title,
            body=metadata.get("body"),
            state=metadata["state"],
            author=PullRequestAuthorRead(login=metadata["authorLogin"]),
            createdAt=_as_utc(model.occurred_at),
            updatedAt=updated_at,
            mergedAt=_metadata_datetime(metadata.get("mergedAt")),
            url=metadata.get("url"),
            baseBranch=metadata["baseBranch"],
            headBranch=metadata["headBranch"],
            commitShas=list(metadata.get("commitShas", [])),
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
                email=model.author_email or None,
                provider=(
                    "github" if model.source_type == "github_pull_request" else "git"
                ),
            ),
            occurredAt=_as_utc(model.occurred_at),
            ingestedAt=_as_utc(model.ingested_at),
            tags=list(model.tags),
            metadata=dict(model.artifact_metadata),
        )

    @staticmethod
    def _edge_id(
        repository_id: str,
        relation_type: str,
        from_artifact_id: str,
        to_artifact_id: str,
    ) -> str:
        identity = (
            f"{repository_id}:{relation_type}:{from_artifact_id}:{to_artifact_id}"
        )
        return str(uuid5(EDGE_ID_NAMESPACE, identity))
