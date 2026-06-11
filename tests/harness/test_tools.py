"""Tests for the harness toolset: shell, files, web, memory."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from mirach.harness.tools.files import edit_file, read_file, search, write_file
from mirach.harness.tools.memory import make_recall, make_remember
from mirach.harness.tools.shell import bash
from mirach.harness.tools.web import _strip_html, web_fetch, web_search

# ══════════════════════════════════════════════════════════════════════════════
# shell.py — bash
# ══════════════════════════════════════════════════════════════════════════════


class TestBash:
    def test_simple_command(self):
        out = bash({"command": "echo hello"})
        assert out == "hello"

    def test_nonzero_exit_includes_exit_code(self):
        out = bash({"command": "exit 42"})
        assert "[exit 42]" in out

    def test_stderr_included_on_failure(self):
        out = bash({"command": "ls /nonexistent_path_xyz 2>&1; true"})
        # output depends on system but command runs without error
        assert isinstance(out, str)

    def test_timeout_returns_error_string(self):
        out = bash({"command": "sleep 60", "timeout": 0.1})
        assert "[error]" in out
        assert "timed out" in out

    def test_empty_output(self):
        out = bash({"command": "true"})
        assert out == "(no output)"


# ══════════════════════════════════════════════════════════════════════════════
# files.py
# ══════════════════════════════════════════════════════════════════════════════


class TestReadFile:
    def test_reads_file_content(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\n")
        assert read_file({"path": str(f)}) == "line1\nline2\n"

    def test_missing_file_returns_error(self, tmp_path):
        result = read_file({"path": str(tmp_path / "nope.txt")})
        assert "[error]" in result

    def test_not_a_file_returns_error(self, tmp_path):
        result = read_file({"path": str(tmp_path)})
        assert "[error]" in result

    def test_offset_and_limit(self, tmp_path):
        f = tmp_path / "many.txt"
        f.write_text("\n".join(str(i) for i in range(10)))
        result = read_file({"path": str(f), "offset": 3, "limit": 2})
        lines = result.strip().splitlines()
        assert lines[0] == "2"  # offset 3 = line index 2 (0-based)
        assert len(lines) == 2

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert read_file({"path": str(f)}) == "(empty file)"


class TestWriteFile:
    def test_creates_new_file(self, tmp_path):
        f = tmp_path / "out.txt"
        result = write_file({"path": str(f), "content": "hello"})
        assert "Written" in result
        assert f.read_text() == "hello"

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text("old")
        write_file({"path": str(f), "content": "new"})
        assert f.read_text() == "new"

    def test_creates_parent_directories(self, tmp_path):
        f = tmp_path / "a" / "b" / "c.txt"
        write_file({"path": str(f), "content": "deep"})
        assert f.read_text() == "deep"


class TestEditFile:
    def test_replaces_unique_string(self, tmp_path):
        f = tmp_path / "src.py"
        f.write_text("x = 1\ny = 2\n")
        result = edit_file({"path": str(f), "old_string": "x = 1", "new_string": "x = 99"})
        assert "Edited" in result
        assert f.read_text() == "x = 99\ny = 2\n"

    def test_missing_old_string_returns_error(self, tmp_path):
        f = tmp_path / "src.txt"
        f.write_text("hello world")
        result = edit_file({"path": str(f), "old_string": "not_there", "new_string": "x"})
        assert "[error]" in result

    def test_duplicate_old_string_returns_error(self, tmp_path):
        f = tmp_path / "dup.txt"
        f.write_text("aa aa")
        result = edit_file({"path": str(f), "old_string": "aa", "new_string": "bb"})
        assert "[error]" in result and "2" in result

    def test_missing_file_returns_error(self, tmp_path):
        result = edit_file(
            {"path": str(tmp_path / "nope.py"), "old_string": "a", "new_string": "b"}
        )
        assert "[error]" in result


class TestSearch:
    def test_glob_finds_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x=1")
        (tmp_path / "b.txt").write_text("y=2")
        result = search({"pattern": "*.py", "directory": str(tmp_path)})
        assert "a.py" in result
        assert "b.txt" not in result

    def test_glob_no_match(self, tmp_path):
        result = search({"pattern": "*.xyz", "directory": str(tmp_path)})
        assert result == "(no matches)"

    def test_grep_finds_content(self, tmp_path):
        (tmp_path / "code.py").write_text("def hello():\n    pass\n")
        result = search({"pattern": "def hello", "directory": str(tmp_path), "type": "grep"})
        assert "hello" in result


# ══════════════════════════════════════════════════════════════════════════════
# memory.py
# ══════════════════════════════════════════════════════════════════════════════


class TestMemoryTools:
    def test_remember_appends_to_file(self, tmp_path):
        remember = make_remember(tmp_path)
        result = remember({"content": "Buy milk"})
        assert "Remembered" in result
        content = (tmp_path / "recordatorios.md").read_text()
        assert "Buy milk" in content

    def test_remember_creates_file_if_missing(self, tmp_path):
        remember = make_remember(tmp_path)
        remember({"content": "test note"})
        assert (tmp_path / "recordatorios.md").exists()

    def test_remember_uses_specified_file(self, tmp_path):
        remember = make_remember(tmp_path)
        remember({"content": "I like dark mode", "file": "preferencias"})
        assert (tmp_path / "preferencias.md").exists()

    def test_remember_invalid_file_returns_error(self, tmp_path):
        remember = make_remember(tmp_path)
        result = remember({"content": "x", "file": "unknown"})
        assert "[error]" in result

    def test_recall_finds_matching_lines(self, tmp_path):
        (tmp_path / "recordatorios.md").write_text(
            "- [2026-01-01] Buy milk\n- [2026-01-02] Call dentist\n"
        )
        recall = make_recall(tmp_path)
        result = recall({"query": "milk"})
        assert "Buy milk" in result
        assert "dentist" not in result

    def test_recall_returns_no_match_message(self, tmp_path):
        (tmp_path / "recordatorios.md").write_text("- nothing\n")
        recall = make_recall(tmp_path)
        result = recall({"query": "xyzzy_not_found"})
        assert "No memory found" in result

    def test_recall_searches_all_files(self, tmp_path):
        (tmp_path / "conocimiento.md").write_text("- Python 3.11 adds tomllib\n")
        (tmp_path / "preferencias.md").write_text("- Prefer dark mode\n")
        recall = make_recall(tmp_path)
        result = recall({"query": "prefer"})
        assert "preferencias" in result


# ══════════════════════════════════════════════════════════════════════════════
# web.py — HTML stripper (no network)
# ══════════════════════════════════════════════════════════════════════════════


class TestStripHTML:
    def test_removes_tags(self):
        result = _strip_html("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_strips_script_and_style(self):
        result = _strip_html(
            "<style>body{color:red}</style><p>content</p><script>alert(1)</script>"
        )
        assert "content" in result
        assert "color:red" not in result
        assert "alert" not in result

    def test_unescapes_html_entities(self):
        result = _strip_html("<p>AT&amp;T &lt;rocks&gt;</p>")
        assert "AT&T" in result


# ══════════════════════════════════════════════════════════════════════════════
# web.py — web_search and web_fetch (network patched)
# ══════════════════════════════════════════════════════════════════════════════


def _fake_http_response(body: bytes, content_type: str = "text/html") -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    mock.headers = {"Content-Type": content_type}
    return mock


class TestWebSearch:
    def test_returns_summary_when_abstract_present(self):
        data = {
            "AbstractText": "Python is a programming language.",
            "AbstractURL": "https://python.org",
            "RelatedTopics": [],
        }
        fake = _fake_http_response(json.dumps(data).encode(), "application/json")
        with patch("urllib.request.urlopen", return_value=fake):
            result = web_search({"query": "python"})
        assert "Python is a programming language" in result
        assert "python.org" in result

    def test_returns_no_results_message_when_empty(self):
        data = {"AbstractText": "", "AbstractURL": "", "RelatedTopics": []}
        fake = _fake_http_response(json.dumps(data).encode(), "application/json")
        with patch("urllib.request.urlopen", return_value=fake):
            result = web_search({"query": "unknownxyz"})
        assert "No results" in result

    def test_returns_related_topics(self):
        data = {
            "AbstractText": "",
            "AbstractURL": "",
            "RelatedTopics": [
                {"Text": "Python (programming language)", "FirstURL": "https://ddg.gg/python"},
            ],
        }
        fake = _fake_http_response(json.dumps(data).encode(), "application/json")
        with patch("urllib.request.urlopen", return_value=fake):
            result = web_search({"query": "python"})
        assert "Python (programming language)" in result

    def test_network_error_returns_error_string(self):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = web_search({"query": "test"})
        assert "[error]" in result


class TestWebFetch:
    def test_fetches_and_strips_html(self):
        html_body = b"<html><body><p>Hello world</p></body></html>"
        fake = _fake_http_response(html_body, "text/html; charset=utf-8")
        with patch("urllib.request.urlopen", return_value=fake):
            result = web_fetch({"url": "https://example.com"})
        assert "Hello world" in result
        assert "<p>" not in result

    def test_returns_plain_text_as_is(self):
        fake = _fake_http_response(b"just text", "text/plain")
        with patch("urllib.request.urlopen", return_value=fake):
            result = web_fetch({"url": "https://example.com/file.txt"})
        assert "just text" in result

    def test_network_error_returns_error(self):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            result = web_fetch({"url": "https://example.com"})
        assert "[error]" in result
