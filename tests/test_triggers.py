"""Tests for word-boundary trigger matching (no substring false positives)."""

from pathlib import Path

from mirach.assistant import Assistant, UserScript


def test_phrase_in_word_boundary():
    assert Assistant._phrase_in("api", "consulta la api del clima")
    assert Assistant._phrase_in("ver conversación", "quiero ver conversación ahora")
    # Substring inside a longer word must NOT match.
    assert not Assistant._phrase_in("api", "esto es muy rápido")
    assert not Assistant._phrase_in("test", "el contexto importa")
    assert not Assistant._phrase_in("", "cualquier texto")


def test_match_user_script_no_substring_false_positive():
    asst = Assistant()
    asst._user_scripts = [
        UserScript(path=Path("/tmp/x.sh"), triggers=["api"], response="ok"),
    ]
    assert asst._match_user_script("dame la api") is not None
    assert asst._match_user_script("habla más rápido") is None


def test_match_builtin_trigger_word_boundary():
    asst = Assistant()
    matched = asst._match_builtin_trigger("por favor muestra la conversación")
    assert matched is not None
    assert matched[1] == "conversation"
    assert asst._match_builtin_trigger("dime algo interesante") is None
