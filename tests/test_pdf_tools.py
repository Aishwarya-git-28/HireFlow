from models import SourceType
from tools.pdf_tools import clean_text, load_document


def _tiny_pdf(text: str) -> bytes:
    """Builds a minimal valid one-page PDF so we can test the real pdfplumber path offline."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_clean_text_strips_noise():
    raw = "Python\u200b   developer\n\n\n\n\u00a0SQL \x00 expert"
    assert clean_text(raw) == "Python developer\n\nSQL expert"


def test_text_file_loads():
    body = ("Ananya Rao. Machine learning engineer with Python and SQL experience. " * 3).encode()
    doc = load_document(body, "resume.txt", SourceType.RESUME, doc_id="cand_01_resume")
    assert doc.ok and doc.doc_id == "cand_01_resume" and "Python" in doc.text and doc.content_hash


def test_real_pdf_loads_with_page_marker():
    doc = load_document(_tiny_pdf("Senior Python engineer with ten years of NLP and SQL experience"), "cv.pdf", SourceType.RESUME)
    assert doc.ok, doc.error
    assert "[Page 1]" in doc.text and "Python" in doc.text and doc.page_count == 1


def test_garbage_pdf_returns_error_not_exception():
    doc = load_document(b"this is not a pdf", "broken.pdf", SourceType.RESUME)
    assert not doc.ok and doc.error


def test_empty_and_unsupported_files_are_rejected_politely():
    assert not load_document(b"", "a.txt", SourceType.RESUME).ok
    bad = load_document(b"some bytes here", "resume.exe", SourceType.RESUME)
    assert not bad.ok and "Unsupported" in bad.error


def test_tiny_text_is_treated_as_unreadable():
    doc = load_document(b"hi", "a.txt", SourceType.RESUME)
    assert not doc.ok and "No extractable text" in doc.error


def test_long_text_is_truncated_with_warning():
    doc = load_document(("word " * 5000).encode(), "long.txt", SourceType.RESUME, max_chars=1000)
    assert doc.ok and doc.truncated and len(doc.text) <= 1000 and doc.warnings