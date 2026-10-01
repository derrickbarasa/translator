"""Translate uploaded .txt, .srt, .docx and .pdf files, returning bytes to download."""
import io
import re
from concurrent.futures import ThreadPoolExecutor

SUPPORTED = (".txt", ".srt", ".docx", ".pdf")

_TIMING = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->")


def _decode(data):
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def translate_srt(text, translate):
    """Translate subtitle text only; cue numbers and timestamps are left untouched."""
    out = []
    for block in re.split(r"\n{2,}", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        timing_idx = next((i for i, ln in enumerate(lines) if _TIMING.match(ln)), None)
        if timing_idx is None:
            out.append(block)
            continue
        head, body = lines[: timing_idx + 1], "\n".join(lines[timing_idx + 1 :])
        out.append("\n".join(head + ([translate(body)] if body.strip() else [])))
    return "\n\n".join(out) + "\n"


def _snap(text, idx, window=12):
    """Move a cut point to the nearest word boundary within `window` characters, else keep it."""
    for step in range(window + 1):
        for cand in (idx - step, idx + step):
            if 0 < cand < len(text) and (text[cand - 1].isspace() or text[cand].isspace()):
                return cand
    return idx


def spread_over_runs(run_texts, formats, translated):
    """Split `translated` across runs so that differently formatted spans keep roughly their share.

    `formats` holds one hashable formatting key per run. Adjacent runs with the same format are one
    span. Word order changes between languages, so the alignment is approximate by nature.
    Returns one string per run; joining them always gives `translated`.
    """
    spans = []  # [format, first run index, total original length]
    for i, (text, fmt) in enumerate(zip(run_texts, formats)):
        if spans and spans[-1][0] == fmt:
            spans[-1][2] += len(text)
        else:
            spans.append([fmt, i, len(text)])
    out = [""] * len(run_texts)
    total = sum(span[2] for span in spans)
    if len(spans) <= 1 or total == 0:
        out[spans[0][1] if spans else 0] = translated
        return out
    cuts, done = [0], 0
    for span in spans[:-1]:
        done += span[2]
        cut = _snap(translated, round(done / total * len(translated)))
        cuts.append(max(cut, cuts[-1]))
    cuts.append(len(translated))
    for (_, first, _), lo, hi in zip(spans, cuts, cuts[1:]):
        out[first] = translated[lo:hi]
    return out


def translate_docx(data, translate, workers=1):
    """Translate every paragraph (including tables and hyperlinks), keeping run-level formatting."""
    from docx import Document
    from docx.text.run import Run

    doc = Document(io.BytesIO(data))

    def paragraphs(container):
        yield from container.paragraphs
        for table in getattr(container, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    yield from paragraphs(cell)

    jobs = []  # (runs, original text)
    for para in paragraphs(doc):
        runs = [Run(r, para) for r in para._p.xpath(".//w:r")]
        text = "".join(run.text for run in runs)
        if text.strip():
            jobs.append((runs, text))

    if workers > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            translated = list(pool.map(lambda job: translate(job[1]), jobs))
    else:
        translated = [translate(text) for _, text in jobs]

    for (runs, _), result in zip(jobs, translated):
        formats = [run._r.rPr.xml if run._r.rPr is not None else "" for run in runs]
        for run, piece in zip(runs, spread_over_runs([r.text for r in runs], formats, result)):
            run.text = piece
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def reflow(text):
    """Undo the hard line wraps PDF extraction leaves inside paragraphs.

    Joins a line to the next when the next starts in lowercase (or the line ends in a hyphenated
    break), keeping blank lines as paragraph breaks.
    """
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)
    return re.sub(r"(?<=[^\n.!?:])\n(?=[a-z])", " ", text)


def extract_pdf_text(data):
    """Text of every page, pages separated by a blank line. Raises ValueError for scanned PDFs."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except PdfReadError as e:
        raise ValueError("Couldn't read this PDF; the file may be damaged.") from e
    text = "\n\n".join(p for p in pages if p)
    if not text:
        raise ValueError("No text found in this PDF. It may be a scan; OCR it first.")
    return reflow(text)


def translate_file(filename, data, translate, workers=1):
    """Return (new_filename, bytes). `translate` maps str -> str.

    `workers` > 1 translates .docx paragraphs concurrently.
    """
    name = filename.lower()
    stem, dot, ext = filename.rpartition(".")
    stem = stem or filename
    if name.endswith(".docx"):
        return f"{stem}.translated.docx", translate_docx(data, translate, workers)
    if name.endswith(".srt"):
        return f"{stem}.translated.srt", translate_srt(_decode(data), translate).encode("utf-8")
    if name.endswith(".pdf"):
        # PDF layout can't be rebuilt, so the translated text comes back as a .txt file.
        return f"{stem}.translated.txt", translate(extract_pdf_text(data)).encode("utf-8")
    if name.endswith(".txt"):
        return f"{stem}.translated.txt", translate(_decode(data)).encode("utf-8")
    raise ValueError(f"Unsupported file type. Use one of: {', '.join(SUPPORTED)}")
