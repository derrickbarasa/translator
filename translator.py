"""Interactive translator: Panel web UI plus a small CLI.

Web UI:  panel serve translator.py --show
CLI:     python translator.py "I am learning python" --to ja
"""
import argparse
import asyncio
import io
import json
import os
import sys
import threading

from deep_translator import GoogleTranslator

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from backends import BACKENDS, EngineError, RateLimited, UnsupportedLanguage, get_backend
from core import annotate_cached, chunk_text, default_cache, default_history, detect_language, translate_text
from files import SUPPORTED, translate_file

FALLBACK_LANGUAGES = {"english": "en", "japanese": "ja", "french": "fr", "spanish": "es", "german": "de"}
HISTORY_LIMIT = 20  # entries shown in the sidebar
LIVE_DEBOUNCE_MS = 800


def load_languages():
    """name -> code from Google's list, with a small fallback if offline."""
    try:
        return GoogleTranslator().get_supported_languages(as_dict=True)
    except Exception:
        return FALLBACK_LANGUAGES


def demo():
    """Static translations printed to the terminal."""
    backend = get_backend("Google (free, unofficial)")
    samples = [
        ("お元気ですか", "en"),
        ("Tell me who doesn't love baby yoda from mandalorian?\nBaby yoda has shaken me like soda.\n", "ja"),
        ("I am learning python", "ja"),
    ]
    for text, target in samples:
        print(f"Original: {text!r} | Translated: {translate_text(text, 'auto', target, backend)!r}")


# ---------------- Panel Interactive Translator ----------------
async def run_with_progress(work, bar, total):
    """Run `work(tick)` in a worker thread so the UI stays responsive, mirroring progress on `bar`.

    `total` is the number of expected tick() calls, or None for an indeterminate bar.
    Widgets are only touched here on the event loop, never from the worker thread.
    """
    done = {"n": 0}
    lock = threading.Lock()

    def tick():
        with lock:  # translate_text may tick from several worker threads
            done["n"] += 1

    if total:
        bar.max, bar.value = total, 0
    else:
        bar.value = -1
    bar.active, bar.visible = True, True
    task = asyncio.create_task(asyncio.to_thread(work, tick))
    try:
        while not task.done():
            if total:
                bar.value = min(done["n"], total)
            await asyncio.sleep(0.15)
        return await task
    finally:
        bar.visible, bar.active = False, False


def build_app():
    import panel as pn

    pn.extension()

    languages = load_languages()
    code_to_name = {c: n.title() for n, c in languages.items()}
    source_options = {"Auto-detect": "auto", **{n.title(): c for n, c in languages.items()}}
    target_options = {n.title(): c for n, c in languages.items()}
    default_target = "ja" if "ja" in target_options.values() else next(iter(target_options.values()))

    # ---- settings (sidebar) ----
    backend_select = pn.widgets.Select(name="Engine", options=list(BACKENDS), value=next(iter(BACKENDS)))
    live_toggle = pn.widgets.Checkbox(name="Live translate", value=False)
    annotate_toggle = pn.widgets.Checkbox(name="Reading & notes (Claude only)", value=False)

    # ---- inputs ----
    source_lang = pn.widgets.Select(name="From", options=source_options, value="auto", width=200)
    swap_btn = pn.widgets.Button(name="⇄", width=50, align="end", description="Swap source and target")
    target_langs = pn.widgets.MultiChoice(
        name="To", options=target_options, value=[default_target], sizing_mode="stretch_width", min_width=200
    )
    input_text = pn.widgets.TextAreaInput(
        name="Text", placeholder="Type or paste text here...", height=260, sizing_mode="stretch_width"
    )
    status = pn.pane.Markdown("_Translation will appear here._", sizing_mode="stretch_width")
    mic_btn = pn.widgets.Button(name="🎤 Dictate", width=110, description="Speak instead of typing (browser feature)")
    mic_btn.js_on_click(
        args={"inp": input_text, "src": source_lang, "codes": source_options, "status": status},
        code="""
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) { status.object = '⚠️ Voice input is not supported in this browser.'; return; }
        const r = new SR();
        const code = codes[src.value];
        if (code && code !== 'auto') r.lang = code;
        r.onresult = (e) => { inp.value = (inp.value ? inp.value + ' ' : '') + e.results[0][0].transcript; };
        r.start();
        """,
    )
    counter = pn.bind(lambda v: f"<small>{len(v):,} characters</small>", input_text.param.value_input)
    translate_btn = pn.widgets.Button(name="Translate", color="primary", width=150)

    # ---- outputs ----
    progress = pn.indicators.Progress(value=0, max=100, visible=False, active=False, sizing_mode="stretch_width")
    detected = pn.pane.Markdown("", sizing_mode="stretch_width")
    results = pn.Tabs(sizing_mode="stretch_width")

    state = {"detected_code": None, "token": 0, "busy": False, "rerun": False}
    history = default_history()
    history_box = pn.Column(sizing_mode="stretch_width")

    # ---- result panels (copy + speak run in the browser) ----
    def result_panel(lang_code, text, note=""):
        height = max(120, min(400, 24 * (text.count("\n") + 3)))
        area = pn.widgets.TextAreaInput(value=text, disabled=True, height=height, sizing_mode="stretch_width")
        copy_btn = pn.widgets.Button(name="📋 Copy", width=100)
        copy_btn.js_on_click(args={"out": area}, code="navigator.clipboard.writeText(out.value);")
        speak_btn = pn.widgets.Button(name="🔊 Speak", width=100)
        speak_btn.js_on_click(
            args={"out": area},
            code=f"""
            const u = new SpeechSynthesisUtterance(out.value);
            u.lang = {json.dumps(lang_code)};
            speechSynthesis.cancel(); speechSynthesis.speak(u);
            """,
        )
        parts = [area, pn.Row(copy_btn, speak_btn)]
        if note:
            parts.append(pn.pane.Markdown(note, sizing_mode="stretch_width"))
        return pn.Column(*parts, sizing_mode="stretch_width")

    def check_backend():
        backend = get_backend(backend_select.value)
        ok, reason = backend.available()
        return backend, ok, reason

    # ---- main translate action ----
    async def do_translate(event=None):
        if state["busy"]:
            state["rerun"] = True  # text changed mid-flight; translate again once this one finishes
            return
        text = input_text.value.strip()
        if not text:
            status.object = "⚠️ Please enter text to translate."
            return
        targets = list(target_langs.value)
        if not targets:
            status.object = "⚠️ Choose at least one target language."
            return
        backend, ok, reason = check_backend()
        if not ok:
            status.object = f"🔑 {backend.name} isn't configured: {reason} (see README)."
            return

        state["busy"] = True
        translate_btn.disabled = True
        translate_btn.name = "Translating..."
        source = source_lang.value
        want_notes = annotate_toggle.value and hasattr(backend, "annotate")

        def work(tick):
            out = []
            for code in targets:
                translated = translate_text(text, source, code, backend, on_chunk=tick)
                note = ""
                if want_notes:
                    try:
                        note = annotate_cached(backend, text, translated, code)
                    except Exception as e:  # notes are a bonus; never fail the translation over them
                        print(f"Annotation error: {e}")
                out.append((code, translated, note))
            return out, (detect_language(text) if source == "auto" else None)

        try:
            total = len(chunk_text(text, backend.max_chars)) * len(targets)
            out, detected_code = await run_with_progress(work, progress, total)
            results[:] = [(code_to_name.get(c, c), result_panel(c, t, n)) for c, t, n in out]
            status.object = ""
            state["detected_code"] = detected_code
            if detected_code:
                detected.object = f"Detected language: **{code_to_name.get(detected_code, detected_code)}**"
            else:
                detected.object = ""
            add_history(text, source, targets, out[0][1])
            refresh_cache_info()
        except RateLimited:
            status.object = "⏳ The translation service is rate-limiting requests. Please wait a minute and try again."
        except UnsupportedLanguage as e:
            status.object = f"⚠️ {e} Try a different engine or language."
        except EngineError as e:
            status.object = f"❌ {e}"
        except Exception as e:
            status.object = f"❌ Translation failed ({type(e).__name__}). Please try again."
            print(f"Translation error: {e}")
        finally:
            state["busy"] = False
            translate_btn.disabled = False
            translate_btn.name = "Translate"
        if state["rerun"]:
            state["rerun"] = False
            if live_toggle.value:
                await do_translate()

    translate_btn.on_click(do_translate)

    # ---- swap languages ----
    def do_swap(event):
        src = source_lang.value
        if src == "auto":
            src = state["detected_code"]
        if not src or src not in target_options.values():
            status.object = "⚠️ Can't swap while the source language is unknown. Pick a source language first."
            return
        old_target = target_langs.value[0] if target_langs.value else default_target
        output = results[0].objects[0].value if len(results) else ""
        source_lang.value = old_target
        target_langs.value = [src]
        if output:
            input_text.value = output

    swap_btn.on_click(do_swap)

    # ---- live translate (debounced) ----
    def on_typing(event):
        if not live_toggle.value or not event.new.strip():
            return
        state["token"] += 1
        token = state["token"]

        async def fire():
            if token == state["token"]:
                await do_translate()

        pn.state.add_periodic_callback(fire, period=LIVE_DEBOUNCE_MS, count=1)

    input_text.param.watch(on_typing, "value_input")

    # ---- history ----
    history_search = pn.widgets.TextInput(placeholder="Search history...", sizing_mode="stretch_width")

    def add_history(text, source, targets, translated):
        history.add(text, source, targets, translated)
        refresh_history()

    def restore(entry):
        source_lang.value = entry["source"]
        target_langs.value = [t for t in entry["targets"] if t in code_to_name] or target_langs.value
        input_text.value = entry["text"]

    def delete_entry(entry):
        history.delete(entry["id"])
        refresh_history()

    def refresh_history(*_):
        rows = []
        for entry in history.list(history_search.value_input, HISTORY_LIMIT):
            label = entry["text"].replace("\n", " ")
            btn = pn.widgets.Button(
                name=f"{label[:40]}{'…' if len(label) > 40 else ''}  →  {entry['out'][:25]}",
                color="light",
                sizing_mode="stretch_width",
            )
            btn.on_click(lambda event, e=entry: restore(e))
            remove = pn.widgets.Button(name="✕", color="light", width=40, description="Delete this entry")
            remove.on_click(lambda event, e=entry: delete_entry(e))
            rows.append(pn.Row(btn, remove, sizing_mode="stretch_width"))
        empty = "_No matches._" if history_search.value_input else "_No translations yet._"
        history_box[:] = rows or [pn.pane.Markdown(empty)]

    history_search.param.watch(refresh_history, "value_input")

    def clear_history(event):
        history.clear()
        refresh_history()

    clear_history_btn = pn.widgets.Button(name="Clear history", color="light", width=120)
    clear_history_btn.on_click(clear_history)

    cache_info = pn.pane.Markdown("")
    clear_cache_btn = pn.widgets.Button(name="Clear cache", color="light", width=120)

    def refresh_cache_info():
        cache_info.object = f"<small>{default_cache().count():,} cached translations</small>"

    def clear_cache(event):
        default_cache().clear()
        refresh_cache_info()

    clear_cache_btn.on_click(clear_cache)
    refresh_cache_info()
    refresh_history()

    # ---- file translation ----
    file_input = pn.widgets.FileInput(accept=",".join(SUPPORTED), multiple=False)
    file_btn = pn.widgets.Button(name="Translate file", color="success", width=150)
    download = pn.widgets.FileDownload(
        label="Download translated file", color="primary", disabled=True, auto=False, embed=False, width=220
    )
    file_progress = pn.indicators.Progress(value=-1, visible=False, active=False, sizing_mode="stretch_width")
    file_status = pn.pane.Markdown("", sizing_mode="stretch_width")

    async def do_file(event):
        if not file_input.value:
            file_status.object = "⚠️ Choose a .txt, .srt or .docx file first."
            return
        targets = list(target_langs.value)
        if not targets:
            file_status.object = "⚠️ Choose a target language."
            return
        backend, ok, reason = check_backend()
        if not ok:
            file_status.object = f"🔑 {backend.name} isn't configured: {reason}"
            return
        file_btn.disabled = True
        file_btn.name = "Translating..."
        source, target = source_lang.value, targets[0]
        filename, data = file_input.filename, file_input.value
        try:
            name, out = await run_with_progress(
                lambda tick: translate_file(
                    filename, data, lambda s: translate_text(s, source, target, backend, on_chunk=tick)
                ),
                file_progress,
                None,
            )
            download.file = io.BytesIO(out)
            download.filename = name
            download.disabled = False
            file_status.object = f"✅ Done ({code_to_name.get(target, target)}). Use the download button."
        except RateLimited:
            file_status.object = "⏳ Rate-limited. Please wait a minute and try again."
        except UnsupportedLanguage as e:
            file_status.object = f"⚠️ {e}"
        except EngineError as e:
            file_status.object = f"❌ {e}"
        except Exception as e:
            file_status.object = f"❌ File translation failed: {e}"
            print(f"File translation error: {e}")
        finally:
            file_btn.disabled = False
            file_btn.name = "Translate file"

    file_btn.on_click(do_file)

    # ---- layout: settings in the sidebar, input and output side by side (wraps on narrow screens) ----
    input_col = pn.Column(
        input_text,
        pn.Row(mic_btn, pn.pane.HTML(counter, align="center")),
        translate_btn,
        styles={"flex": "1 1 360px", "min-width": "0"},
    )
    output_col = pn.Column(
        progress, status, detected, results, styles={"flex": "1 1 360px", "min-width": "0"}
    )
    files_card = pn.Card(
        file_input,
        pn.Row(file_btn, download),
        file_progress,
        file_status,
        title="Translate a file (.txt / .srt / .docx)",
        collapsed=True,
        sizing_mode="stretch_width",
    )
    return pn.template.FastListTemplate(
        title="🌐 Translator",
        accent="#4a6cf7",
        sidebar_width=300,
        sidebar=[
            backend_select,
            live_toggle,
            annotate_toggle,
            pn.layout.Divider(),
            pn.pane.Markdown("**History**"),
            history_search,
            history_box,
            clear_history_btn,
            pn.layout.Divider(),
            cache_info,
            clear_cache_btn,
        ],
        main=[
            pn.Row(source_lang, swap_btn, target_langs, sizing_mode="stretch_width"),
            pn.FlexBox(input_col, output_col, flex_wrap="wrap", gap="16px", sizing_mode="stretch_width"),
            files_card,
        ],
    )


# ---------------- CLI ----------------
def cli(argv=None):
    parser = argparse.ArgumentParser(description="Translate text from the command line.")
    parser.add_argument("text", nargs="?", help="Text to translate (reads stdin if omitted and piped)")
    parser.add_argument("--to", dest="target", default="en", help="Target language code (default: en)")
    parser.add_argument("--from", dest="source", default="auto", help="Source language code (default: auto)")
    parser.add_argument("--engine", default=next(iter(BACKENDS)), choices=list(BACKENDS), help="Translation engine")
    parser.add_argument("--demo", action="store_true", help="Run the sample translations")
    args = parser.parse_args(argv)

    if args.demo or (args.text is None and sys.stdin.isatty()):
        demo()
        return 0
    text = args.text if args.text is not None else sys.stdin.read()
    backend = get_backend(args.engine)
    ok, reason = backend.available()
    if not ok:
        print(f"{backend.name} isn't configured: {reason}", file=sys.stderr)
        return 2
    try:
        print(translate_text(text, args.source, args.target, backend))
    except RateLimited:
        print("Rate-limited by the translation service; try again shortly.", file=sys.stderr)
        return 1
    except (EngineError, UnsupportedLanguage) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
elif not os.environ.get("TRANSLATOR_NO_AUTOSERVE"):
    # `panel serve translator.py` imports this module; make the app servable.
    build_app().servable()
