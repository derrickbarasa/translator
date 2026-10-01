"""Chunking, persistent cache, and the translate pipeline (UI-independent)."""
import hashlib
import os
import sqlite3
import threading

CACHE_PATH = os.environ.get("TRANSLATOR_CACHE", os.path.join(os.path.dirname(__file__), ".translation_cache.sqlite"))
MAX_CHARS = 4900  # Google's free endpoint rejects requests of ~5000+ chars


def chunk_text(text, limit=MAX_CHARS):
    """Split text into pieces under `limit`, preferring line boundaries.

    Hard-splits only lines longer than `limit`, preferring whitespace so words stay whole.
    Joining the chunks always reproduces the input exactly.
    """
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            cut = line.rfind(" ", 0, limit)
            cut = cut + 1 if cut > 0 else limit
            chunks.append(line[:cut])
            line = line[cut:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


class Cache:
    """SQLite-backed translation cache that survives restarts."""

    def __init__(self, path=CACHE_PATH):
        self.path = path
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path)

    @staticmethod
    def key(backend, source, target, text):
        return hashlib.sha256("\x00".join((backend, source, target, text)).encode()).hexdigest()

    def get(self, key):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))


_default_cache = None


def default_cache():
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache


def translate_text(text, source, target, backend, cache=None):
    """Translate `text` chunk by chunk through `backend`, using the cache when possible."""
    cache = cache if cache is not None else default_cache()
    parts = []
    for chunk in chunk_text(text, backend.max_chars):
        if not chunk.strip():
            parts.append(chunk)
            continue
        key = cache.key(backend.name, source, target, chunk)
        hit = cache.get(key)
        if hit is None:
            hit = backend.translate(chunk, source, target)
            cache.set(key, hit)
        parts.append(hit)
    return "".join(parts)


def detect_language(text):
    """Best-effort language code for `text`, or None if it can't tell."""
    try:
        from langdetect import detect

        return detect(text)
    except Exception:
        return None
