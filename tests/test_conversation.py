"""Tests for the per-session conversation log."""

from mirach import config
from mirach.conversation import ConversationLog


def test_start_creates_file_and_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONVERSATIONS_DIR", tmp_path)
    conv = ConversationLog()

    path = conv.start()

    assert path.exists()
    assert path.read_text().startswith("# Conversation ")
    latest = tmp_path / "latest.md"
    assert latest.is_symlink()
    assert (tmp_path / latest.readlink()).resolve() == path.resolve()


def test_append_writes_role_and_text(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONVERSATIONS_DIR", tmp_path)
    conv = ConversationLog()
    conv.start()
    conv.append("You", "hello")
    conv.append("Assistant", "hi there")

    content = conv.path.read_text()
    assert "**You**" in content
    assert "hello" in content
    assert "**Assistant**" in content
    assert "hi there" in content


def test_append_before_start_is_noop():
    """Calling append() without start() must not raise."""
    conv = ConversationLog()
    conv.append("You", "ignored")  # no path → silently skips


def test_start_replaces_existing_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONVERSATIONS_DIR", tmp_path)
    # Pre-existing symlink pointing nowhere
    stale = tmp_path / "latest.md"
    stale.symlink_to("does-not-exist.md")

    conv = ConversationLog()
    path = conv.start()

    latest = tmp_path / "latest.md"
    assert latest.is_symlink()
    assert (tmp_path / latest.readlink()).resolve() == path.resolve()
