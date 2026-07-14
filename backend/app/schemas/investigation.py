from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.artifact import ArtifactRead


class EvidenceEdgeRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_artifact_id: str = Field(alias="fromArtifactId")
    to_artifact_id: str = Field(alias="toArtifactId")
    relation_type: Literal["modifies"] = Field(alias="relationType")
    label: str
    explanation: str
    confidence: float
    direct: bool = True


class EvidenceStatusRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["verified_evidence", "missing_context"] = "verified_evidence"
    label: str
    artifact_ids: list[str] = Field(default_factory=list, alias="artifactIds")
    edge_ids: list[str] = Field(default_factory=list, alias="edgeIds")


class MissingContextWarningRead(BaseModel):
    code: Literal[
        "missing_pull_request",
        "missing_issue",
        "missing_human_rationale",
        "missing_modified_files",
    ]
    message: str


class CommitInvestigationRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repository_id: str = Field(alias="repositoryId")
    commit_sha: str = Field(alias="commitSha")
    selected_commit: ArtifactRead = Field(alias="selectedCommit")
    modified_files: list[ArtifactRead] = Field(alias="modifiedFiles")
    evidence_edges: list[EvidenceEdgeRead] = Field(alias="evidenceEdges")
    evidence_status: list[EvidenceStatusRead] = Field(alias="evidenceStatus")
    missing_context_warnings: list[MissingContextWarningRead] = Field(
        alias="missingContextWarnings"
    )
