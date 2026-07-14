from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.artifacts import ArtifactRepository
from app.parsers.git_log import FULL_HASH_RE
from app.schemas.artifact import ArtifactRead
from app.schemas.ingestion import IngestionResult
from app.schemas.investigation import CommitInvestigationRead
from app.services.git_ingestion import GitIngestionService


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


def _decode_git_log(raw_content: bytes) -> str:
    if raw_content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "UTF-16 Git logs are not supported. Generate UTF-8 input directly "
                "with git log --output=git_log.txt."
            ),
        )
    try:
        return raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Git log file must be valid UTF-8 or UTF-8 with BOM",
        ) from exc


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


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
    content = _decode_git_log(raw_content)

    return GitIngestionService(session).ingest(normalized_repository_id, content)


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
        Literal["git_commit", "modified_file"] | None,
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
