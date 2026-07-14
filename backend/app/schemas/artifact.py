from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ActorRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName")
    email: str
    provider: Literal["git"] = "git"


class ArtifactCreate(BaseModel):
    id: str
    repository_id: str
    source_type: Literal["git_commit"] = "git_commit"
    external_id: str
    title: str
    summary: str
    body: str
    author_name: str
    author_email: str
    occurred_at: datetime
    ingested_at: datetime
    tags: list[str]
    metadata: dict[str, Any]


class ArtifactRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    repository_id: str = Field(alias="repositoryId")
    source_type: Literal["git_commit"] = Field(alias="sourceType")
    external_id: str = Field(alias="externalId")
    title: str
    summary: str
    body: str
    author: ActorRef
    occurred_at: datetime = Field(alias="occurredAt")
    ingested_at: datetime = Field(alias="ingestedAt")
    confidence: float = 1.0
    tags: list[str]
    metadata: dict[str, Any]
