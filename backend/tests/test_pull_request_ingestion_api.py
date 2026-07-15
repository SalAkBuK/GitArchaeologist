from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import MAX_UPLOAD_BYTES
from app.parsers.pull_request_fixture import MAX_VALIDATION_ERRORS
from tests.test_api import upload_with_files
from tests.test_git_parser import HASH_ONE, HASH_TWO


def pull_request(
    number: int = 22,
    *,
    title: str = "Add deterministic cache evidence",
    body: str | None = "Documents why the cache was added.",
    commit_shas: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": "merged",
        "author": {"login": "developer"},
        "createdAt": "2026-07-10T10:00:00Z",
        "updatedAt": "2026-07-11T12:00:00Z",
        "mergedAt": "2026-07-11T12:00:00Z",
        "url": f"https://github.com/example/repository/pull/{number}",
        "baseBranch": "main",
        "headBranch": f"feature/pr-{number}",
        "commitShas": commit_shas if commit_shas is not None else [HASH_ONE],
    }


def fixture(repository_id: str, records: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        {
            "schemaVersion": 1,
            "repositoryId": repository_id,
            "pullRequests": records,
        }
    ).encode("utf-8")


def upload_pull_requests(
    client: TestClient,
    repository_id: str,
    content: bytes,
    *,
    filename: str = "pull_requests.json",
):
    return client.post(
        "/api/ingestions/github/pull-requests",
        data={"repositoryId": repository_id},
        files={"file": (filename, content, "application/json")},
    )


def test_upload_accepts_only_json_and_enforces_exact_size_boundary(
    client: TestClient,
) -> None:
    normal = fixture("acme/platform", [pull_request()])
    wrong_extension = upload_pull_requests(
        client,
        "acme/platform",
        normal,
        filename="pull_requests.txt",
    )

    payload = {
        "schemaVersion": 1,
        "repositoryId": "acme/boundary",
        "pullRequests": [pull_request(body="")],
    }
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload["pullRequests"][0]["body"] = "x" * (MAX_UPLOAD_BYTES - len(encoded))
    exactly_limit = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(exactly_limit) == MAX_UPLOAD_BYTES

    accepted = upload_pull_requests(client, "acme/boundary", exactly_limit)
    too_large = upload_pull_requests(
        client,
        "acme/too-large",
        fixture("acme/too-large", []) + b" " * MAX_UPLOAD_BYTES,
    )

    assert wrong_extension.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["recordsInserted"] == 1
    assert too_large.status_code == 413


def test_upload_accepts_utf8_and_bom_and_rejects_invalid_utf8(
    client: TestClient,
) -> None:
    utf8 = upload_pull_requests(
        client,
        "acme/utf8",
        fixture("acme/utf8", [pull_request()]),
    )
    bom = upload_pull_requests(
        client,
        "acme/bom",
        b"\xef\xbb\xbf" + fixture("acme/bom", [pull_request()]),
    )
    invalid = upload_pull_requests(client, "acme/invalid", b"\x80invalid")

    assert utf8.status_code == 200
    assert bom.status_code == 200
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == (
        "Pull request fixture file must be valid UTF-8 or UTF-8 with BOM"
    )


def test_fixture_and_request_repository_ids_must_match(client: TestClient) -> None:
    response = upload_pull_requests(
        client,
        "acme/request",
        fixture("acme/fixture", [pull_request()]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Fixture repositoryId does not match the request repositoryId"
    )
    listed = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/request", "sourceType": "github_pull_request"},
    )
    assert listed.json() == []


def test_record_validation_errors_are_bounded_without_skipping_later_valid_records(
    client: TestClient,
) -> None:
    invalid_records = [pull_request(number=0) for _ in range(MAX_VALIDATION_ERRORS + 5)]
    records = [*invalid_records, pull_request(number=22)]

    response = upload_pull_requests(
        client,
        "acme/bounded",
        fixture("acme/bounded", records),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["recordsReceived"] == MAX_VALIDATION_ERRORS + 6
    assert result["recordsRejected"] == MAX_VALIDATION_ERRORS + 5
    assert len(result["validationErrors"]) == MAX_VALIDATION_ERRORS
    assert result["validationErrors"][0] == {
        "recordNumber": 1,
        "message": "number: Input should be greater than 0",
        "externalId": None,
    }
    assert max(len(error["message"]) for error in result["validationErrors"]) < 200
    assert result["recordsInserted"] == 1


def test_explicit_known_reference_produces_exact_edge_and_warning_contract(
    client: TestClient,
) -> None:
    assert upload_with_files(client).status_code == 200
    ingestion = upload_pull_requests(
        client,
        "acme/platform",
        fixture("acme/platform", [pull_request()]),
    )
    assert ingestion.status_code == 200
    assert ingestion.json()["explicitCommitReferencesResolved"] == 1
    assert ingestion.json()["explicitCommitReferencesUnresolved"] == 0

    investigation = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    ).json()
    pull_request_artifact = investigation["linkedPullRequests"][0]
    contains = [
        edge for edge in investigation["evidenceEdges"] if edge["relationType"] == "contains"
    ]
    modifies = [
        edge for edge in investigation["evidenceEdges"] if edge["relationType"] == "modifies"
    ]

    assert len(contains) == 1
    assert contains[0]["fromArtifactId"] == pull_request_artifact["id"]
    assert contains[0]["toArtifactId"] == investigation["selectedCommit"]["id"]
    assert contains[0]["direct"] is True
    assert {edge["toArtifactId"] for edge in modifies} == {
        artifact["id"] for artifact in investigation["modifiedFiles"]
    }
    assert {edge["fromArtifactId"] for edge in modifies} == {
        investigation["selectedCommit"]["id"]
    }
    warnings = {
        warning["code"]: warning["message"]
        for warning in investigation["missingContextWarnings"]
    }
    assert warnings == {
        "missing_issue": "No issue evidence has been imported for this investigation."
    }


def test_empty_body_and_unknown_reference_have_stable_scoped_warnings(
    client: TestClient,
) -> None:
    assert upload_with_files(client).status_code == 200
    assert upload_pull_requests(
        client,
        "acme/platform",
        fixture(
            "acme/platform",
            [pull_request(body="  ", commit_shas=[HASH_ONE, HASH_TWO])],
        ),
    ).status_code == 200

    investigation = client.get(
        f"/api/investigations/commits/{HASH_ONE}",
        params={"repositoryId": "acme/platform"},
    ).json()
    codes = [warning["code"] for warning in investigation["missingContextWarnings"]]

    assert codes == [
        "missing_pull_request_body",
        "missing_issue",
        "missing_human_rationale",
        "unresolved_pull_request_commit",
    ]
    assert investigation["unresolvedCommitReferences"] == [
        {
            "pullRequestId": investigation["linkedPullRequests"][0]["id"],
            "pullRequestNumber": 22,
            "commitSha": HASH_TWO,
        }
    ]
    assert all(edge["toArtifactId"] != HASH_TWO for edge in investigation["evidenceEdges"])
    assert client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/platform", "sourceType": "git_commit"},
    ).json()[0]["externalId"] == HASH_ONE


def test_overlapping_external_ids_are_repository_isolated(client: TestClient) -> None:
    assert upload_with_files(client, "acme/one").status_code == 200
    first = upload_pull_requests(
        client,
        "acme/one",
        fixture("acme/one", [pull_request(number=22, title="Repository one")]),
    )
    second = upload_pull_requests(
        client,
        "acme/two",
        fixture("acme/two", [pull_request(number=22, title="Repository two")]),
    )

    assert first.json()["explicitCommitReferencesResolved"] == 1
    assert second.json()["explicitCommitReferencesResolved"] == 0
    assert second.json()["explicitCommitReferencesUnresolved"] == 1
    one = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/one", "sourceType": "github_pull_request"},
    ).json()
    two = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/two", "sourceType": "github_pull_request"},
    ).json()
    assert one[0]["id"] != two[0]["id"]
    assert one[0]["title"] == "Repository one"
    assert two[0]["title"] == "Repository two"

    update = upload_pull_requests(
        client,
        "acme/one",
        fixture("acme/one", [pull_request(number=22, title="Repository one updated")]),
    )
    assert update.json()["recordsUpdated"] == 1
    two_after = client.get(
        "/api/artifacts",
        params={"repositoryId": "acme/two", "sourceType": "github_pull_request"},
    ).json()
    assert two_after[0]["title"] == "Repository two"
