"""Translate uploaded .txt, .srt and .docx files, returning bytes to download."""
import io
import re

SUPPORTED = (".txt", ".srt", ".docx")

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


def translate_docx(data, translate):
    from docx import Document

    doc = Document(io.BytesIO(data))

    def paragraphs(container):
        yield from container.paragraphs
        for table in getattr(container, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    yield from paragraphs(cell)

    for para in paragraphs(doc):
        if para.text.strip():
            translated = translate(para.text)
            # Keep the first run's formatting; drop the rest.
            if para.runs:
                para.runs[0].text = translated
                for run in para.runs[1:]:
                    run.text = ""
            else:
                para.text = translated
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def translate_file(filename, data, translate):
    """Return (new_filename, bytes). `translate` maps str -> str."""
    name = filename.lower()
    stem, dot, ext = filename.rpartition(".")
    stem = stem or filename
    if name.endswith(".docx"):
        return f"{stem}.translated.docx", translate_docx(data, translate)
    if name.endswith(".srt"):
        return f"{stem}.translated.srt", translate_srt(_decode(data), translate).encode("utf-8")
    if name.endswith(".txt"):
        return f"{stem}.translated.txt", translate(_decode(data)).encode("utf-8")
    raise ValueError(f"Unsupported file type. Use one of: {', '.join(SUPPORTED)}")
