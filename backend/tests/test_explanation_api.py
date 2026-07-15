from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.artifact import ArtifactModel
from app.repositories.artifacts import ArtifactRepository
from app.services.explanation import EvidenceBundleBuilder, ExplanationService
from tests.test_api import upload, upload_with_files
from tests.test_git_parser import HASH_ONE, commit_record
from tests.test_pull_request_ingestion_api import (
    fixture,
    pull_request,
    upload_pull_requests,
)


HASH_UNRESOLVED = "b" * 40
HASH_UNRELATED = "c" * 40


def post_explanation(
    client: TestClient,
    artifact_id: str,
    *,
    repository_id: str = "acme/platform",
    question: str = "Why was this changed?",
    warning_codes: list[str] | None = None,
):
    return client.post(
        "/api/explanations",
        json={
            "repositoryId": repository_id,
            "selectedArtifactId": artifact_id,
            "question": question,
            "importWarningCodes": warning_codes or [],
        },
    )


def ingest_grounded_fixture(client: TestClient) -> dict[str, Any]:
    assert upload_with_files(client).status_code == 200
    assert upload_pull_requests(
        client,
        "acme/platform",
        fixture(
            "acme/platform",
            [
                pull_request(
                    body="Add deterministic cache behavior for repeated repository reads.",
                    commit_shas=[HASH_ONE, HASH_UNRESOLVED],
                )
            ],
        ),
    ).status_code == 200
    assert client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/platform"},
        files={
            "file": (
                "unrelated.txt",
                commit_record(HASH_UNRELATED, message="Unrelated cleanup"),
                "text/plain",
            )
        },
    ).status_code == 200
    return client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    ).json()


def test_explanation_bundle_contains_only_direct_repository_scoped_evidence(
    client: TestClient,
) -> None:
    investigation = ingest_grounded_fixture(client)
    database = client.app.state.database
    with database.session_factory() as session:
        bundle = EvidenceBundleBuilder(ArtifactRepository(session)).build(
            repository_id="acme/platform",
            selected_artifact_id=investigation["selectedCommit"]["id"],
            import_warning_codes=["git_history_truncated"],
        )

    artifact_ids = {artifact.id for artifact in bundle.artifacts}
    expected_ids = {
        investigation["selectedCommit"]["id"],
        investigation["linkedPullRequests"][0]["id"],
        *(artifact["id"] for artifact in investigation["modifiedFiles"]),
    }
    assert artifact_ids == expected_ids
    assert HASH_UNRELATED not in {artifact.external_id for artifact in bundle.artifacts}
    assert {artifact.repository_id for artifact in bundle.artifacts} == {"acme/platform"}
    assert {
        (edge.relation_type, edge.from_artifact_id, edge.to_artifact_id)
        for edge in bundle.edges
    } == {
        (
            edge["relationType"],
            edge["fromArtifactId"],
            edge["toArtifactId"],
        )
        for edge in investigation["evidenceEdges"]
    }
    assert any(warning.id == "import-warning:git_history_truncated" for warning in bundle.warnings)
    assert bundle.unresolved_references[0].commit_sha == HASH_UNRESOLVED


def test_deterministic_explanation_separates_facts_interpretation_and_gaps(
    client: TestClient,
) -> None:
    investigation = ingest_grounded_fixture(client)
    artifact_id = investigation["selectedCommit"]["id"]

    first = post_explanation(
        client,
        artifact_id,
        warning_codes=["pull_requests_truncated"],
    )
    second = post_explanation(
        client,
        artifact_id,
        warning_codes=["pull_requests_truncated"],
    )

    assert first.status_code == 200
    assert first.json() == second.json()
    explanation = first.json()
    assert explanation["generator"] == "deterministic_local"
    assert explanation["question"] == "Why was this changed?"
    assert explanation["context"]["artifactId"] == artifact_id
    assert explanation["verifiedFacts"]
    assert explanation["interpretations"]
    assert all(
        fact["supportingArtifactIds"] or fact["supportingEdgeIds"]
        for fact in explanation["verifiedFacts"]
    )
    assert all(
        interpretation["supportingArtifactIds"]
        or interpretation["supportingEdgeIds"]
        for interpretation in explanation["interpretations"]
    )
    assert {
        "missing_issue",
        "unresolved_pull_request_commit",
        "unresolved_commit_reference",
        "pull_requests_truncated",
    }.issubset({item["code"] for item in explanation["missingContext"]})
    assert {
        (edge["relationType"], edge["fromArtifactId"], edge["toArtifactId"])
        for edge in explanation["supportingEdges"]
    } == {
        (edge["relationType"], edge["fromArtifactId"], edge["toArtifactId"])
        for edge in investigation["evidenceEdges"]
    }


def test_commit_pull_request_and_file_are_supported_question_contexts(
    client: TestClient,
) -> None:
    investigation = ingest_grounded_fixture(client)
    contexts = [
        (investigation["selectedCommit"]["id"], "git_commit"),
        (investigation["linkedPullRequests"][0]["id"], "github_pull_request"),
        (investigation["modifiedFiles"][0]["id"], "modified_file"),
    ]

    for artifact_id, artifact_type in contexts:
        response = post_explanation(client, artifact_id)
        assert response.status_code == 200
        assert response.json()["context"] == {
            "artifactId": artifact_id,
            "artifactType": artifact_type,
            "label": response.json()["context"]["label"],
        }


def test_explanation_rejects_bad_questions_and_repository_scope_violations(
    client: TestClient,
) -> None:
    assert upload(client, "acme/other").status_code == 200
    other_artifact = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/other", "sourceType": "git_commit"},
    ).json()[0]

    cross_repository = post_explanation(client, other_artifact["id"])
    missing = post_explanation(client, "00000000-0000-0000-0000-000000000000")
    blank = post_explanation(client, other_artifact["id"], repository_id="acme/other", question="   ")
    overlong = post_explanation(
        client,
        other_artifact["id"],
        repository_id="acme/other",
        question="x" * 501,
    )

    assert cross_repository.status_code == 409
    assert cross_repository.json()["detail"]["code"] == "explanation_repository_mismatch"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "explanation_artifact_not_found"
    assert blank.status_code == 422
    assert overlong.status_code == 422


def test_unsupported_artifact_type_has_stable_sanitized_error(client: TestClient) -> None:
    database = client.app.state.database
    with database.session_factory() as session:
        session.add(
            ArtifactModel(
                id="unsupported-artifact",
                repository_id="acme/platform",
                source_type="deployment",
                external_id="deploy-1",
                title="Production deploy",
                summary="",
                body="",
                author_name="system",
                author_email="",
                occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
                ingested_at=datetime(2026, 7, 15, tzinfo=UTC),
                tags=[],
                artifact_metadata={},
            )
        )
        session.commit()

    response = post_explanation(client, "unsupported-artifact")

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "unsupported_explanation_artifact",
        "message": "Selected artifact type cannot be used for explanations",
    }


def test_malformed_provider_output_is_rejected(client: TestClient) -> None:
    investigation = ingest_grounded_fixture(client)

    class MalformedProvider:
        def generate(self, bundle: object, question: str) -> dict[str, object]:
            return {"generator": "deterministic_local", "question": question}

    database = client.app.state.database
    with database.session_factory() as session:
        service = ExplanationService(
            ArtifactRepository(session),
            provider=MalformedProvider(),
        )
        with pytest.raises(ValidationError):
            service.explain(
                repository_id="acme/platform",
                selected_artifact_id=investigation["selectedCommit"]["id"],
                question="Why?",
                import_warning_codes=[],
            )
