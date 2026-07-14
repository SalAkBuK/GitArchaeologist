from __future__ import annotations

import re
from hashlib import sha256
from datetime import UTC, datetime
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactCreate
from app.schemas.ingestion import IngestionValidationError


ARTIFACT_ID_NAMESPACE = UUID("79ab69cc-01a8-4dc3-9a51-1b585c6d83a8")
COMMIT_HEADER_RE = re.compile(r"(?m)^commit[ \t]+([^\r\n]+?)[ \t]*$")
FULL_HASH_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
AUTHOR_RE = re.compile(r"^Author:\s*(.+?)\s*<([^<>\s]+@[^<>\s]+)>\s*$")
DATE_RE = re.compile(r"^Date:\s*(\S+)\s*$")
TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

COMPONENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("redis", re.compile(r"\bredis\b", re.IGNORECASE)),
    ("postgresql", re.compile(r"\b(?:postgres|postgresql)\b", re.IGNORECASE)),
    ("database", re.compile(r"\bdatabase\b|\bdb\b", re.IGNORECASE)),
    ("rate-limiter", re.compile(r"\brate[- ]?limit(?:er|ing)?\b", re.IGNORECASE)),
    ("retry-worker", re.compile(r"\bretry[- ]worker\b", re.IGNORECASE)),
    ("ui", re.compile(r"\bui\b|\buser interface\b", re.IGNORECASE)),
)

GIT_PATH_ESCAPE_BYTES = {
    "a": 0x07,
    "b": 0x08,
    "t": 0x09,
    "n": 0x0A,
    "v": 0x0B,
    "f": 0x0C,
    "r": 0x0D,
    '"': 0x22,
    "\\": 0x5C,
}
MAX_ERROR_RECORD_LENGTH = 200


class GitParseResult(BaseModel):
    artifacts: list[ArtifactCreate] = Field(default_factory=list)
    errors: list[IngestionValidationError] = Field(default_factory=list)


def stable_artifact_id(repository_id: str, commit_hash: str) -> str:
    identity = f"{repository_id}:git_commit:{commit_hash.lower()}"
    return str(uuid5(ARTIFACT_ID_NAMESPACE, identity))


def stable_modified_file_artifact_id(
    repository_id: str,
    commit_hash: str,
    status: str,
    path: str,
    previous_path: str | None = None,
) -> str:
    identity = ":".join(
        [
            repository_id,
            "modified_file",
            commit_hash.lower(),
            status,
            previous_path or "",
            path,
        ]
    )
    return str(uuid5(ARTIFACT_ID_NAMESPACE, identity))


def stable_modified_file_external_id(
    commit_hash: str,
    status: str,
    path: str,
    previous_path: str | None = None,
) -> str:
    identity = "\0".join([commit_hash.lower(), status, previous_path or "", path])
    return sha256(identity.encode("utf-8")).hexdigest()


def _unique_in_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _normalize_message(lines: list[str]) -> str:
    normalized_lines = [line[4:] if line.startswith("    ") else line for line in lines]
    while normalized_lines and not normalized_lines[0].strip():
        normalized_lines.pop(0)
    while normalized_lines and not normalized_lines[-1].strip():
        normalized_lines.pop()
    return "\n".join(line.rstrip() for line in normalized_lines).strip()


def _summary_from_message(message: str, maximum_length: int = 280) -> str:
    first_paragraph = re.split(r"\n\s*\n", message, maxsplit=1)[0]
    summary = " ".join(first_paragraph.split())
    if len(summary) <= maximum_length:
        return summary
    shortened = summary[: maximum_length - 1].rsplit(" ", maxsplit=1)[0]
    return f"{shortened or summary[: maximum_length - 3]}..."


def decode_git_path(raw_path: str) -> str:
    """Decode the C-style path quoting emitted by Git name-status output."""
    if not raw_path.startswith('"'):
        return raw_path
    if len(raw_path) < 2 or not raw_path.endswith('"'):
        raise ValueError("quoted path is missing its closing double quote")

    encoded = bytearray()
    content = raw_path[1:-1]
    index = 0
    while index < len(content):
        character = content[index]
        if character != "\\":
            encoded.extend(character.encode("utf-8"))
            index += 1
            continue

        index += 1
        if index >= len(content):
            raise ValueError("quoted path ends with an incomplete escape")
        escape = content[index]
        if escape in GIT_PATH_ESCAPE_BYTES:
            encoded.append(GIT_PATH_ESCAPE_BYTES[escape])
            index += 1
            continue
        if escape in "01234567":
            end = index + 1
            while end < len(content) and end < index + 3 and content[end] in "01234567":
                end += 1
            value = int(content[index:end], 8)
            if value > 0xFF:
                raise ValueError("octal escape is outside the byte range")
            encoded.append(value)
            index = end
            continue
        raise ValueError(f"unsupported path escape \\{escape}")

    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("quoted path contains invalid UTF-8 byte escapes") from exc


def _record_excerpt(value: str) -> str:
    if len(value) <= MAX_ERROR_RECORD_LENGTH:
        return value
    return f"{value[: MAX_ERROR_RECORD_LENGTH - 3]}..."


def _parse_timestamp(raw_timestamp: str) -> datetime:
    candidate = raw_timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("Date must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Date must include a timezone offset")
    return parsed.astimezone(UTC)


def _split_message_and_file_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    message_lines: list[str] = []
    file_lines: list[str] = []
    reading_files = False

    for line in lines:
        if not reading_files and (line.startswith("    ") or not line.strip()):
            message_lines.append(line)
            continue
        reading_files = True
        file_lines.append(line)

    return message_lines, file_lines


def _status_label(status: str) -> str:
    return {
        "added": "Added",
        "modified": "Modified",
        "deleted": "Deleted",
        "renamed": "Renamed",
    }[status]


class GitLogParser:
    def parse(
        self,
        content: str,
        repository_id: str,
        *,
        ingested_at: datetime | None = None,
    ) -> GitParseResult:
        result = GitParseResult()
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if not content.strip():
            return result

        normalized_repository_id = repository_id.strip()
        if not normalized_repository_id:
            result.errors.append(
                IngestionValidationError(recordNumber=1, message="Repository ID is required")
            )
            return result

        matches = list(COMMIT_HEADER_RE.finditer(content))
        if not matches:
            result.errors.append(
                IngestionValidationError(
                    recordNumber=1,
                    message="Expected a record beginning with 'commit <full hash>'",
                )
            )
            return result

        preamble = content[: matches[0].start()]
        if preamble.strip():
            result.errors.append(
                IngestionValidationError(
                    recordNumber=1,
                    message="Unexpected content before the first commit record",
                )
            )

        normalized_ingested_at = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            record_body = content[match.end() : end]
            record_number = index + 1
            raw_hash = match.group(1).strip()
            commit_hash = raw_hash.lower()

            try:
                artifacts, errors = self._parse_record(
                    record_body,
                    normalized_repository_id,
                    commit_hash,
                    normalized_ingested_at,
                    record_number,
                )
            except ValueError as exc:
                result.errors.append(
                    IngestionValidationError(
                        recordNumber=record_number,
                        externalId=commit_hash if FULL_HASH_RE.fullmatch(raw_hash) else None,
                        message=str(exc),
                    )
                )
            else:
                result.artifacts.extend(artifacts)
                result.errors.extend(errors)

        return result

    def _parse_record(
        self,
        body: str,
        repository_id: str,
        commit_hash: str,
        ingested_at: datetime,
        record_number: int,
    ) -> tuple[list[ArtifactCreate], list[IngestionValidationError]]:
        if not FULL_HASH_RE.fullmatch(commit_hash):
            raise ValueError("Commit hash must be a full 40- or 64-character hexadecimal hash")

        lines = body.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)

        author_name: str | None = None
        author_email: str | None = None
        timestamp: datetime | None = None
        message_start: int | None = None

        for line_index, line in enumerate(lines):
            if not line.strip():
                message_start = line_index + 1
                break
            author_match = AUTHOR_RE.fullmatch(line)
            if author_match:
                if author_name is not None:
                    raise ValueError("Commit record contains more than one Author header")
                author_name = author_match.group(1).strip()
                author_email = author_match.group(2).strip()
                continue
            date_match = DATE_RE.fullmatch(line)
            if date_match:
                if timestamp is not None:
                    raise ValueError("Commit record contains more than one Date header")
                timestamp = _parse_timestamp(date_match.group(1))
                continue
            raise ValueError(f"Unexpected commit header: {line.strip()!r}")

        if not author_name or not author_email:
            raise ValueError("Commit record is missing a valid 'Author: Name <email>' header")
        if timestamp is None:
            raise ValueError("Commit record is missing a valid 'Date: <ISO 8601 timestamp>' header")
        if message_start is None:
            raise ValueError("Commit record is missing the blank line before its message")

        message_lines, file_lines = _split_message_and_file_lines(lines[message_start:])
        message = _normalize_message(message_lines)
        title = next(
            (line.strip() for line in message.splitlines() if line.strip()),
            f"Commit {commit_hash[:7]}",
        )
        tickets = _unique_in_order(TICKET_RE.findall(message))
        components = [
            component
            for component, pattern in COMPONENT_PATTERNS
            if pattern.search(message)
        ]
        tags = [*(f"ticket:{ticket}" for ticket in tickets), *(f"component:{item}" for item in components)]

        commit_artifact = ArtifactCreate(
            id=stable_artifact_id(repository_id, commit_hash),
            repository_id=repository_id,
            external_id=commit_hash,
            title=title,
            summary=_summary_from_message(message),
            body=message,
            author_name=author_name,
            author_email=author_email,
            occurred_at=timestamp,
            ingested_at=ingested_at,
            tags=tags,
            metadata={
                "commitHash": commit_hash,
                "ticketReferences": tickets,
                "components": components,
            },
        )

        artifacts = [commit_artifact]
        errors: list[IngestionValidationError] = []
        for file_line in file_lines:
            if not file_line.strip():
                continue
            try:
                artifacts.append(
                    self._parse_file_record(
                        file_line=file_line,
                        repository_id=repository_id,
                        commit_hash=commit_hash,
                        author_name=author_name,
                        author_email=author_email,
                        occurred_at=timestamp,
                        ingested_at=ingested_at,
                    )
                )
            except ValueError as exc:
                errors.append(
                    IngestionValidationError(
                        recordNumber=record_number,
                        externalId=commit_hash,
                        message=f"Malformed file record {_record_excerpt(file_line)!r}: {exc}",
                    )
                )

        return artifacts, errors

    def _parse_file_record(
        self,
        *,
        file_line: str,
        repository_id: str,
        commit_hash: str,
        author_name: str,
        author_email: str,
        occurred_at: datetime,
        ingested_at: datetime,
    ) -> ArtifactCreate:
        fields = file_line.split("\t")
        raw_status = fields[0]
        previous_path: str | None = None

        if raw_status in {"A", "M", "D"}:
            if len(fields) != 2:
                raise ValueError("expected '<A|M|D>\\t<path>'")
            status = {"A": "added", "M": "modified", "D": "deleted"}[raw_status]
            path = decode_git_path(fields[1])
        elif raw_status.startswith("R"):
            if len(fields) != 3:
                raise ValueError("expected 'R<score>\\t<previous path>\\t<path>'")
            if not re.fullmatch(r"R\d{1,3}", raw_status):
                raise ValueError("rename status must include a numeric similarity score")
            status = "renamed"
            previous_path = decode_git_path(fields[1])
            path = decode_git_path(fields[2])
        elif raw_status.startswith("C"):
            raise ValueError("copy status C<score> is not supported")
        else:
            raise ValueError("unsupported status; expected A, M, D, or R<score>")

        if not path:
            raise ValueError("file path must not be empty")
        if status == "renamed" and not previous_path:
            raise ValueError("previous file path must not be empty")

        label = _status_label(status)
        title = f"{label} {path}"
        summary = (
            f"{label} file {previous_path} -> {path}"
            if previous_path
            else f"{label} file {path}"
        )

        return ArtifactCreate(
            id=stable_modified_file_artifact_id(
                repository_id,
                commit_hash,
                status,
                path,
                previous_path,
            ),
            repository_id=repository_id,
            source_type="modified_file",
            external_id=stable_modified_file_external_id(
                commit_hash,
                status,
                path,
                previous_path,
            ),
            title=title,
            summary=summary,
            body=summary,
            author_name=author_name,
            author_email=author_email,
            occurred_at=occurred_at,
            ingested_at=ingested_at,
            tags=[f"commit:{commit_hash}", f"file_status:{status}"],
            metadata={
                "commitHash": commit_hash,
                "path": path,
                "previousPath": previous_path,
                "changeStatus": status,
                "rawStatus": raw_status,
            },
        )
