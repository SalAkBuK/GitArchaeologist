from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.repository_import import ImportWarningCode


ExplanationConfidence = Literal["high", "medium", "low"]
ExplanationArtifactType = Literal[
    "git_commit",
    "github_pull_request",
    "modified_file",
]


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repository_id: str = Field(alias="repositoryId", min_length=1, max_length=255)
    selected_artifact_id: str = Field(
        alias="selectedArtifactId",
        min_length=1,
        max_length=100,
    )
    question: str = Field(min_length=1, max_length=500)
    import_warning_codes: list[ImportWarningCode] = Field(
        default_factory=list,
        alias="importWarningCodes",
        max_length=3,
    )

    @field_validator("repository_id", "selected_artifact_id", "question")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("import_warning_codes")
    @classmethod
    def deduplicate_warning_codes(
        cls,
        values: list[ImportWarningCode],
    ) -> list[ImportWarningCode]:
        return list(dict.fromkeys(values))


class ExplanationContextRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    artifact_id: str = Field(alias="artifactId")
    artifact_type: ExplanationArtifactType = Field(alias="artifactType")
    label: str


class CitedStatementRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    text: str = Field(min_length=1)
    supporting_artifact_ids: list[str] = Field(
        default_factory=list,
        alias="supportingArtifactIds",
    )
    supporting_edge_ids: list[str] = Field(
        default_factory=list,
        alias="supportingEdgeIds",
    )

    @model_validator(mode="after")
    def require_support(self) -> CitedStatementRead:
        if not self.supporting_artifact_ids and not self.supporting_edge_ids:
            raise ValueError("cited statements require supporting evidence")
        return self


class MissingContextItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    code: str
    message: str
    supporting_artifact_ids: list[str] = Field(
        default_factory=list,
        alias="supportingArtifactIds",
    )
    warning_ids: list[str] = Field(default_factory=list, alias="warningIds")
    unresolved_reference_ids: list[str] = Field(
        default_factory=list,
        alias="unresolvedReferenceIds",
    )


class SupportingArtifactRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    source_type: ExplanationArtifactType = Field(alias="sourceType")
    label: str


class SupportingEdgeRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    relation_type: Literal["contains", "modifies"] = Field(alias="relationType")
    from_artifact_id: str = Field(alias="fromArtifactId")
    to_artifact_id: str = Field(alias="toArtifactId")
    source_label: str = Field(alias="sourceLabel")
    target_label: str = Field(alias="targetLabel")


class ExplanationRead(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    generator: Literal["deterministic_local"]
    question: str
    context: ExplanationContextRead
    summary: CitedStatementRead
    verified_facts: list[CitedStatementRead] = Field(alias="verifiedFacts")
    interpretations: list[CitedStatementRead]
    missing_context: list[MissingContextItemRead] = Field(alias="missingContext")
    supporting_artifacts: list[SupportingArtifactRead] = Field(
        alias="supportingArtifacts"
    )
    supporting_edges: list[SupportingEdgeRead] = Field(alias="supportingEdges")
    confidence: ExplanationConfidence
