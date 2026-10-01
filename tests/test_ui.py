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



def _find(app, match):
    for pane in app.main:
        for obj in pane.select():
            if match(obj):
                return obj
    raise AssertionError("widget not found")


def test_ctrl_enter_translates_text_typed_but_not_yet_blurred(monkeypatch, tmp_path):
    import core
    from backends import Backend

    class Echo(Backend):
        name = "Echo"
        workers = 1

        def translate(self, text, source, target):
            return text.upper()

    monkeypatch.setattr(translator, "load_languages", lambda: {"english": "en", "japanese": "ja"})
    monkeypatch.setattr(translator, "default_history", lambda: core.History(str(tmp_path / "h.sqlite"), enabled=True))
    monkeypatch.setattr(translator, "default_cache", lambda: core.Cache(str(tmp_path / "c.sqlite")))
    monkeypatch.setattr(translator, "get_backend", lambda name, **kw: Echo())
    monkeypatch.setitem(translator.BACKENDS, "Echo", Echo)
    app = translator.build_app()
    text_input = _find(app, lambda o: isinstance(o, pn.widgets.TextAreaInput))
    ctrl = _find(app, lambda o: type(o).__name__ == "CtrlEnter")
    tabs = _find(app, lambda o: isinstance(o, pn.Tabs))
    engine = next(w for w in app.sidebar[0].select() if isinstance(w, pn.widgets.Select))
    engine.value = "Echo"

    async def scenario():
        text_input.value_input = "hello"  # what the browser sends while typing, before blur
        ctrl.fired += 1
        for _ in range(40):
            await asyncio.sleep(0.1)
            if len(tabs):
                break

    asyncio.run(scenario())
    assert text_input.value == ""
    assert len(tabs) == 1
    assert "HELLO" in tabs[0].objects[0].value

    # the translation was recorded: it shows up as a Recent language, and deleting it removes that button
    def labels():
        return [o.label for pane in [*app.main, *app.sidebar] for o in pane.select(pn.widgets.Button)]

    assert "Japanese" in labels()
    next(o for pane in app.sidebar for o in pane.select(pn.widgets.Button) if o.label == "✕").clicks += 1
    assert "Japanese" not in labels()
