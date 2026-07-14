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
router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


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
        Form(alias="repositoryId", min_length=1, max_length=255),
    ],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
) -> IngestionResult:
    normalized_repository_id = repository_id.strip()
    if not normalized_repository_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="repositoryId must not be blank",
        )
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
    try:
        content = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Git log file must be UTF-8 encoded",
        ) from exc

    return GitIngestionService(session).ingest(normalized_repository_id, content)


@router.get(
    "/api/artifacts",
    response_model=list[ArtifactRead],
    response_model_by_alias=True,
)
def list_artifacts(
    session: Annotated[Session, Depends(get_db)],
    repository_id: Annotated[
        str | None,
        Query(alias="repositoryId", min_length=1, max_length=255),
    ] = None,
    source_type: Annotated[
        Literal["git_commit", "modified_file"] | None,
        Query(alias="sourceType"),
    ] = None,
) -> list[ArtifactRead]:
    return ArtifactRepository(session).list(
        repository_id=repository_id,
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
        Query(alias="repositoryId", min_length=1, max_length=255),
    ],
) -> CommitInvestigationRead:
    normalized_commit_sha = commit_sha.strip().lower()
    if not FULL_HASH_RE.fullmatch(normalized_commit_sha):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A full 40- or 64-character commit SHA is required",
        )

    investigation = ArtifactRepository(session).build_commit_investigation(
        repository_id=repository_id.strip(),
        commit_sha=normalized_commit_sha,
    )
    if investigation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commit artifact not found",
        )
    return investigation
