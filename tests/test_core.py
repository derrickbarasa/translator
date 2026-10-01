import pytest

from backends import Backend, GoogleFree, RateLimited
from core import Cache, chunk_text, translate_text


class Fake(Backend):
    name = "fake"
    max_chars = 20

    def __init__(self):
        self.calls = []

    def translate(self, text, source, target):
        self.calls.append(text)
        return text.upper()


@pytest.mark.parametrize("text", [
    "", "short", "a\nb\nc\n", "x" * 25, "word " * 30, "line one\n" + "y" * 50 + "\nend", "日本語" * 20,
])
def test_chunks_roundtrip_and_respect_limit(text):
    chunks = chunk_text(text, 10)
    assert "".join(chunks) == text
    assert all(len(c) <= 10 for c in chunks)


def test_chunk_prefers_whitespace():
    assert chunk_text("hello world again", 12) == ["hello world ", "again"]


def test_translate_text_caches(tmp_path):
    cache = Cache(str(tmp_path / "c.sqlite"))
    backend = Fake()
    assert translate_text("hello\n\nworld", "auto", "ja", backend, cache) == "HELLO\n\nWORLD"
    first = len(backend.calls)
    assert translate_text("hello\n\nworld", "auto", "ja", backend, cache) == "HELLO\n\nWORLD"
    assert len(backend.calls) == first
    # different target must not reuse the cached value
    translate_text("hello", "auto", "fr", backend, cache)
    assert len(backend.calls) == first + 1


def test_cache_persists(tmp_path):
    path = str(tmp_path / "c.sqlite")
    Cache(path).set("k", "v")
    assert Cache(path).get("k") == "v"


def test_google_retries_then_raises(monkeypatch):
    from deep_translator.exceptions import TooManyRequests

    attempts = []

    class Boom:
        def __init__(self, **kw):
            pass

        def translate(self, text):
            attempts.append(1)
            raise TooManyRequests()

    monkeypatch.setattr("backends.GoogleTranslator", Boom)
    monkeypatch.setattr("backends.time.sleep", lambda s: None)
    with pytest.raises(RateLimited):
        GoogleFree(retries=2).translate("hi", "auto", "ja")
    assert len(attempts) == 3
