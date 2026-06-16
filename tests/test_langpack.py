"""Tests for the reusable language-pack map (mirach.langpack)."""

from mirach import langpack

REQUIRED_KEYS = {"whisper_model", "whisper_lang", "locale", "voice", "voice_url"}


def test_spanish_pack():
    pack = langpack.pack_for("es")
    assert pack["whisper_model"] == "medium"
    assert pack["whisper_lang"] == "es"
    assert pack["locale"] == "es"
    assert pack["voice"] == "es_MX-ald-medium.onnx"
    assert pack["voice_url"].endswith("es_MX-ald-medium.onnx")


def test_english_pack():
    pack = langpack.pack_for("en")
    assert pack["whisper_model"] == "medium.en"
    assert pack["whisper_lang"] == "en"
    assert pack["locale"] == "en"
    assert pack["voice"] == "en_US-lessac-low.onnx"
    assert pack["voice_url"].endswith("en_US-lessac-low.onnx")


def test_unknown_lang_falls_back_to_english():
    assert langpack.pack_for("xx") == langpack.pack_for("en")


def test_every_pack_has_all_keys():
    for code in langpack.LANGUAGE_PACKS:
        assert set(langpack.pack_for(code)) == REQUIRED_KEYS


def test_pack_for_returns_a_copy():
    pack = langpack.pack_for("en")
    pack["voice"] = "mutated.onnx"
    # Mutating the returned dict must not corrupt the shared table.
    assert langpack.LANGUAGE_PACKS["en"]["voice"] == "en_US-lessac-low.onnx"
