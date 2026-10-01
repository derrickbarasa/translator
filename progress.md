# Progress

Running log of what has been built, what was verified, and what is left.

## Status (2026-10-01)

Working app on `main`. 74 tests pass, `ruff` is clean.

**Verified in a real browser** (Chrome, real keystrokes and clicks, MyMemory engine): layout, async flow,
progress bar, a successful translation render, Ctrl+Enter, copy (pasted back), speak (called with the right text
and language), history persistence across a server restart, history restore / search / delete, recent-language
buttons, *Export for Anki* (real download, correct CSV), and file translation of a `.docx` (upload, translate,
download; the bold span survived, slightly shifted). Also verified end to end from the CLI.

**Not verified:** dictate (needs a microphone); `.srt`, `.txt` and `.pdf` uploads in a browser (only unit-tested);
a Google free translation (it rate-limits the dev machine's IP); and the Claude, DeepL and Google
Cloud engines against their real APIs (mocked tests only; no keys available).

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

**Engines** (`backends.py`): Google free (retry with backoff), MyMemory (keyless fallback, lower quality, ~5,000
chars/day anonymous), Google Cloud, DeepL (direct API, code mapping,
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

- MyMemory is translation-memory based: it handled sentences well in testing but returned nonsense for a short
  greeting into Japanese. Treat it as a fallback, not a default.
- PDF input extracts text only: layout, tables and images are lost, scanned PDFs are rejected (no OCR), and the reflow
  heuristic can mis-join lines in multi-column documents. Output is a `.txt`.
- Anki export covers the first target of each history entry only (history stores one output).
- Google's free endpoint is unofficial and currently rejects requests from the dev machine; the app shows the
  rate-limit message after about 27s of retries. A DeepL free key is the simplest workaround.
- Dictation is untested (needs a microphone); it shows an inline notice if the browser has no speech recognition.
- `.docx` formatting is spread across runs proportionally (snapped to word boundaries), so bold/italic spans stay
  roughly where they were but can drift when word order differs between languages. Headers, footers, footnotes and
  text boxes are not translated.
- Language detection uses `langdetect` and is unreliable on very short text, which also affects swap.
- Cache has a 5000-entry LRU cap but no expiry.
- Engine failures other than rate limits, bad keys, quota and network errors still show a generic error.
- `translator.py` itself has only smoke-test coverage; the async translate and file flows are not unit tested.

## Next up

1. Usage and cost tracking.

## Notes for contributors

- Run locally: `panel serve translator.py --show`. Restart the server after editing; a stale server serves old
  code.
- Checks: `ruff check . && pytest`.
- Set `TRANSLATOR_NO_AUTOSERVE=1` when importing `translator.py` outside `panel serve` (the tests do this).
- Secrets live in `.env` (git-ignored); see `.env.example`.
