import pytest

from files import SUPPORTED, extract_pdf_text, reflow, translate_file

fpdf = pytest.importorskip("fpdf")


def make_pdf(pages):
    pdf = fpdf.FPDF()
    for lines in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        for line in lines:
            pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_pdf_is_supported():
    assert ".pdf" in SUPPORTED


def test_extracts_all_pages_and_reflows():
    data = make_pdf([["The quick brown fox", "jumps over the lazy dog."], ["Second page text."]])
    text = extract_pdf_text(data)
    assert "The quick brown fox jumps over the lazy dog." in text
    assert "Second page text." in text
    assert text.index("quick") < text.index("Second")


def test_translate_file_pdf_returns_txt():
    data = make_pdf([["Hello world."]])
    name, out = translate_file("report.pdf", data, str.upper)
    assert name == "report.translated.txt"
    assert "HELLO WORLD." in out.decode("utf-8")


def test_pdf_without_text_has_clear_error():
    with pytest.raises(ValueError, match="No text found"):
        extract_pdf_text(make_pdf([[]]))


def test_damaged_pdf_has_clear_error():
    with pytest.raises(ValueError, match="Couldn't read"):
        extract_pdf_text(b"%PDF-1.4 this is not really a pdf")


@pytest.mark.parametrize("raw, expected", [
    ("one line\ncontinues here", "one line continues here"),
    ("A sentence.\nNew sentence", "A sentence.\nNew sentence"),
    ("para one\n\npara two", "para one\n\npara two"),
    ("trans-\nlation works", "translation works"),
])
def test_reflow(raw, expected):
    assert reflow(raw) == expected
