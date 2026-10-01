"""Chunking, persistent cache, and the translate pipeline (UI-independent)."""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

CACHE_PATH = os.environ.get("TRANSLATOR_CACHE", os.path.join(os.path.dirname(__file__), ".translation_cache.sqlite"))
MAX_CHARS = 4900  # Google's free endpoint rejects requests of ~5000+ chars


_SENTENCE = re.compile(r".*?[.!?。！？…]+[\"'”’)\]]*\s*|.+", re.S)


def _split_long(line, limit):
    """Split an over-long line into pieces <= limit: sentences first, then spaces, then hard cuts."""
    pieces, current = [], ""
    for sentence in _SENTENCE.findall(line):
        while len(sentence) > limit:  # a single "sentence" too long: break on whitespace, else hard cut
            if current:
                pieces.append(current)
                current = ""
            cut = sentence.rfind(" ", 0, limit)
            cut = cut + 1 if cut > 0 else limit
            pieces.append(sentence[:cut])
            sentence = sentence[cut:]
        if len(current) + len(sentence) > limit:
            pieces.append(current)
            current = ""
        current += sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text, limit=MAX_CHARS):
    """Split text into pieces under `limit`, preferring line, then sentence, then word boundaries.

    Joining the chunks always reproduces the input exactly.
    """
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            *full, line = _split_long(line, limit)
            chunks.extend(full)
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


MAX_CACHE_ENTRIES = 5000


class Cache:
    """SQLite-backed translation cache that survives restarts.

    Holds at most `max_entries`; the least recently used entries are dropped first.
    """

    def __init__(self, path=CACHE_PATH, max_entries=MAX_CACHE_ENTRIES):
        self.path = path
        self.max_entries = max_entries
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            columns = [row[1] for row in db.execute("PRAGMA table_info(cache)")]
            if "used" not in columns:  # caches created before the size cap existed
                db.execute("ALTER TABLE cache ADD COLUMN used REAL NOT NULL DEFAULT 0")

    def _connect(self):
        return sqlite3.connect(self.path)

    @staticmethod
    def key(backend, source, target, text):
        return hashlib.sha256("\x00".join((backend, source, target, text)).encode()).hexdigest()

    def get(self, key):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
            if row:
                db.execute("UPDATE cache SET used = ? WHERE key = ?", (time.time(), key))
        return row[0] if row else None

    def set(self, key, value):
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO cache (key, value, used) VALUES (?, ?, ?)", (key, value, time.time()))
            db.execute(
                "DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY used DESC LIMIT -1 OFFSET ?)",
                (self.max_entries,),
            )

    def count(self):
        with self._lock, self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]

    def clear(self):
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM cache")


HISTORY_PATH = os.environ.get(
    "TRANSLATOR_HISTORY", os.path.join(os.path.dirname(__file__), ".translation_history.sqlite")
)
HISTORY_MAX_ENTRIES = 500


class History:
    """Persistent, searchable log of past translations.

    Set TRANSLATOR_HISTORY_DISABLED=1 to record nothing (e.g. on a shared server: the history is
    shared by everyone who uses the app).
    """

    def __init__(self, path=HISTORY_PATH, max_entries=HISTORY_MAX_ENTRIES, enabled=None):
        self.path = path
        self.max_entries = max_entries
        self.enabled = enabled if enabled is not None else not os.environ.get("TRANSLATOR_HISTORY_DISABLED")
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL,"
                " source TEXT NOT NULL, targets TEXT NOT NULL, text TEXT NOT NULL, output TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self.path)

    def add(self, text, source, targets, output):
        if not self.enabled:
            return
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO history (created, source, targets, text, output) VALUES (?, ?, ?, ?, ?)",
                (time.time(), source, json.dumps(list(targets)), text, output),
            )
            db.execute(
                "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                (self.max_entries,),
            )

    def list(self, query="", limit=20):
        """Newest first; `query` matches the original text or the translation (case-insensitive)."""
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT id, source, targets, text, output FROM history"
                " WHERE text LIKE ? ESCAPE '\\' OR output LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                (like, like, limit),
            ).fetchall()
        return [
            {"id": i, "source": src, "targets": json.loads(tg), "text": text, "out": out}
            for i, src, tg, text, out in rows
        ]

    def delete(self, entry_id):
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM history WHERE id = ?", (entry_id,))

    def clear(self):
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM history")


_default_cache = None
_default_history = None


def default_history():
    global _default_history
    if _default_history is None:
        _default_history = History()
    return _default_history


def default_cache():
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache


def translate_text(text, source, target, backend, cache=None, on_chunk=None):
    """Translate `text` chunk by chunk through `backend`, using the cache when possible.

    Chunks run concurrently (up to `backend.workers`) and are reassembled in order.
    `on_chunk()` is called after each chunk finishes (used for progress reporting); it may be
    called from worker threads.
    """
    cache = cache if cache is not None else default_cache()

    def one(chunk):
        if chunk.strip():
            key = cache.key(backend.cache_id, source, target, chunk)
            result = cache.get(key)
            if result is None:
                result = backend.translate(chunk, source, target)
                cache.set(key, result)
        else:
            result = chunk
        if on_chunk:
            on_chunk()
        return result

    chunks = chunk_text(text, backend.max_chars)
    workers = min(backend.workers, len(chunks))
    if workers <= 1:
        return "".join(one(c) for c in chunks)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return "".join(pool.map(one, chunks))  # map re-raises the first failure, in chunk order


def annotate_cached(backend, original, translated, target, cache=None):
    """`backend.annotate(...)`, cached so repeated runs aren't billed again."""
    cache = cache if cache is not None else default_cache()
    key = cache.key(backend.cache_id + ":notes", "", target, original + "\x00" + translated)
    note = cache.get(key)
    if note is None:
        note = backend.annotate(original, translated, target)
        cache.set(key, note)
    return note


def detect_language(text):
    """Best-effort language code for `text`, or None if it can't tell."""
    try:
        from langdetect import detect

        return detect(text)
    except Exception:
        return None
