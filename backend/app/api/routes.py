from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.artifacts import ArtifactRepository
from app.parsers.git_log import FULL_HASH_RE
from app.parsers.pull_request_fixture import PullRequestFixtureFormatError
from app.importers.errors import RepositoryImportError
from app.schemas.artifact import ArtifactRead
from app.schemas.explanation import ExplanationRead, ExplanationRequest
from app.schemas.ingestion import IngestionResult
from app.schemas.investigation import CommitInvestigationRead
from app.schemas.pull_request import PullRequestIngestionResult
from app.schemas.repository_import import (
    RepositoryImportRequest,
    RepositoryImportResponse,
)
from app.services.git_ingestion import GitIngestionService
from app.services.pull_request_ingestion import PullRequestIngestionService
from app.services.repository_import import RepositoryImportService
from app.services.explanation import (
    ExplanationArtifactNotFoundError,
    ExplanationCrossRepositoryError,
    ExplanationDisconnectedArtifactError,
    ExplanationService,
    ExplanationUnsupportedArtifactError,
)


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REPOSITORY_ID_LENGTH = 255
router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def _normalize_repository_id(repository_id: str) -> str:
    normalized = repository_id.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="repositoryId must not be blank",
        )
    return normalized


def _decode_utf8_upload(raw_content: bytes, *, upload_type: str) -> str:
    if raw_content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"UTF-16 {upload_type} files are not supported. "
                "Provide UTF-8 or UTF-8 with BOM."
            ),
        )
    try:
        return raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{upload_type} file must be valid UTF-8 or UTF-8 with BOM",
        ) from exc


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/api/repositories/import",
    response_model=RepositoryImportResponse,
    response_model_by_alias=True,
)
def import_public_repository(
    request: RepositoryImportRequest,
    session: Annotated[Session, Depends(get_db)],
) -> RepositoryImportResponse:
    try:
        return RepositoryImportService(session).import_repository(request.repository_url)
    except RepositoryImportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "repository_import_failed",
                "message": "Repository import failed",
            },
        ) from exc


@router.post(
    "/api/ingestions/git",
    response_model=IngestionResult,
    response_model_by_alias=True,
)
async def ingest_git_log(
    repository_id: Annotated[
        str,
        Form(alias="repositoryId", min_length=1, max_length=MAX_REPOSITORY_ID_LENGTH),
    ],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
) -> IngestionResult:
    normalized_repository_id = _normalize_repository_id(repository_id)
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A .txt Git log file is required",
        )

    raw_content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Git log file exceeds the {MAX_UPLOAD_BYTES}-byte limit",
        )
    content = _decode_utf8_upload(raw_content, upload_type="Git log")

    return GitIngestionService(session).ingest(normalized_repository_id, content)


@router.post(
    "/api/ingestions/github/pull-requests",
    response_model=PullRequestIngestionResult,
    response_model_by_alias=True,
)
async def ingest_pull_request_fixture(
    repository_id: Annotated[
        str,
        Form(alias="repositoryId", min_length=1, max_length=MAX_REPOSITORY_ID_LENGTH),
    ],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
) -> PullRequestIngestionResult:
    normalized_repository_id = _normalize_repository_id(repository_id)
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A .json pull request fixture is required",
        )

    raw_content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Pull request fixture exceeds the {MAX_UPLOAD_BYTES}-byte limit",
        )
    content = _decode_utf8_upload(raw_content, upload_type="Pull request fixture")

    try:
        return PullRequestIngestionService(session).ingest(
            normalized_repository_id,
            content,
        )
    except PullRequestFixtureFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/artifacts",
    response_model=list[ArtifactRead],
    response_model_by_alias=True,
)
def list_artifacts(
    session: Annotated[Session, Depends(get_db)],
    repository_id: Annotated[
        str,
        Query(alias="repositoryId", min_length=1, max_length=MAX_REPOSITORY_ID_LENGTH),
    ],
    source_type: Annotated[
        Literal["git_commit", "modified_file", "github_pull_request"] | None,
        Query(alias="sourceType"),
    ] = None,
) -> list[ArtifactRead]:
    return ArtifactRepository(session).list(
        repository_id=_normalize_repository_id(repository_id),
        source_type=source_type,
    )


@router.get(
    "/api/investigations/commits/{commit_sha}",
    response_model=CommitInvestigationRead,
    response_model_by_alias=True,
)
def investigate_commit(
    commit_sha: str,
    session: Annotated[Session, Depends(get_db)],
    repository_id: Annotated[
        str,
        Query(alias="repositoryId", min_length=1, max_length=MAX_REPOSITORY_ID_LENGTH),
    ],
) -> CommitInvestigationRead:
    normalized_commit_sha = commit_sha.strip().lower()
    if not FULL_HASH_RE.fullmatch(normalized_commit_sha):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A full 40- or 64-character commit SHA is required",
        )

    investigation = ArtifactRepository(session).build_commit_investigation(
        repository_id=_normalize_repository_id(repository_id),
        commit_sha=normalized_commit_sha,
    )
    if investigation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commit artifact not found",
        )
    return investigation


@router.post(
    "/api/explanations",
    response_model=ExplanationRead,
    response_model_by_alias=True,
)
def explain_selected_evidence(
    request: ExplanationRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ExplanationRead:
    try:
        return ExplanationService(ArtifactRepository(session)).explain(
            repository_id=_normalize_repository_id(request.repository_id),
            selected_artifact_id=request.selected_artifact_id,
            question=request.question,
            import_warning_codes=list(request.import_warning_codes),
        )
    except ExplanationArtifactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "explanation_artifact_not_found",
                "message": "Selected evidence artifact was not found",
            },
        ) from exc
    except ExplanationCrossRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "explanation_repository_mismatch",
                "message": "Selected evidence artifact does not belong to this repository",
            },
        ) from exc
    except ExplanationUnsupportedArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "unsupported_explanation_artifact",
                "message": "Selected artifact type cannot be used for explanations",
            },
        ) from exc
    except ExplanationDisconnectedArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "disconnected_explanation_artifact",
                "message": "Selected file has no verified commit relationship",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "explanation_generation_failed",
                "message": "Grounded explanation generation failed",
            },
        ) from exc
