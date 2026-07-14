from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_git_parser import HASH_ONE, HASH_TWO, commit_record


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
        "recordsUpdated": 0,
        "recordsDeleted": 0,
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
    response = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/platform", "sourceType": "slack_message"},
    )

    assert response.status_code == 422


def test_artifact_listing_requires_nonblank_repository(client: TestClient) -> None:
    missing = client.get("/api/artifacts")
    blank = client.get("/api/artifacts", params={"repositoryId": "   "})

    assert missing.status_code == 422
    assert blank.status_code == 422


def test_upload_accepts_utf8_bom_and_rejects_utf16(client: TestClient) -> None:
    content = commit_record(HASH_ONE).encode("utf-8")
    bom_response = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/bom"},
        files={"file": ("git_log.txt", b"\xef\xbb\xbf" + content, "text/plain")},
    )
    utf16_response = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/utf16"},
        files={"file": ("git_log.txt", commit_record(HASH_TWO).encode("utf-16"), "text/plain")},
    )

    assert bom_response.status_code == 200
    assert bom_response.json()["recordsInserted"] == 1
    assert utf16_response.status_code == 400
    assert "UTF-16" in utf16_response.json()["detail"]


def test_upload_rejects_invalid_utf8_and_oversized_files(client: TestClient) -> None:
    invalid = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/invalid"},
        files={"file": ("git_log.txt", b"\x80invalid", "text/plain")},
    )
    oversized = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/large"},
        files={"file": ("git_log.txt", b"a" * (5 * 1024 * 1024 + 1), "text/plain")},
    )

    assert invalid.status_code == 400
    assert "valid UTF-8" in invalid.json()["detail"]
    assert oversized.status_code == 413


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


def test_commit_investigation_rejects_blank_repository(client: TestClient) -> None:
    response = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "   "},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "repositoryId must not be blank"


def test_empty_message_commit_is_persisted_and_investigated(client: TestClient) -> None:
    response = client.post(
        "/api/ingestions/git",
        data={"repositoryId": "acme/empty"},
        files={
            "file": (
                "git_log.txt",
                commit_record(HASH_ONE, message="", files=["A\tempty.txt"]),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    investigation = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/empty"},
    ).json()
    assert investigation["selectedCommit"]["title"] == f"Commit {HASH_ONE[:7]}"
    assert investigation["selectedCommit"]["body"] == ""
    assert investigation["modifiedFiles"][0]["metadata"]["path"] == "empty.txt"
    assert "missing_human_rationale" in {
        warning["code"] for warning in investigation["missingContextWarnings"]
    }
