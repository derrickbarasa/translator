# translator

An interactive text translator built with [Panel](https://panel.holoviz.org/), with pluggable
engines (free Google, Google Cloud, DeepL, Claude).

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

- **Engines:** Google (free, no key), Google Cloud (`GOOGLE_API_KEY`), DeepL (`DEEPL_API_KEY`),
  Claude (`ANTHROPIC_API_KEY`, optional `CLAUDE_MODEL`).
- **Claude extras:** tick *Add reading & notes* for romaji/pinyin and nuance/idiom notes.
- **Multiple targets** at once (one tab per language), swap button, detected-language display.
- **Live translate** (debounced), character counter.
- **Copy**, **speak** (browser speech synthesis) and **dictate** (browser speech recognition;
  Chrome/Edge work best).
- **History** of the session; click an entry to reload it.
- **File translation:** `.txt`, `.srt` (timestamps preserved) and `.docx`.
- **Persistent cache** in `.translation_cache.sqlite` (override with `TRANSLATOR_CACHE`).
- Long input is chunked automatically, preferring line then word boundaries.

## Development

```
pip install -r requirements-dev.txt
ruff check . && pytest
```

CI runs both on every push (`.github/workflows/ci.yml`).

## Notes

- The free Google engine is an unofficial endpoint: it may be rate-limited or change. Retries with
  backoff are built in; for production use another engine.
- Language codes come from Google's list. DeepL supports a subset and some regional variants
  (e.g. `en-us`) may be needed; unsupported pairs surface as a failed translation.
