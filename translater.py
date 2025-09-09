from deep_translator import GoogleTranslator
import panel as pn

# ---------------- Your Original Examples ----------------
# Static translations in the terminal
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

# ---------------- Panel Interactive Translator ----------------
pn.extension()

# Widgets
source_lang = pn.widgets.TextInput(name="Source Language", value="auto", placeholder="e.g. en, ja, fr, auto")
target_lang = pn.widgets.TextInput(name="Target Language", value="ja", placeholder="e.g. en, ja, fr")
input_text = pn.widgets.TextAreaInput(
    name="Enter Text to Translate",
    placeholder="Type or paste text here...",
    height=150,
    width=500
)
translate_btn = pn.widgets.Button(name="Translate", button_type="primary", width=150)
output_text = pn.pane.Markdown("### Translation will appear here...", width=500)

# Translation callback
def do_translate(event):
    text = input_text.value.strip()
    if not text:
        output_text.object = "⚠️ Please enter text to translate."
        return

    try:
        translated = GoogleTranslator(source=source_lang.value, target=target_lang.value).translate(text)
        output_text.object = f"### **Translated Text:**\n\n{translated}"
    except Exception as e:
        output_text.object = f"❌ Error: {e}"

translate_btn.on_click(do_translate)

# Panel layout
app = pn.Column(
    "## 🌐 Interactive Translator",
    pn.Row(source_lang, target_lang),
    input_text,
    translate_btn,
    output_text,
    sizing_mode="stretch_width"
)

# Make servable for Panel
app.servable()
