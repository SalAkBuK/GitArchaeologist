from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.repositories.artifacts import ArtifactRepository
from app.schemas.artifact import ArtifactRead
from app.schemas.explanation import ExplanationRead
from app.schemas.investigation import CommitInvestigationRead, EvidenceEdgeRead


SUPPORTED_ARTIFACT_TYPES = {
    "git_commit",
    "github_pull_request",
    "modified_file",
}
IMPORT_WARNING_MESSAGES = {
    "git_history_truncated": (
        "The repository import reached its Git-history limit, so older commits may be absent."
    ),
    "pull_requests_truncated": (
        "The repository import reached its pull-request limit, so additional PR context may be absent."
    ),
    "pull_request_commits_truncated": (
        "At least one pull request reached its commit-reference limit."
    ),
}


class ExplanationArtifactNotFoundError(LookupError):
    pass


class ExplanationCrossRepositoryError(ValueError):
    pass


class ExplanationUnsupportedArtifactError(ValueError):
    pass


class ExplanationDisconnectedArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class BundleWarning:
    id: str
    code: str
    message: str
    artifact_ids: tuple[str, ...]


@dataclass(frozen=True)
class BundleUnresolvedReference:
    id: str
    pull_request_id: str
    pull_request_number: int
    commit_sha: str


@dataclass(frozen=True)
class EvidenceBundle:
    repository_id: str
    selected_artifact: ArtifactRead
    investigations: tuple[CommitInvestigationRead, ...]
    artifacts: tuple[ArtifactRead, ...]
    edges: tuple[EvidenceEdgeRead, ...]
    warnings: tuple[BundleWarning, ...]
    unresolved_references: tuple[BundleUnresolvedReference, ...]


def artifact_label(artifact: ArtifactRead) -> str:
    if artifact.source_type == "git_commit":
        return f"Commit {artifact.external_id[:7]}"
    if artifact.source_type == "github_pull_request":
        number = artifact.metadata.get("number", artifact.external_id)
        return f"PR #{number}"
    path = artifact.metadata.get("path")
    return str(path) if isinstance(path, str) else artifact.title


class EvidenceBundleBuilder:
    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def build(
        self,
        *,
        repository_id: str,
        selected_artifact_id: str,
        import_warning_codes: list[str],
    ) -> EvidenceBundle:
        identity = self.repository.get_identity(selected_artifact_id)
        if identity is None:
            raise ExplanationArtifactNotFoundError
        artifact_repository_id, artifact_source_type = identity
        if artifact_repository_id != repository_id:
            raise ExplanationCrossRepositoryError
        if artifact_source_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ExplanationUnsupportedArtifactError
        selected = self.repository.get_by_id_for_repository(
            repository_id=repository_id,
            artifact_id=selected_artifact_id,
        )
        if selected is None:
            raise ExplanationArtifactNotFoundError

        investigations = self._investigations_for_selected(selected)
        if selected.source_type == "modified_file" and not investigations:
            raise ExplanationDisconnectedArtifactError

        artifacts_by_id: dict[str, ArtifactRead] = {selected.id: selected}
        edges_by_id: dict[str, EvidenceEdgeRead] = {}
        warnings_by_id: dict[str, BundleWarning] = {}
        unresolved_by_id: dict[str, BundleUnresolvedReference] = {}

        for investigation in investigations:
            relevant_artifacts = [
                investigation.selected_commit,
                *investigation.modified_files,
            ]
            for artifact in relevant_artifacts:
                artifacts_by_id[artifact.id] = artifact
            for pull_request in investigation.linked_pull_requests:
                pull_request_artifact = self.repository.get_by_id_for_repository(
                    repository_id=repository_id,
                    artifact_id=pull_request.id,
                )
                if pull_request_artifact is not None:
                    artifacts_by_id[pull_request_artifact.id] = pull_request_artifact
            for edge in investigation.evidence_edges:
                if edge.direct:
                    edges_by_id[edge.id] = edge
            for index, warning in enumerate(investigation.missing_context_warnings):
                warning_id = (
                    f"warning:{investigation.selected_commit.id}:{warning.code}:{index}"
                )
                warnings_by_id[warning_id] = BundleWarning(
                    id=warning_id,
                    code=warning.code,
                    message=warning.message,
                    artifact_ids=(investigation.selected_commit.id,),
                )
            for reference in investigation.unresolved_commit_references:
                reference_id = (
                    f"unresolved:{reference.pull_request_id}:{reference.commit_sha}"
                )
                unresolved_by_id[reference_id] = BundleUnresolvedReference(
                    id=reference_id,
                    pull_request_id=reference.pull_request_id,
                    pull_request_number=reference.pull_request_number,
                    commit_sha=reference.commit_sha,
                )

        if selected.source_type == "github_pull_request":
            known_shas = {
                investigation.commit_sha for investigation in investigations
            }
            for value in selected.metadata.get("commitShas", []):
                if not isinstance(value, str) or value in known_shas:
                    continue
                reference_id = f"unresolved:{selected.id}:{value}"
                unresolved_by_id[reference_id] = BundleUnresolvedReference(
                    id=reference_id,
                    pull_request_id=selected.id,
                    pull_request_number=int(
                        selected.metadata.get("number", selected.external_id)
                    ),
                    commit_sha=value,
                )

        for code in import_warning_codes:
            warning_id = f"import-warning:{code}"
            warnings_by_id[warning_id] = BundleWarning(
                id=warning_id,
                code=code,
                message=IMPORT_WARNING_MESSAGES[code],
                artifact_ids=(selected.id,),
            )

        return EvidenceBundle(
            repository_id=repository_id,
            selected_artifact=selected,
            investigations=tuple(investigations),
            artifacts=tuple(artifacts_by_id.values()),
            edges=tuple(edges_by_id.values()),
            warnings=tuple(warnings_by_id.values()),
            unresolved_references=tuple(unresolved_by_id.values()),
        )

    def _investigations_for_selected(
        self,
        selected: ArtifactRead,
    ) -> list[CommitInvestigationRead]:
        if selected.source_type == "git_commit":
            investigation = self.repository.build_commit_investigation(
                repository_id=selected.repository_id,
                commit_sha=selected.external_id,
            )
            return [investigation] if investigation else []

        if selected.source_type == "modified_file":
            commit_sha = selected.metadata.get("commitHash")
            if not isinstance(commit_sha, str):
                return []
            investigation = self.repository.build_commit_investigation(
                repository_id=selected.repository_id,
                commit_sha=commit_sha,
            )
            if investigation is None or not any(
                edge.direct
                and edge.relation_type == "modifies"
                and edge.from_artifact_id == investigation.selected_commit.id
                and edge.to_artifact_id == selected.id
                for edge in investigation.evidence_edges
            ):
                return []
            return [investigation]

        investigations: list[CommitInvestigationRead] = []
        for commit_sha in selected.metadata.get("commitShas", []):
            if not isinstance(commit_sha, str):
                continue
            investigation = self.repository.build_commit_investigation(
                repository_id=selected.repository_id,
                commit_sha=commit_sha,
            )
            if investigation is not None and any(
                edge.direct
                and edge.relation_type == "contains"
                and edge.from_artifact_id == selected.id
                and edge.to_artifact_id == investigation.selected_commit.id
                for edge in investigation.evidence_edges
            ):
                investigations.append(investigation)
        return investigations


class ExplanationProvider(Protocol):
    def generate(self, bundle: EvidenceBundle, question: str) -> Mapping[str, Any]: ...


class DeterministicExplanationProvider:
    def generate(self, bundle: EvidenceBundle, question: str) -> Mapping[str, Any]:
        selected = bundle.selected_artifact
        labels = {artifact.id: artifact_label(artifact) for artifact in bundle.artifacts}
        context_label = labels[selected.id]
        supporting_artifact_ids = [selected.id]
        supporting_artifact_ids.extend(
            investigation.selected_commit.id
            for investigation in bundle.investigations
            if investigation.selected_commit.id != selected.id
        )
        supporting_artifact_ids = list(dict.fromkeys(supporting_artifact_ids))

        verified_facts: list[dict[str, Any]] = [
            {
                "text": self._selected_fact(selected, context_label),
                "supportingArtifactIds": [selected.id],
                "supportingEdgeIds": [],
            }
        ]
        for edge in bundle.edges:
            verified_facts.append(
                {
                    "text": (
                        f"{labels[edge.from_artifact_id]} {edge.relation_type} "
                        f"{labels[edge.to_artifact_id]}."
                    ),
                    "supportingArtifactIds": [
                        edge.from_artifact_id,
                        edge.to_artifact_id,
                    ],
                    "supportingEdgeIds": [edge.id],
                }
            )

        interpretation_artifact = self._interpretation_artifact(bundle)
        interpretations = [
            {
                "text": self._interpretation_text(interpretation_artifact),
                "supportingArtifactIds": [interpretation_artifact.id],
                "supportingEdgeIds": [],
            }
        ]

        missing_context = [
            {
                "id": warning.id,
                "code": warning.code,
                "message": warning.message,
                "supportingArtifactIds": list(warning.artifact_ids),
                "warningIds": [warning.id],
                "unresolvedReferenceIds": [],
            }
            for warning in bundle.warnings
        ]
        missing_context.extend(
            {
                "id": reference.id,
                "code": "unresolved_commit_reference",
                "message": (
                    f"PR #{reference.pull_request_number} references commit "
                    f"{reference.commit_sha}, which was not available in the imported history."
                ),
                "supportingArtifactIds": [reference.pull_request_id],
                "warningIds": [],
                "unresolvedReferenceIds": [reference.id],
            }
            for reference in bundle.unresolved_references
        )

        commit_count = len(bundle.investigations)
        pull_request_count = sum(
            artifact.source_type == "github_pull_request"
            for artifact in bundle.artifacts
        )
        file_count = sum(
            artifact.source_type == "modified_file" for artifact in bundle.artifacts
        )

        return {
            "generator": "deterministic_local",
            "question": question,
            "context": {
                "artifactId": selected.id,
                "artifactType": selected.source_type,
                "label": context_label,
            },
            "summary": {
                "text": (
                    f"Imported evidence for {context_label} connects {commit_count} commit(s), "
                    f"{pull_request_count} pull request(s), and {file_count} modified file(s)."
                ),
                "supportingArtifactIds": supporting_artifact_ids,
                "supportingEdgeIds": [edge.id for edge in bundle.edges],
            },
            "verifiedFacts": verified_facts,
            "interpretations": interpretations,
            "missingContext": missing_context,
            "supportingArtifacts": [
                {
                    "id": artifact.id,
                    "sourceType": artifact.source_type,
                    "label": labels[artifact.id],
                }
                for artifact in bundle.artifacts
            ],
            "supportingEdges": [
                {
                    "id": edge.id,
                    "relationType": edge.relation_type,
                    "fromArtifactId": edge.from_artifact_id,
                    "toArtifactId": edge.to_artifact_id,
                    "sourceLabel": labels[edge.from_artifact_id],
                    "targetLabel": labels[edge.to_artifact_id],
                }
                for edge in bundle.edges
            ],
            "confidence": self._confidence(bundle),
        }

    @staticmethod
    def _selected_fact(selected: ArtifactRead, label: str) -> str:
        if selected.source_type == "git_commit":
            return f'{label} has the imported subject "{selected.title}".'
        if selected.source_type == "github_pull_request":
            return f'{label} has the imported title "{selected.title}".'
        return f"{label} is present as imported modified-file evidence."

    @staticmethod
    def _interpretation_artifact(bundle: EvidenceBundle) -> ArtifactRead:
        pull_request_with_body = next(
            (
                artifact
                for artifact in bundle.artifacts
                if artifact.source_type == "github_pull_request"
                and artifact.body.strip()
            ),
            None,
        )
        if pull_request_with_body is not None:
            return pull_request_with_body
        commit = next(
            (
                artifact
                for artifact in bundle.artifacts
                if artifact.source_type == "git_commit"
            ),
            None,
        )
        return commit or bundle.selected_artifact

    @staticmethod
    def _interpretation_text(artifact: ArtifactRead) -> str:
        rationale = artifact.body.strip() or artifact.title.strip()
        first_line = rationale.splitlines()[0].strip()
        if len(first_line) > 240:
            first_line = f"{first_line[:237]}..."
        source = (
            "pull request description"
            if artifact.source_type == "github_pull_request" and artifact.body.strip()
            else "commit message"
            if artifact.source_type == "git_commit"
            else "selected artifact title"
        )
        return f'The imported {source} suggests the change was intended to address: "{first_line}".'

    @staticmethod
    def _confidence(bundle: EvidenceBundle) -> str:
        has_rationale = any(
            artifact.source_type == "github_pull_request" and artifact.body.strip()
            for artifact in bundle.artifacts
        )
        has_verified_relationship = bool(bundle.edges)
        completeness_gap_codes = {
            warning.code
            for warning in bundle.warnings
            if warning.code != "missing_issue"
        }
        if has_rationale and has_verified_relationship and not completeness_gap_codes:
            return "medium" if bundle.warnings else "high"
        return "low"


class ExplanationService:
    def __init__(
        self,
        repository: ArtifactRepository,
        provider: ExplanationProvider | None = None,
    ) -> None:
        self.bundle_builder = EvidenceBundleBuilder(repository)
        self.provider = provider or DeterministicExplanationProvider()

    def explain(
        self,
        *,
        repository_id: str,
        selected_artifact_id: str,
        question: str,
        import_warning_codes: list[str],
    ) -> ExplanationRead:
        bundle = self.bundle_builder.build(
            repository_id=repository_id,
            selected_artifact_id=selected_artifact_id,
            import_warning_codes=import_warning_codes,
        )
        raw_explanation = self.provider.generate(bundle, question)
        explanation = ExplanationRead.model_validate(raw_explanation)
        self._validate_support(explanation, bundle)
        return explanation

    @staticmethod
    def _validate_support(
        explanation: ExplanationRead,
        bundle: EvidenceBundle,
    ) -> None:
        artifact_ids = {artifact.id for artifact in bundle.artifacts}
        edge_ids = {edge.id for edge in bundle.edges}
        warning_ids = {warning.id for warning in bundle.warnings}
        unresolved_ids = {
            reference.id for reference in bundle.unresolved_references
        }
        statements = [
            explanation.summary,
            *explanation.verified_facts,
            *explanation.interpretations,
        ]
        if any(
            not set(statement.supporting_artifact_ids).issubset(artifact_ids)
            or not set(statement.supporting_edge_ids).issubset(edge_ids)
            for statement in statements
        ):
            raise ValueError("Explanation cites evidence outside the bundle")
        if any(
            not set(item.supporting_artifact_ids).issubset(artifact_ids)
            or not set(item.warning_ids).issubset(warning_ids)
            or not set(item.unresolved_reference_ids).issubset(unresolved_ids)
            for item in explanation.missing_context
        ):
            raise ValueError("Explanation cites missing context outside the bundle")
