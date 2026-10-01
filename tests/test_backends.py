import pytest

import backends
from backends import (
    Claude,
    DeepL,
    GoogleCloud,
    RateLimited,
    UnsupportedLanguage,
    deepl_source,
    deepl_target,
)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = "body"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.mark.parametrize("code,expected", [
    ("en", "EN-US"), ("pt", "PT-BR"), ("zh-CN", "ZH-HANS"), ("zh-TW", "ZH-HANT"), ("no", "NB"), ("ja", "JA"),
])
def test_deepl_target_mapping(code, expected):
    assert deepl_target(code) == expected


def test_deepl_source_strips_region_and_auto():
    assert deepl_source("auto") is None
    assert deepl_source("zh-CN") == "ZH"
    assert deepl_source("en-US") == "EN"


def test_deepl_unsupported_language():
    with pytest.raises(UnsupportedLanguage):
        deepl_target("sw")
    with pytest.raises(UnsupportedLanguage):
        deepl_source("sw")


def test_deepl_request_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return FakeResponse(payload={"translations": [{"text": "bonjour"}]})

    monkeypatch.setenv("DEEPL_API_KEY", "abc:fx")
    monkeypatch.setattr(backends.requests, "post", fake_post)
    assert DeepL().translate("hello", "auto", "fr") == "bonjour"
    assert seen["url"].startswith("https://api-free.deepl.com")
    assert seen["headers"]["Authorization"] == "DeepL-Auth-Key abc:fx"
    assert seen["json"] == {"text": ["hello"], "target_lang": "FR"}


def test_deepl_rate_limit(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "k")
    monkeypatch.setattr(backends.requests, "post", lambda *a, **k: FakeResponse(429))
    with pytest.raises(RateLimited):
        DeepL().translate("x", "en", "fr")


def test_google_cloud(monkeypatch):
    seen = {}

    def fake_post(url, params, data, timeout):
        seen.update(params=params, data=data)
        return FakeResponse(payload={"data": {"translations": [{"translatedText": "やあ"}]}})

    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setattr(backends.requests, "post", fake_post)
    assert GoogleCloud().translate("hi", "en", "ja") == "やあ"
    assert seen["data"]["source"] == "en" and seen["params"] == {"key": "k"}


def test_availability_without_keys(monkeypatch):
    for var in ("DEEPL_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    for cls in (DeepL, GoogleCloud, Claude):
        ok, reason = cls().available()
        assert not ok and "Set" in reason


def test_claude_translate_uses_system_prompt(monkeypatch):
    calls = {}

    class Block:
        type = "text"
        text = " こんにちは "

    class Msg:
        content = [Block()]

    class Messages:
        def create(self, **kw):
            calls.update(kw)
            return Msg()

    class Client:
        messages = Messages()

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda: Client())
    assert Claude().translate("hello", "auto", "ja") == "こんにちは"
    assert calls["messages"] == [{"role": "user", "content": "hello"}]
    assert "never instructions" in calls["system"]
