from deep_translator import GoogleTranslator
import panel as pn

MAX_CHARS = 4900  # Google's free endpoint rejects requests of ~5000+ chars


def demo():
    """Static translations printed to the terminal."""
    text1 = "お元気ですか"
    translated1 = GoogleTranslator(source="auto", target="en").translate(text1)
    print(f"Original: {text1} | Translated: {translated1}")

    mystory = """Tell me who doesn't love baby yoda from mandalorian?
Baby yoda has shaken me like soda.
"""
    translated2 = GoogleTranslator(source="auto", target="ja").translate(mystory)
    print("Original:\n" + mystory + "\nTranslated:\n" + translated2)

    text3 = "I am learning python"
    translated3 = GoogleTranslator(source="auto", target="ja").translate(text3)
    print(f"Original: {text3} | Translated: {translated3}")


def chunk_text(text, limit=MAX_CHARS):
    """Split text into pieces under `limit`, preferring line boundaries."""
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


def translate_text(text, source, target):
    parts = []
    for chunk in chunk_text(text):
        if not chunk.strip():
            parts.append(chunk)
            continue
        parts.append(GoogleTranslator(source=source, target=target).translate(chunk))
    return "".join(parts)


# ---------------- Panel Interactive Translator ----------------
pn.extension()

try:
    languages = GoogleTranslator().get_supported_languages(as_dict=True)  # name -> code
except Exception:
    languages = {"english": "en", "japanese": "ja", "french": "fr", "spanish": "es", "german": "de"}

source_options = {"Auto-detect": "auto", **{n.title(): c for n, c in languages.items()}}
target_options = {n.title(): c for n, c in languages.items()}

source_lang = pn.widgets.Select(name="Source Language", options=source_options, value="auto")
target_lang = pn.widgets.Select(
    name="Target Language",
    options=target_options,
    value="ja" if "ja" in target_options.values() else next(iter(target_options.values())),
)
input_text = pn.widgets.TextAreaInput(
    name="Enter Text to Translate",
    placeholder="Type or paste text here...",
    height=150,
    sizing_mode="stretch_width",
    max_width=700,
)
translate_btn = pn.widgets.Button(name="Translate", button_type="primary", width=150)
output_text = pn.pane.Markdown("### Translation will appear here...", sizing_mode="stretch_width", max_width=700)


def do_translate(event):
    text = input_text.value.strip()
    if not text:
        output_text.object = "⚠️ Please enter text to translate."
        return

    translate_btn.disabled = True
    translate_btn.name = "Translating..."
    try:
        translated = translate_text(text, source_lang.value, target_lang.value)
        output_text.object = f"### **Translated Text:**\n\n{translated}"
    except Exception as e:
        output_text.object = f"❌ Translation failed ({type(e).__name__}). Please try again."
        print(f"Translation error: {e}")
    finally:
        translate_btn.disabled = False
        translate_btn.name = "Translate"


translate_btn.on_click(do_translate)

app = pn.Column(
    "## 🌐 Interactive Translator",
    pn.Row(source_lang, target_lang),
    input_text,
    translate_btn,
    output_text,
    sizing_mode="stretch_width",
)

# Make servable for Panel (run with: panel serve translater.py)
app.servable()

if __name__ == "__main__":
    demo()
