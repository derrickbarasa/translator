# Progress

Running log of what has been built, what was verified, and what is left.

## Status (2026-10-01)

Working app on `main`. 67 tests pass, `ruff` is clean. Verified in a real browser: layout, async flow, progress
bar, rate-limit message. **Not verified:** the Ctrl+Enter key listener in a real browser (the Python side is tested); a successful translation render (Google rate-limited the dev
machine's IP) and the Claude / DeepL / Google Cloud engines against their real APIs (mocked tests only).

## History

| Commit | What changed |
| --- | --- |
| `d73ee38` | Initial upload |
| `95957a5` | Refactor: dropdowns, chunking, guarded demo, docs |
| `3889eda` | Rate-limit retry with backoff, cache, clearer rate-limit message |
| `97d4902`, `2fc3404` | Rename `translater` to `translator`, comment fix |
| `3e5cb93` | Batch 1: engines, files, CLI, history, tests, Docker, CI |
| `8362228` | Batch 2: async + progress, new layout, DeepL mapping, sentence chunking, backend tests |

## Done

**Engines** (`backends.py`): Google free (retry with backoff), Google Cloud, DeepL (direct API, code mapping,
clear unsupported-language error), Claude (translation plus optional reading and nuance notes, tone selector, glossary). All raise a
shared `RateLimited` error, or `BadCredentials` / `QuotaExceeded` / `NetworkError` with user-facing messages.

**Core** (`core.py`): parallel chunk translation (ordered, per-engine worker count); chunking by line, then sentence (incl. CJK punctuation), then word, then hard cut, with
lossless round-trip. SQLite cache that survives restarts (LRU cap, clear button in the sidebar, Claude model in the key, Claude notes cached). Per-chunk progress callback. Language detection.

**Files** (`files.py`): `.txt`, `.srt` (cue numbers and timestamps preserved), `.docx` (inline formatting kept, paragraphs translated concurrently), `.pdf` (text extraction via pypdf, returned as `.txt`).

**UI** (`translator.py`): sidebar settings and history; side-by-side input and output that wraps on narrow
screens; dark-mode toggle; non-blocking translation with progress bar; multiple targets as tabs; swap;
detected language; live translate (debounced, re-runs if text changed mid-flight); Ctrl/Cmd+Enter to translate; recent target languages (from history) as one-click buttons; copy, speak, dictate
(browser APIs); persistent history (SQLite, search, per-entry delete, Anki CSV export, shared across sessions, opt-out via `TRANSLATOR_HISTORY_DISABLED`); file translation card.

**CLI:** `python translator.py "text" --to ja [--from xx] [--engine ...]`, `--demo`, stdin supported.

**Tooling:** pytest suite, ruff, `Dockerfile`, GitHub Actions CI, `.env.example`, `.gitignore`.

## Known limitations

- PDF input extracts text only: layout, tables and images are lost, scanned PDFs are rejected (no OCR), and the reflow
  heuristic can mis-join lines in multi-column documents. Output is a `.txt`.
- Anki export covers the first target of each history entry only (history stores one output). The download button is
  untested in a browser.
- Google's free endpoint is unofficial and currently rejects requests from the dev machine; the app shows the
  rate-limit message after about 27s of retries. A DeepL free key is the simplest workaround.
- Copy, speak and dictate are untested in a browser (they run as client-side JavaScript). Dictation shows an
  inline notice if the browser has no speech recognition.
- `.docx` formatting is spread across runs proportionally (snapped to word boundaries), so bold/italic spans stay
  roughly where they were but can drift when word order differs between languages. Headers, footers, footnotes and
  text boxes are not translated.
- Language detection uses `langdetect` and is unreliable on very short text, which also affects swap.
- Cache has a 5000-entry LRU cap but no expiry.
- Engine failures other than rate limits, bad keys, quota and network errors still show a generic error.
- `translator.py` itself has only smoke-test coverage; the async translate and file flows are not unit tested.
- Panel warns that `Button(name=...)` is deprecated in favour of `label` (Panel 2.0).

## Next up

1. Usage and cost tracking.
2. Rename `Button(name=...)` to `label`.

## Notes for contributors

- Run locally: `panel serve translator.py --show`. Restart the server after editing; a stale server serves old
  code.
- Checks: `ruff check . && pytest`.
- Set `TRANSLATOR_NO_AUTOSERVE=1` when importing `translator.py` outside `panel serve` (the tests do this).
- Secrets live in `.env` (git-ignored); see `.env.example`.
