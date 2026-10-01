# Progress

Running log of what has been built, what was verified, and what is left.

## Status (2026-10-01)

Working app on `main`. 34 tests pass, `ruff` is clean. Verified in a real browser: layout, async flow, progress
bar, rate-limit message. **Not verified:** a successful translation render (Google rate-limited the dev
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
clear unsupported-language error), Claude (translation plus optional reading and nuance notes). All raise a
shared `RateLimited` error.

**Core** (`core.py`): chunking by line, then sentence (incl. CJK punctuation), then word, then hard cut, with
lossless round-trip. SQLite cache that survives restarts. Per-chunk progress callback. Language detection.

**Files** (`files.py`): `.txt`, `.srt` (cue numbers and timestamps preserved), `.docx`.

**UI** (`translator.py`): sidebar settings and history; side-by-side input and output that wraps on narrow
screens; dark-mode toggle; non-blocking translation with progress bar; multiple targets as tabs; swap;
detected language; live translate (debounced, re-runs if text changed mid-flight); copy, speak, dictate
(browser APIs); session history; file translation card.

**CLI:** `python translator.py "text" --to ja [--from xx] [--engine ...]`, `--demo`, stdin supported.

**Tooling:** pytest suite, ruff, `Dockerfile`, GitHub Actions CI, `.env.example`, `.gitignore`.

## Known limitations

- Google's free endpoint is unofficial and currently rejects requests from the dev machine; the app shows the
  rate-limit message after about 27s of retries. A DeepL free key is the simplest workaround.
- Copy, speak and dictate are untested in a browser (they run as client-side JavaScript). Dictation shows an
  `alert()` if the browser has no speech recognition.
- Chunks are translated one after another, so long files are slow.
- Claude notes (`annotate`) are not cached, so repeated runs are billed again.
- `.docx` translation keeps only the first run's formatting in each paragraph.
- Language detection uses `langdetect` and is unreliable on very short text, which also affects swap.
- Cache has no size limit, expiry or clear button, and Claude cache keys don't include the model version.
- Engine failures other than rate limits and unsupported languages show a generic error, with details only in
  the server console.
- `translator.py` itself has only smoke-test coverage; the async translate and file flows are not unit tested.
- Panel emits deprecation warnings for `button_type` (to be replaced by `color` before Panel 2.0).

## Next up

1. Parallel chunk translation with a small thread pool, keeping the backoff.
2. Cache Claude notes; add cache size cap, clear button and model version in the key.
3. Specific error messages (bad key, quota, network) instead of the generic one.
4. Persist history to SQLite, with search and per-entry delete.
5. Searchable language picker with recent and favorite languages; Ctrl+Enter to translate.
6. Preserve inline formatting in `.docx`.
7. Tone selector and glossary for Claude; Anki CSV export; usage and cost tracking; PDF input.
8. Replace deprecated `button_type` with `color`.

## Notes for contributors

- Run locally: `panel serve translator.py --show`. Restart the server after editing; a stale server serves old
  code.
- Checks: `ruff check . && pytest`.
- Set `TRANSLATOR_NO_AUTOSERVE=1` when importing `translator.py` outside `panel serve` (the tests do this).
- Secrets live in `.env` (git-ignored); see `.env.example`.
