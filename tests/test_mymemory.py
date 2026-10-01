import pytest

import backends
from backends import EngineError, MyMemory, NetworkError, QuotaExceeded, UnsupportedLanguage


class FakeResponse:
    def __init__(self, body, http=200):
        self.body, self.http = body, http

    def raise_for_status(self):
        if self.http >= 400:
            raise backends.requests.HTTPError(str(self.http))

    def json(self):
        return self.body


def reply(text="", status=200, details=""):
    data = {"translatedText": text}
    return FakeResponse({"responseStatus": status, "responseDetails": details, "responseData": data})


def patch_get(monkeypatch, response):
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen["params"] = params
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(backends.requests, "get", fake_get)
    return seen


def test_translate_request_shape_and_unescape(monkeypatch):
    seen = patch_get(monkeypatch, reply("l&#39;eau"))
    assert MyMemory().translate("water", "en", "fr") == "l'eau"
    assert seen["params"] == {"q": "water", "langpair": "en|fr"}


def test_auto_source_uses_autodetect_and_email(monkeypatch):
    monkeypatch.setenv("MYMEMORY_EMAIL", "me@example.com")
    seen = patch_get(monkeypatch, reply("Bonjour"))
    MyMemory().translate("Hello", "auto", "fr")
    assert seen["params"]["langpair"] == "Autodetect|fr"
    assert seen["params"]["de"] == "me@example.com"


@pytest.mark.parametrize("response", [
    reply("MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY.", status=200),
    reply("", status=429, details="too many"),
])
def test_quota_is_reported_even_when_http_is_200(monkeypatch, response):
    patch_get(monkeypatch, response)
    with pytest.raises(QuotaExceeded):
        MyMemory().translate("x", "en", "fr")


def test_invalid_language_and_other_errors(monkeypatch):
    invalid = "'XX' IS AN INVALID TARGET LANGUAGE"
    patch_get(monkeypatch, reply(invalid, status=403, details=invalid))
    with pytest.raises(UnsupportedLanguage):
        MyMemory().translate("x", "en", "xx")
    patch_get(monkeypatch, reply("", status=500, details="boom"))
    with pytest.raises(EngineError, match="boom"):
        MyMemory().translate("x", "en", "fr")


def test_connection_error(monkeypatch):
    patch_get(monkeypatch, backends.requests.ConnectionError("down"))
    with pytest.raises(NetworkError):
        MyMemory().translate("x", "en", "fr")


def test_registered_and_keyless():
    assert MyMemory.name in backends.BACKENDS
    assert MyMemory().available() == (True, "")
    assert next(iter(backends.BACKENDS)) != MyMemory.name  # Google stays the default
    assert MyMemory.max_chars <= 500
