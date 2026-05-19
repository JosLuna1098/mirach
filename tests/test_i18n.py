"""Tests for the lightweight i18n layer."""

import importlib


def _reload_i18n(monkeypatch, locale: str | None = None, fillers: str | None = None):
    """Reload mirach.i18n with given env vars and return the fresh module."""
    if locale is None:
        monkeypatch.delenv("MIRACH_LOCALE", raising=False)
    else:
        monkeypatch.setenv("MIRACH_LOCALE", locale)
    if fillers is None:
        monkeypatch.delenv("MIRACH_FILLERS", raising=False)
    else:
        monkeypatch.setenv("MIRACH_FILLERS", fillers)
    import mirach.i18n as mod

    return importlib.reload(mod)


def test_default_locale_is_english(monkeypatch):
    i18n = _reload_i18n(monkeypatch)
    assert i18n.LOCALE == "en"
    assert i18n.t("nothing_recorded") == "Nothing was recorded."


def test_spanish_locale(monkeypatch):
    i18n = _reload_i18n(monkeypatch, locale="es")
    assert i18n.t("nothing_recorded") == "No grabé nada."


def test_unknown_locale_falls_back_to_english(monkeypatch):
    i18n = _reload_i18n(monkeypatch, locale="zz")
    assert i18n.t("nothing_recorded") == "Nothing was recorded."


def test_fillers_match_locale(monkeypatch):
    i18n = _reload_i18n(monkeypatch, locale="es")
    fillers = i18n.fillers()
    assert "Un momento." in fillers


def test_fillers_env_override(monkeypatch):
    i18n = _reload_i18n(monkeypatch, locale="en", fillers="foo|bar|baz")
    assert i18n.fillers() == ["foo", "bar", "baz"]


def test_fillers_env_override_ignores_empty(monkeypatch):
    i18n = _reload_i18n(monkeypatch, locale="en", fillers="foo||  |bar")
    assert i18n.fillers() == ["foo", "bar"]
