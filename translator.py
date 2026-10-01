"""Interactive translator: Panel web UI plus a small CLI.

Web UI:  panel serve translator.py --show
CLI:     python translator.py "I am learning python" --to ja
"""
import argparse
import io
import json
import sys

from deep_translator import GoogleTranslator

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from backends import BACKENDS, RateLimited, get_backend
from core import detect_language, translate_text
from files import SUPPORTED, translate_file

FALLBACK_LANGUAGES = {"english": "en", "japanese": "ja", "french": "fr", "spanish": "es", "german": "de"}
HISTORY_LIMIT = 20
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
def build_app():
    import panel as pn

    pn.extension()

    languages = load_languages()
    code_to_name = {c: n.title() for n, c in languages.items()}
    source_options = {"Auto-detect": "auto", **{n.title(): c for n, c in languages.items()}}
    target_options = {n.title(): c for n, c in languages.items()}
    default_target = "ja" if "ja" in target_options.values() else next(iter(target_options.values()))

    backend_select = pn.widgets.Select(name="Engine", options=list(BACKENDS), value=next(iter(BACKENDS)), width=240)
    source_lang = pn.widgets.Select(name="Source Language", options=source_options, value="auto", width=220)
    swap_btn = pn.widgets.Button(name="⇄", width=50, align="end", description="Swap source and target")
    target_langs = pn.widgets.MultiChoice(
        name="Target Language(s)", options=target_options, value=[default_target], width=320
    )
    live_toggle = pn.widgets.Checkbox(name="Live translate", value=False)
    annotate_toggle = pn.widgets.Checkbox(name="Add reading & notes (Claude only)", value=False)

    input_text = pn.widgets.TextAreaInput(
        name="Enter Text to Translate",
        placeholder="Type or paste text here...",
        height=150,
        sizing_mode="stretch_width",
        max_width=700,
    )
    mic_btn = pn.widgets.Button(name="🎤 Dictate", width=110, description="Speak instead of typing (browser feature)")
    mic_btn.js_on_click(
        args={"inp": input_text, "src": source_lang, "codes": source_options},
        code="""
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) { alert('Voice input is not supported in this browser.'); return; }
        const r = new SR();
        const code = codes[src.value];
        if (code && code !== 'auto') r.lang = code;
        r.onresult = (e) => { inp.value = (inp.value ? inp.value + ' ' : '') + e.results[0][0].transcript; };
        r.start();
        """,
    )
    counter = pn.bind(lambda v: f"<small>{len(v):,} characters</small>", input_text.param.value_input)
    translate_btn = pn.widgets.Button(name="Translate", button_type="primary", width=150)

    status = pn.pane.Markdown("", sizing_mode="stretch_width", max_width=700)
    detected = pn.pane.Markdown("", sizing_mode="stretch_width", max_width=700)
    results = pn.Tabs(sizing_mode="stretch_width", max_width=700)
    placeholder = "### Translation will appear here..."
    status.object = placeholder

    state = {"detected_code": None, "token": 0}
    history = []
    history_box = pn.Column(sizing_mode="stretch_width", max_width=700)

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
    def run_translation(text, source, targets, backend):
        panels = []
        for code in targets:
            translated = translate_text(text, source, code, backend)
            note = ""
            if annotate_toggle.value and hasattr(backend, "annotate"):
                try:
                    note = backend.annotate(text, translated, code)
                except Exception as e:  # notes are a bonus; never fail the translation over them
                    print(f"Annotation error: {e}")
            panels.append((code_to_name.get(code, code), result_panel(code, translated, note), code, translated))
        return panels

    def do_translate(event=None):
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

        translate_btn.disabled = True
        translate_btn.name = "Translating..."
        try:
            source = source_lang.value
            panels = run_translation(text, source, targets, backend)
            results[:] = [(name, panel) for name, panel, _, _ in panels]
            status.object = ""
            state["detected_code"] = detect_language(text) if source == "auto" else None
            if state["detected_code"]:
                det = state["detected_code"]
                detected.object = f"Detected language: **{code_to_name.get(det, det)}**"
            else:
                detected.object = ""
            _, _, code, translated = panels[0]
            add_history(text, source, targets, translated)
        except RateLimited:
            status.object = "⏳ The translation service is rate-limiting requests. Please wait a minute and try again."
        except Exception as e:
            status.object = f"❌ Translation failed ({type(e).__name__}). Please try again."
            print(f"Translation error: {e}")
        finally:
            translate_btn.disabled = False
            translate_btn.name = "Translate"

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

        def fire():
            if token == state["token"]:
                do_translate()

        pn.state.add_periodic_callback(fire, period=LIVE_DEBOUNCE_MS, count=1)

    input_text.param.watch(on_typing, "value_input")

    # ---- history ----
    def add_history(text, source, targets, translated):
        history.insert(0, {"text": text, "source": source, "targets": targets, "out": translated})
        del history[HISTORY_LIMIT:]
        refresh_history()

    def restore(entry):
        source_lang.value = entry["source"]
        target_langs.value = entry["targets"]
        input_text.value = entry["text"]

    def refresh_history():
        rows = []
        for entry in history:
            label = entry["text"].replace("\n", " ")
            btn = pn.widgets.Button(name=f"{label[:45]}{'…' if len(label) > 45 else ''}  →  {entry['out'][:30]}",
                                    button_type="light", sizing_mode="stretch_width")
            btn.on_click(lambda event, e=entry: restore(e))
            rows.append(btn)
        history_box[:] = rows or [pn.pane.Markdown("_No translations yet._")]

    clear_history_btn = pn.widgets.Button(name="Clear history", button_type="light", width=120)
    clear_history_btn.on_click(lambda event: (history.clear(), refresh_history()))
    refresh_history()

    # ---- file translation ----
    file_input = pn.widgets.FileInput(accept=",".join(SUPPORTED), multiple=False)
    file_btn = pn.widgets.Button(name="Translate file", button_type="success", width=150)
    download = pn.widgets.FileDownload(label="Download translated file", button_type="primary",
                                       disabled=True, auto=False, embed=False, width=220)
    file_status = pn.pane.Markdown("", sizing_mode="stretch_width", max_width=700)

    def do_file(event):
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
        try:
            source, target = source_lang.value, targets[0]
            name, data = translate_file(
                file_input.filename, file_input.value, lambda s: translate_text(s, source, target, backend)
            )
            download.file = io.BytesIO(data)
            download.filename = name
            download.disabled = False
            file_status.object = f"✅ Done ({code_to_name.get(target, target)}). Use the download button."
        except RateLimited:
            file_status.object = "⏳ Rate-limited. Please wait a minute and try again."
        except Exception as e:
            file_status.object = f"❌ File translation failed: {e}"
            print(f"File translation error: {e}")
        finally:
            file_btn.disabled = False
            file_btn.name = "Translate file"

    file_btn.on_click(do_file)

    # ---- layout ----
    return pn.Column(
        "## 🌐 Interactive Translator",
        backend_select,
        pn.Row(source_lang, swap_btn, target_langs),
        pn.Row(live_toggle, annotate_toggle),
        input_text,
        pn.Row(mic_btn, pn.pane.HTML(counter, align="center")),
        translate_btn,
        detected,
        status,
        results,
        pn.layout.Divider(),
        pn.Accordion(
            ("History", pn.Column(history_box, clear_history_btn)),
            ("Translate a file (.txt / .srt / .docx)",
             pn.Column(file_input, pn.Row(file_btn, download), file_status)),
            sizing_mode="stretch_width", max_width=700,
        ),
        sizing_mode="stretch_width",
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
    return 0


if __name__ == "__main__":
    sys.exit(cli())
else:
    # `panel serve translator.py` imports this module; make the app servable.
    build_app().servable()
