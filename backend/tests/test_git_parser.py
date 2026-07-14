from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_parses_supported_newline_styles(newline: str) -> None:
    content = commit_record(files=["M\tbackend/app/main.py"]).replace("\n", newline)

    result = GitLogParser().parse(content, "acme/platform")

    assert result.errors == []
    assert len(result.artifacts) == 2


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("src/main.py", "src/main.py"),
        ("dir with spaces/file.py", "dir with spaces/file.py"),
        ("café.py", "café.py"),
        ('"dir with spaces/caf\\303\\251.txt"', "dir with spaces/café.txt"),
        ('"path/\\"quoted\\".txt"', 'path/"quoted".txt'),
        ('"path\\\\name.txt"', "path\\name.txt"),
        ('"path/line\\tbreak\\n.txt"', "path/line\tbreak\n.txt"),
    ],
)
def test_decodes_git_file_paths(raw_path: str, expected: str) -> None:
    result = GitLogParser().parse(
        commit_record(files=[f"M\t{raw_path}"]),
        "acme/platform",
    )

    assert result.errors == []
    assert result.artifacts[1].metadata["path"] == expected


def test_decodes_quoted_rename_paths() -> None:
    result = GitLogParser().parse(
        commit_record(files=['R095\t"old/caf\\303\\251.txt"\t"new/caf\\303\\251.txt"']),
        "acme/platform",
    )

    file_artifact = result.artifacts[1]
    assert result.errors == []
    assert file_artifact.metadata["previousPath"] == "old/café.txt"
    assert file_artifact.metadata["path"] == "new/café.txt"


def test_invalid_quoted_path_and_copy_status_are_precise_record_errors() -> None:
    result = GitLogParser().parse(
        commit_record(files=['M\t"bad\\q.txt"', "C100\told.py\tcopy.py", "A\tvalid.py"]),
        "acme/platform",
    )

    assert [artifact.metadata.get("path") for artifact in result.artifacts[1:]] == ["valid.py"]
    assert len(result.errors) == 2
    assert "unsupported path escape" in result.errors[0].message
    assert "copy status C<score> is not supported" in result.errors[1].message


def test_malformed_file_error_truncates_extremely_long_records() -> None:
    result = GitLogParser().parse(
        commit_record(files=[f"X\t{'a' * 1000}"]),
        "acme/platform",
    )

    assert len(result.errors[0].message) < 300


def test_preserves_empty_message_commit_and_attached_file() -> None:
    result = GitLogParser().parse(
        commit_record(message="", files=["A\tempty-message.txt"]),
        "acme/platform",
    )

    commit, file_artifact = result.artifacts
    assert result.errors == []
    assert commit.title == f"Commit {HASH_ONE[:7]}"
    assert commit.summary == ""
    assert commit.body == ""
    assert file_artifact.metadata["commitHash"] == HASH_ONE


def test_parses_actual_git_output_from_documented_command(tmp_path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is not installed")

    repository = tmp_path / "repository"
    log_path = tmp_path / "git_log.txt"
    repository.mkdir()

    def run(*arguments: str) -> None:
        subprocess.run(
            [git, "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    run("init", "--quiet")
    run("config", "user.name", "Real Git User")
    run("config", "user.email", "real-git@example.com")
    unicode_file = repository / "dir with spaces" / "café.txt"
    unicode_file.parent.mkdir()
    unicode_file.write_text("first\n", encoding="utf-8")
    run("add", ".")
    run("commit", "--quiet", "-m", "Subject", "-m", "Multiline body")

    unicode_file.write_text("second\n", encoding="utf-8")
    empty_message = tmp_path / "empty-message.txt"
    empty_message.write_bytes(b"")
    run("add", ".")
    run("commit", "--quiet", "--allow-empty-message", "-F", str(empty_message))
    empty_sha = subprocess.run(
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    renamed_file = repository / "dir with spaces" / "renamed café.txt"
    run("mv", "dir with spaces/café.txt", "dir with spaces/renamed café.txt")
    run("commit", "--quiet", "-m", "Rename Unicode file")
    deleted_file = repository / "delete-me.bin"
    deleted_file.write_bytes(b"\x00\x01\xff")
    run("add", ".")
    run("commit", "--quiet", "-m", "Add binary file")
    deleted_file.unlink()
    run("add", "--all")
    run("commit", "--quiet", "-m", "Delete binary file")

    run(
        "-c",
        "core.quotepath=false",
        "log",
        "--date=iso-strict",
        "--name-status",
        "--pretty=format:commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n",
        f"--output={log_path}",
    )

    result = GitLogParser().parse(log_path.read_text(encoding="utf-8"), "real/repo")

    assert result.errors == []
    commits = [artifact for artifact in result.artifacts if artifact.source_type == "git_commit"]
    files = [artifact for artifact in result.artifacts if artifact.source_type == "modified_file"]
    empty_commit = next(artifact for artifact in commits if artifact.external_id == empty_sha)
    assert empty_commit.title == f"Commit {empty_sha[:7]}"
    assert empty_commit.body == ""
    assert {artifact.metadata["changeStatus"] for artifact in files} == {
        "added",
        "modified",
        "renamed",
        "deleted",
    }
    assert any(artifact.metadata["path"] == "dir with spaces/renamed café.txt" for artifact in files)
    assert renamed_file.exists()
