"""Tests for the markdown stripper used before sending text to TTS."""

from mirach.llm_types import _strip_markdown


def test_passthrough_plain_text():
    assert _strip_markdown("Hola, esto es una prueba.") == "Hola, esto es una prueba."


def test_strips_bold_and_italic():
    assert _strip_markdown("**bold** and *italic*") == "bold and italic"


def test_strips_inline_code():
    assert _strip_markdown("run `ls -la` now") == "run ls -la now"


def test_drops_code_blocks_entirely():
    txt = "intro\n```python\ndef f():\n    pass\n```\nouter"
    cleaned = _strip_markdown(txt)
    assert "def f" not in cleaned
    assert "intro" in cleaned and "outer" in cleaned


def test_strips_headers():
    assert _strip_markdown("# Title\nbody") == "Title\nbody"


def test_strips_link_markup_keeps_text():
    assert _strip_markdown("see [the docs](https://example.com) please") == "see the docs please"


def test_strips_bullets():
    txt = "- one\n- two\n- three"
    assert _strip_markdown(txt) == "one\ntwo\nthree"


def test_strips_numbered_lists():
    txt = "1. one\n2. two"
    assert _strip_markdown(txt) == "one\ntwo"


def test_collapses_whitespace():
    assert _strip_markdown("a    b\t\tc") == "a b c"
