from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.parsers.git_log import GitLogParser, stable_artifact_id


HASH_ONE = "a" * 40
HASH_TWO = "b" * 40


def commit_record(
    commit_hash: str = HASH_ONE,
    *,
    author: str = "Ada Lovelace <ada@example.com>",
    timestamp: str = "2026-07-14T10:30:00+05:00",
    message: str = "Add Redis cache",
    files: list[str] | None = None,
) -> str:
    indented_message = "\n".join(f"    {line}" if line else "" for line in message.splitlines())
    file_section = ""
    if files is not None:
        file_section = "\n" + "\n".join(files) + "\n"
    return (
        f"commit {commit_hash}\n"
        f"Author: {author}\n"
        f"Date: {timestamp}\n\n"
        f"{indented_message}\n"
        f"{file_section}"
    )


def test_parses_a_valid_single_commit() -> None:
    result = GitLogParser().parse(
        commit_record(message="JIRA-43 add Redis cache"),
        "acme/platform",
        ingested_at=datetime(2026, 7, 14, tzinfo=UTC),
    )

    assert result.errors == []
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.external_id == HASH_ONE
    assert artifact.title == "JIRA-43 add Redis cache"
    assert artifact.author_name == "Ada Lovelace"
    assert artifact.author_email == "ada@example.com"
    assert artifact.source_type == "git_commit"


def test_parses_multiple_commits_from_sample_data() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "sample-data" / "git_log.txt"
    result = GitLogParser().parse(sample_path.read_text(encoding="utf-8"), "demo/repo")

    assert result.errors == []
    commits = [artifact for artifact in result.artifacts if artifact.source_type == "git_commit"]
    files = [artifact for artifact in result.artifacts if artifact.source_type == "modified_file"]

    assert len(commits) == 5
    assert len(files) == 8
    assert {artifact.external_id for artifact in commits} == {
        "1" * 40,
        "2" * 40,
        "3" * 40,
        "4" * 40,
        "5" * 40,
    }


def test_preserves_multiline_commit_message() -> None:
    result = GitLogParser().parse(
        commit_record(message="Subject line\n\nBody line one\nBody line two"),
        "acme/platform",
    )

    artifact = result.artifacts[0]
    assert artifact.title == "Subject line"
    assert artifact.summary == "Subject line"
    assert artifact.body == "Subject line\n\nBody line one\nBody line two"


def test_extracts_explicit_ticket_references_once_and_in_order() -> None:
    result = GitLogParser().parse(
        commit_record(message="JIRA-43 follows OPS-7 and JIRA-43"),
        "acme/platform",
    )

    artifact = result.artifacts[0]
    assert artifact.metadata["ticketReferences"] == ["JIRA-43", "OPS-7"]
    assert artifact.tags[:2] == ["ticket:JIRA-43", "ticket:OPS-7"]


def test_normalizes_timestamp_to_utc() -> None:
    result = GitLogParser().parse(commit_record(), "acme/platform")

    assert result.artifacts[0].occurred_at == datetime(2026, 7, 14, 5, 30, tzinfo=UTC)


def test_rejects_malformed_record_without_hiding_valid_records() -> None:
    malformed = (
        f"commit {HASH_ONE}\n"
        "Author: Ada Lovelace <ada@example.com>\n\n"
        "    Missing the date\n"
    )
    result = GitLogParser().parse(
        malformed + "\n" + commit_record(HASH_TWO),
        "acme/platform",
    )

    assert len(result.artifacts) == 1
    assert result.artifacts[0].external_id == HASH_TWO
    assert len(result.errors) == 1
    assert result.errors[0].record_number == 1
    assert "Date" in result.errors[0].message


def test_rejects_non_full_hash_and_timezone_free_date() -> None:
    short_hash = GitLogParser().parse(commit_record("abc123"), "acme/platform")
    naive_date = GitLogParser().parse(
        commit_record(timestamp="2026-07-14T10:30:00"),
        "acme/platform",
    )

    assert "full 40- or 64-character" in short_hash.errors[0].message
    assert "timezone offset" in naive_date.errors[0].message


def test_artifact_id_is_stable_and_repository_scoped() -> None:
    first = GitLogParser().parse(commit_record(), "acme/platform").artifacts[0]
    second = GitLogParser().parse(commit_record(), "acme/platform").artifacts[0]
    other_repository = GitLogParser().parse(commit_record(), "acme/other").artifacts[0]

    assert first.id == second.id == stable_artifact_id("acme/platform", HASH_ONE)
    assert first.id != other_repository.id


def test_parses_added_file_record() -> None:
    result = GitLogParser().parse(
        commit_record(files=["A\tbackend/app/cache.py"]),
        "acme/platform",
    )

    file_artifact = result.artifacts[1]
    assert result.errors == []
    assert file_artifact.source_type == "modified_file"
    assert file_artifact.metadata["changeStatus"] == "added"
    assert file_artifact.metadata["path"] == "backend/app/cache.py"
    assert file_artifact.metadata["commitHash"] == HASH_ONE


def test_parses_modified_file_record() -> None:
    result = GitLogParser().parse(
        commit_record(files=["M\tbackend/app/main.py"]),
        "acme/platform",
    )

    file_artifact = result.artifacts[1]
    assert result.errors == []
    assert file_artifact.metadata["changeStatus"] == "modified"
    assert file_artifact.metadata["path"] == "backend/app/main.py"


def test_parses_deleted_file_record() -> None:
    result = GitLogParser().parse(
        commit_record(files=["D\tbackend/app/old_cache.py"]),
        "acme/platform",
    )

    file_artifact = result.artifacts[1]
    assert result.errors == []
    assert file_artifact.metadata["changeStatus"] == "deleted"
    assert file_artifact.metadata["path"] == "backend/app/old_cache.py"


def test_parses_renamed_file_record() -> None:
    result = GitLogParser().parse(
        commit_record(files=["R100\tbackend/app/cache_old.py\tbackend/app/cache.py"]),
        "acme/platform",
    )

    file_artifact = result.artifacts[1]
    assert result.errors == []
    assert file_artifact.metadata["changeStatus"] == "renamed"
    assert file_artifact.metadata["previousPath"] == "backend/app/cache_old.py"
    assert file_artifact.metadata["path"] == "backend/app/cache.py"


def test_parses_multiple_file_records_for_one_commit() -> None:
    result = GitLogParser().parse(
        commit_record(
            files=[
                "A\tbackend/app/cache.py",
                "M\tbackend/app/main.py",
                "D\tbackend/app/old_cache.py",
            ],
        ),
        "acme/platform",
    )

    assert result.errors == []
    assert len(result.artifacts) == 4
    assert [artifact.metadata["changeStatus"] for artifact in result.artifacts[1:]] == [
        "added",
        "modified",
        "deleted",
    ]


def test_parses_commit_with_no_file_records() -> None:
    result = GitLogParser().parse(commit_record(), "acme/platform")

    assert result.errors == []
    assert len(result.artifacts) == 1
    assert result.artifacts[0].source_type == "git_commit"


def test_malformed_file_record_does_not_corrupt_commit() -> None:
    result = GitLogParser().parse(
        commit_record(files=["A", "M\tbackend/app/main.py"]),
        "acme/platform",
    )

    assert len(result.artifacts) == 2
    assert result.artifacts[0].source_type == "git_commit"
    assert result.artifacts[1].metadata["path"] == "backend/app/main.py"
    assert len(result.errors) == 1
    assert "Malformed file record" in result.errors[0].message


def test_file_records_do_not_leak_between_commits() -> None:
    result = GitLogParser().parse(
        commit_record(HASH_ONE, files=["A\tbackend/app/cache.py"])
        + "\n"
        + commit_record(HASH_TWO),
        "acme/platform",
    )

    files = [artifact for artifact in result.artifacts if artifact.source_type == "modified_file"]
    assert len(files) == 1
    assert files[0].metadata["commitHash"] == HASH_ONE
