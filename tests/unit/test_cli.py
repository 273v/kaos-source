"""Tests for kaos-source CLI."""

from __future__ import annotations

import json
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from kaos_core import KaosRuntime

from kaos_source.cli import main


@pytest.fixture()
def runtime(tmp_path: Path) -> KaosRuntime:
    """Create a runtime with temp VFS for CLI tests."""
    rt = KaosRuntime()
    rt.vfs.config.disk_base_path = tmp_path / "vfs"
    KaosRuntime.set_default(rt)
    return rt


@pytest.fixture()
def sample_dir(tmp_path: Path) -> Path:
    """Create a directory with sample files for testing."""
    d = tmp_path / "sources"
    d.mkdir()
    (d / "readme.txt").write_text("Hello world", encoding="utf-8")
    (d / "data.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    (d / "notes.md").write_text("# Notes\nSome notes here.", encoding="utf-8")
    return d


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """Create a single sample file."""
    f = tmp_path / "test.txt"
    f.write_text("This is a test file with some content.", encoding="utf-8")
    return f


@pytest.fixture()
def sample_zip(tmp_path: Path) -> Path:
    """Create a sample zip archive."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("doc1.txt", "Hello")
        zf.writestr("doc2.txt", "World")
        zf.writestr("subdir/doc3.txt", "Nested")
    return zip_path


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_discover_human(runtime: KaosRuntime, sample_dir: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["discover", str(sample_dir)])
    output = stdout.getvalue()
    assert "readme.txt" in output
    assert "data.csv" in output
    assert "notes.md" in output
    assert "3 item(s) found" in output


@pytest.mark.unit()
def test_discover_json(runtime: KaosRuntime, sample_dir: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["discover", str(sample_dir), "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "discover"
    assert data["total"] == 3
    assert len(data["items"]) == 3
    names = {item["name"] for item in data["items"]}
    assert "readme.txt" in names
    assert "data.csv" in names
    assert "notes.md" in names
    # Check item structure
    for item in data["items"]:
        assert "source_id" in item
        assert "name" in item
        assert "mime_type" in item
        assert "size" in item


@pytest.mark.unit()
def test_discover_with_pattern(runtime: KaosRuntime, sample_dir: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["discover", str(sample_dir), "--pattern", "*.txt", "--json"])
    data = json.loads(stdout.getvalue())
    assert data["total"] == 1
    assert data["items"][0]["name"] == "readme.txt"


@pytest.mark.unit()
def test_discover_with_limit(runtime: KaosRuntime, sample_dir: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["discover", str(sample_dir), "--limit", "2", "--json"])
    data = json.loads(stdout.getvalue())
    assert data["total"] <= 2


@pytest.mark.unit()
def test_discover_empty_dir(runtime: KaosRuntime, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["discover", str(empty)])
    assert "No sources found" in stdout.getvalue()


@pytest.mark.unit()
def test_discover_missing_path(runtime: KaosRuntime) -> None:
    stderr = StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        main(["discover", "/nonexistent/path"])
    assert exc_info.value.code == 1
    assert "Error:" in stderr.getvalue()


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_preview_human(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["preview", str(sample_file)])
    output = stdout.getvalue()
    assert "This is a test file" in output


@pytest.mark.unit()
def test_preview_json(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["preview", str(sample_file), "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "preview"
    assert data["locator"] == str(sample_file.resolve())
    assert "text" in data
    assert "This is a test file" in data["text"]
    assert isinstance(data["truncated"], bool)


@pytest.mark.unit()
def test_preview_truncated(runtime: KaosRuntime, tmp_path: Path) -> None:
    big = tmp_path / "big.txt"
    big.write_text("x" * 5000, encoding="utf-8")
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["preview", str(big), "--max-bytes", "100", "--json"])
    data = json.loads(stdout.getvalue())
    assert data["truncated"] is True
    assert len(data["text"]) <= 100


@pytest.mark.unit()
def test_preview_missing_file(runtime: KaosRuntime) -> None:
    stderr = StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        main(["preview", "/nonexistent/file.txt"])
    assert exc_info.value.code == 1
    assert "Error:" in stderr.getvalue()


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_info_human(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["info", str(sample_file)])
    output = stdout.getvalue()
    assert "Name:" in output
    assert "test.txt" in output
    assert "Kind:" in output
    assert "Size:" in output


@pytest.mark.unit()
def test_info_json(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["info", str(sample_file), "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "info"
    assert data["name"] == "test.txt"
    assert "mime_type" in data
    assert "size" in data
    assert data["source_kind"] == "filesystem"
    assert "source_id" in data


@pytest.mark.unit()
def test_info_missing_file(runtime: KaosRuntime) -> None:
    stderr = StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        main(["info", "/nonexistent/file.txt"])
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# materialize
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_materialize_human(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["materialize", str(sample_file)])
    output = stdout.getvalue()
    assert "Materialized:" in output
    assert "Artifact ID:" in output
    assert "Bytes:" in output


@pytest.mark.unit()
def test_materialize_json(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["materialize", str(sample_file), "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "materialize"
    assert "artifact_id" in data
    assert "bytes_written" in data
    assert data["bytes_written"] > 0


@pytest.mark.unit()
def test_materialize_with_name(runtime: KaosRuntime, sample_file: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["materialize", str(sample_file), "--name", "my-artifact", "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "materialize"
    assert data["bytes_written"] > 0


# ---------------------------------------------------------------------------
# inspect-archive
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_inspect_archive_human(runtime: KaosRuntime, sample_zip: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["inspect-archive", str(sample_zip)])
    output = stdout.getvalue()
    assert "Archive:" in output
    assert "doc1.txt" in output
    assert "doc2.txt" in output
    assert "doc3.txt" in output


@pytest.mark.unit()
def test_inspect_archive_json(runtime: KaosRuntime, sample_zip: Path) -> None:
    stdout = StringIO()
    with patch("sys.stdout", stdout):
        main(["inspect-archive", str(sample_zip), "--json"])
    data = json.loads(stdout.getvalue())
    assert data["command"] == "inspect-archive"
    assert data["total"] == 3
    assert len(data["members"]) == 3
    names = {m["name"] for m in data["members"]}
    assert "doc1.txt" in names
    assert "doc2.txt" in names
    assert "doc3.txt" in names


@pytest.mark.unit()
def test_inspect_archive_missing(runtime: KaosRuntime) -> None:
    stderr = StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        main(["inspect-archive", "/nonexistent/archive.zip"])
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Edge cases / general
# ---------------------------------------------------------------------------


@pytest.mark.unit()
def test_no_command() -> None:
    stderr = StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
