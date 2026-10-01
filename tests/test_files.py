import io

from docx import Document

from files import translate_file, translate_srt

SRT = """1
00:00:01,000 --> 00:00:02,000
Hello there

2
00:00:03,000 --> 00:00:04,000
Line one
Line two
"""


def test_srt_keeps_numbers_and_timestamps():
    out = translate_srt(SRT, str.upper)
    assert "00:00:01,000 --> 00:00:02,000" in out
    assert "HELLO THERE" in out and "LINE ONE\nLINE TWO" in out
    assert out.startswith("1\n")


def test_txt_and_names():
    name, data = translate_file("notes.txt", "hi".encode(), str.upper)
    assert name == "notes.translated.txt" and data == b"HI"


def test_docx_translates_paragraphs():
    doc = Document()
    doc.add_paragraph("hello world")
    buf = io.BytesIO()
    doc.save(buf)
    name, data = translate_file("a.docx", buf.getvalue(), str.upper)
    assert name == "a.translated.docx"
    assert Document(io.BytesIO(data)).paragraphs[0].text == "HELLO WORLD"


def test_unsupported():
    import pytest

    with pytest.raises(ValueError):
        translate_file("a.pdf", b"", str)
