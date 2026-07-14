from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IngestionValidationError(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    record_number: int = Field(alias="recordNumber")
    message: str
    external_id: str | None = Field(default=None, alias="externalId")


class IngestionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repository_id: str = Field(alias="repositoryId")
    records_parsed: int = Field(alias="recordsParsed")
    records_inserted: int = Field(alias="recordsInserted")
    records_skipped_as_duplicates: int = Field(alias="recordsSkippedAsDuplicates")
    records_rejected: int = Field(alias="recordsRejected")
    validation_errors: list[IngestionValidationError] = Field(alias="validationErrors")
