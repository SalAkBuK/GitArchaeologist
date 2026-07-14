from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, Field, ValidationError

from app.schemas.artifact import ArtifactCreate
from app.schemas.ingestion import IngestionValidationError
from app.schemas.pull_request import (
    PullRequestFixtureEnvelope,
    PullRequestFixtureRecord,
)


PULL_REQUEST_ARTIFACT_ID_NAMESPACE = UUID("72c7300a-6f31-4d48-9ddb-5e186465c597")
MAX_VALIDATION_ERRORS = 100


class PullRequestFixtureFormatError(ValueError):
    pass


class PullRequestParseResult(BaseModel):
    repository_id: str
    records_received: int
    records_rejected: int = 0
    artifacts: list[ArtifactCreate] = Field(default_factory=list)
    errors: list[IngestionValidationError] = Field(default_factory=list)


def stable_pull_request_artifact_id(repository_id: str, number: int) -> str:
    identity = f"{repository_id}:github_pull_request:{number}"
    return str(uuid5(PULL_REQUEST_ARTIFACT_ID_NAMESPACE, identity))


def _validation_message(error: ValidationError) -> str:
    first = error.errors(include_url=False, include_input=False)[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}" if location else str(first["msg"])


def _iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.astimezone(UTC).isoformat()
    return normalized.replace("+00:00", "Z")


class PullRequestFixtureParser:
    def parse(
        self,
        content: str,
        expected_repository_id: str,
        *,
        ingested_at: datetime | None = None,
    ) -> PullRequestParseResult:
        try:
            payload: Any = json.loads(content)
        except json.JSONDecodeError as exc:
            raise PullRequestFixtureFormatError(
                f"Malformed JSON at line {exc.lineno}, column {exc.colno}"
            ) from exc

        try:
            envelope = PullRequestFixtureEnvelope.model_validate(payload)
        except ValidationError as exc:
            raise PullRequestFixtureFormatError(_validation_message(exc)) from exc

        normalized_expected_repository_id = expected_repository_id.strip()
        if envelope.repository_id != normalized_expected_repository_id:
            raise PullRequestFixtureFormatError(
                "Fixture repositoryId does not match the request repositoryId"
            )

        normalized_ingested_at = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        result = PullRequestParseResult(
            repository_id=envelope.repository_id,
            records_received=len(envelope.pull_requests),
        )
        seen_numbers: set[int] = set()
        for index, raw_record in enumerate(envelope.pull_requests, start=1):
            try:
                record = PullRequestFixtureRecord.model_validate(raw_record)
            except ValidationError as exc:
                result.records_rejected += 1
                if len(result.errors) < MAX_VALIDATION_ERRORS:
                    result.errors.append(
                        IngestionValidationError(
                            recordNumber=index,
                            message=_validation_message(exc),
                        )
                    )
                continue

            if record.number in seen_numbers:
                result.records_rejected += 1
                if len(result.errors) < MAX_VALIDATION_ERRORS:
                    result.errors.append(
                        IngestionValidationError(
                            recordNumber=index,
                            externalId=str(record.number),
                            message=(
                                f"Duplicate pull request number {record.number} in this fixture"
                            ),
                        )
                    )
                continue
            seen_numbers.add(record.number)
            result.artifacts.append(
                self._to_artifact(
                    envelope.repository_id,
                    record,
                    normalized_ingested_at,
                )
            )

        return result

    @staticmethod
    def _to_artifact(
        repository_id: str,
        record: PullRequestFixtureRecord,
        ingested_at: datetime,
    ) -> ArtifactCreate:
        body = record.body
        return ArtifactCreate(
            id=stable_pull_request_artifact_id(repository_id, record.number),
            repository_id=repository_id,
            source_type="github_pull_request",
            external_id=str(record.number),
            title=record.title,
            summary=body or "",
            body=body or "",
            author_name=record.author.login,
            author_email="",
            occurred_at=record.created_at,
            ingested_at=ingested_at,
            tags=[f"pull_request_state:{record.state}"],
            metadata={
                "number": record.number,
                "body": body,
                "state": record.state,
                "authorLogin": record.author.login,
                "createdAt": _iso_timestamp(record.created_at),
                "updatedAt": _iso_timestamp(record.updated_at),
                "mergedAt": _iso_timestamp(record.merged_at),
                "url": str(record.url) if record.url is not None else None,
                "baseBranch": record.base_branch,
                "headBranch": record.head_branch,
                "commitShas": record.commit_shas,
            },
        )
