# translator

An interactive text translator built with [Panel](https://panel.holoviz.org/), with pluggable
engines (free Google, MyMemory, Google Cloud, DeepL, Claude).

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # add keys only for the engines you want
```

## Run

Web UI:

```
panel serve translator.py --show
```

CLI:

```
python translator.py "I am learning python" --to ja
echo "Bonjour" | python translator.py --to en --engine Claude
python translator.py --demo
```

Docker:

```
docker build -t translator . && docker run -p 5006:5006 --env-file .env translator
```

## Features

- **Engines:** Google (free, no key), MyMemory (free, no key, lower quality; optional `MYMEMORY_EMAIL` raises the
  daily limit), Google Cloud (`GOOGLE_API_KEY`), DeepL (`DEEPL_API_KEY`),
  Claude (`ANTHROPIC_API_KEY`, optional `CLAUDE_MODEL`).
- **Claude extras:** tick *Add reading & notes* for romaji/pinyin and nuance/idiom notes. Pick a *Tone* (formal, casual, ...) and add a *Glossary* (`term = required translation`,
  one per line) to control wording; the CLI has `--tone` and `--glossary FILE`.
- **Multiple targets** at once (one tab per language), swap button, detected-language display.
- **Live translate** (debounced), character counter.
- **Copy**, **speak** (browser speech synthesis) and **dictate** (browser speech recognition;
  Chrome/Edge work best).
- **History** saved in `.translation_history.sqlite` (override with `TRANSLATOR_HISTORY`): search, click to reload, ✕ to delete, *Export for Anki* downloads the listed entries as a CSV (front, back, language tag). It is shared by everyone using the server; set `TRANSLATOR_HISTORY_DISABLED=1` to record nothing.
- **File translation:** `.txt`, `.srt` (timestamps preserved), `.docx` (inline formatting kept) and `.pdf` (text is extracted and returned as a `.txt`; scanned PDFs need OCR first).
- **Persistent cache** in `.translation_cache.sqlite` (override with `TRANSLATOR_CACHE`).
- Responsive UI: translation runs off the UI thread with a progress bar; settings and history live in a
  sidebar, input and output sit side by side (stacking on narrow screens), and there's a dark-mode toggle.
- Long input is chunked automatically, preferring line, then sentence, then word boundaries.

## Development

```
pip install -r requirements-dev.txt
ruff check . && pytest
```

CI runs both on every push (`.github/workflows/ci.yml`).

## Notes

- The free Google engine is an unofficial endpoint: it may be rate-limited or change. Retries with
  backoff are built in; for production use another engine.
- Language codes come from Google's list. For DeepL they're mapped automatically (`en`→`EN-US`,
  `pt`→`PT-BR`, `zh-CN`→`ZH-HANS`, ...); languages DeepL doesn't offer show a clear message.
