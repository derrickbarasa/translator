import asyncio
import os

os.environ["TRANSLATOR_NO_AUTOSERVE"] = "1"

import panel as pn  # noqa: E402

import translator  # noqa: E402


def test_build_app_smoke(monkeypatch):
    monkeypatch.setattr(translator, "load_languages", lambda: {"english": "en", "japanese": "ja"})
    app = translator.build_app()
    assert isinstance(app, pn.template.FastListTemplate)


def test_run_with_progress_reports_and_hides_bar():
    bar = pn.indicators.Progress(value=0, max=100, visible=False)

    def work(tick):
        for _ in range(3):
            tick()
        return "ok"

    assert asyncio.run(translator.run_with_progress(work, bar, 3)) == "ok"
    assert bar.visible is False


def test_run_with_progress_propagates_errors():
    bar = pn.indicators.Progress(value=-1, visible=False)

    def work(tick):
        raise ValueError("boom")

    try:
        asyncio.run(translator.run_with_progress(work, bar, None))
    except ValueError:
        assert bar.visible is False
    else:
        raise AssertionError("expected ValueError")
