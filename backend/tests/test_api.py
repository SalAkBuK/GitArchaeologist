from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_git_parser import HASH_ONE, commit_record


def upload(client: TestClient, repository_id: str = "acme/platform"):
    return client.post(
        "/api/ingestions/git",
        data={"repositoryId": repository_id},
        files={"file": ("git_log.txt", commit_record(HASH_ONE), "text/plain")},
    )


def upload_with_files(client: TestClient, repository_id: str = "acme/platform"):
    return client.post(
        "/api/ingestions/git",
        data={"repositoryId": repository_id},
        files={
            "file": (
                "git_log.txt",
                commit_record(
                    HASH_ONE,
                    files=[
                        "A\tbackend/app/cache.py",
                        "M\tbackend/app/main.py",
                    ],
                ),
                "text/plain",
            )
        },
    )


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingestion_request_validation(client: TestClient) -> None:
    missing_repository = client.post(
        "/api/ingestions/git",
        files={"file": ("git_log.txt", commit_record(), "text/plain")},
    )
    blank_repository = upload(client, "   ")
    wrong_extension = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/platform"},
        files={"file": ("git_log.json", commit_record(), "application/json")},
    )

    assert missing_repository.status_code == 422
    assert blank_repository.status_code == 422
    assert wrong_extension.status_code == 422


def test_ingests_and_retrieves_normalized_artifact(client: TestClient) -> None:
    ingestion = upload(client)

    assert ingestion.status_code == 200
    assert ingestion.json() == {
        "repositoryId": "acme/platform",
        "recordsParsed": 1,
        "recordsInserted": 1,
        "recordsSkippedAsDuplicates": 0,
        "recordsRejected": 0,
        "validationErrors": [],
    }

    response = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/platform", "sourceType": "git_commit"},
    )

    assert response.status_code == 200
    artifacts = response.json()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["repositoryId"] == "acme/platform"
    assert artifact["sourceType"] == "git_commit"
    assert artifact["externalId"] == HASH_ONE
    assert artifact["author"] == {
        "displayName": "Ada Lovelace",
        "email": "ada@example.com",
        "provider": "git",
    }
    assert artifact["occurredAt"] == "2026-07-14T05:30:00Z"
    assert artifact["confidence"] == 1.0


def test_ingests_and_retrieves_modified_file_artifacts(client: TestClient) -> None:
    ingestion = upload_with_files(client)

    assert ingestion.status_code == 200
    assert ingestion.json()["recordsInserted"] == 3

    response = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/platform", "sourceType": "modified_file"},
    )

    assert response.status_code == 200
    files = response.json()
    assert len(files) == 2
    assert {file_artifact["metadata"]["changeStatus"] for file_artifact in files} == {
        "added",
        "modified",
    }
    assert {file_artifact["metadata"]["commitHash"] for file_artifact in files} == {HASH_ONE}


def test_artifact_filters_exclude_other_repositories(client: TestClient) -> None:
    assert upload(client, "acme/platform").status_code == 200
    assert upload(client, "acme/other").status_code == 200

    response = client.get("/api/artifacts", params={"repositoryId": "acme/platform"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["repositoryId"] == "acme/platform"


def test_artifact_source_type_is_validated(client: TestClient) -> None:
    response = client.get("/api/artifacts", params={"sourceType": "slack_message"})

    assert response.status_code == 422


def test_commit_investigation_response_contains_edges_and_missing_context(
    client: TestClient,
) -> None:
    assert upload_with_files(client).status_code == 200

    response = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    )

    assert response.status_code == 200
    investigation = response.json()
    assert investigation["selectedCommit"]["externalId"] == HASH_ONE
    assert len(investigation["modifiedFiles"]) == 2
    assert len(investigation["evidenceEdges"]) == 2
    assert {edge["relationType"] for edge in investigation["evidenceEdges"]} == {"modifies"}
    assert all(edge["direct"] is True for edge in investigation["evidenceEdges"])
    assert {item["status"] for item in investigation["evidenceStatus"]} == {
        "verified_evidence"
    }
    assert {
        warning["code"] for warning in investigation["missingContextWarnings"]
    } == {
        "missing_pull_request",
        "missing_issue",
        "missing_human_rationale",
    }


def test_commit_investigation_reports_missing_modified_files(client: TestClient) -> None:
    assert upload(client).status_code == 200

    response = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    )

    assert response.status_code == 200
    assert response.json()["modifiedFiles"] == []
    assert "missing_modified_files" in {
        warning["code"] for warning in response.json()["missingContextWarnings"]
    }


def test_commit_investigation_unknown_commit_returns_404(client: TestClient) -> None:
    response = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    )

    assert response.status_code == 404


def test_commit_investigation_requires_full_sha(client: TestClient) -> None:
    response = client.get(
        "/api/investigations/commits/abc123",
        params={"repositoryId": "acme/platform"},
    )

    assert response.status_code == 422


def test_commit_investigation_is_repository_scoped(client: TestClient) -> None:
    assert upload_with_files(client, "acme/platform").status_code == 200

    response = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/other"},
    )

    assert response.status_code == 404
