"""tools/pdf_tools.py: deterministic document loading.

NOT an agent tool. Agents never read files; the app loads text once and passes it into prompts.
Contract: nothing here raises. Failures come back as SourceDocument(ok=False, error=...).
"""
import io
import re

import pdfplumber

from models import SourceDocument, SourceType, content_hash

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PAGES = 12
MAX_CHARS = 20_000  # roughly 5k tokens; protects free-tier token budgets
MIN_CHARS = 50      # below this, the file is treated as unreadable (e.g. scanned PDF)


def slugify(name: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") or "doc"


def clean_text(text: str) -> str:
    """Normalize whitespace and strip invisible characters (saves tokens, blocks hidden text tricks)."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)  # zero-width characters
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fail(doc_id: str, filename: str, source_type: SourceType, error: str) -> SourceDocument:
    return SourceDocument(doc_id=doc_id, filename=filename, source_type=source_type, ok=False, error=error)


def _read_pdf(file_bytes: bytes, warnings: list[str]) -> tuple[str, list[str], int]:
    """Returns (text with [Page N] markers, embedded http links, total page count)."""
    parts: list[str] = []
    links: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total = len(pdf.pages)
        if total > MAX_PAGES:
            warnings.append(f"PDF has {total} pages; only the first {MAX_PAGES} were read.")
        for i, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            try:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            except Exception as e:  # one bad page must not kill the document
                warnings.append(f"Page {i} could not be read ({type(e).__name__}).")
                text = ""
            parts.append(f"[Page {i}]\n{text}")
            try:  # URLs hidden behind link text like "GitHub" matter for verification
                links += [h["uri"] for h in page.hyperlinks if str(h.get("uri", "")).startswith("http")]
            except Exception:
                pass
    return "\n\n".join(parts), list(dict.fromkeys(links)), total


def load_document(
    file_bytes: bytes,
    filename: str,
    source_type: SourceType,
    doc_id: str = "",
    max_chars: int = MAX_CHARS,
) -> SourceDocument:
    """Load a PDF/TXT/MD upload into a SourceDocument. Never raises."""
    doc_id = doc_id or slugify(filename)
    try:
        if not file_bytes:
            return _fail(doc_id, filename, source_type, "File is empty.")
        if len(file_bytes) > MAX_FILE_BYTES:
            return _fail(doc_id, filename, source_type, f"File is larger than {MAX_FILE_BYTES // 1_048_576} MB.")

        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        warnings: list[str] = []
        links: list[str] = []
        if ext == ".pdf":
            raw, links, pages = _read_pdf(file_bytes, warnings)
        elif ext in (".txt", ".md"):
            raw, pages = file_bytes.decode("utf-8-sig", errors="replace"), 1
        else:
            return _fail(doc_id, filename, source_type, f"Unsupported file type '{ext or 'none'}'. Use PDF, TXT or MD.")

        text = clean_text(raw)
        body_chars = len(re.sub(r"\[Page \d+\]", "", text).strip())
        if body_chars < MIN_CHARS:
            return _fail(
                doc_id, filename, source_type,
                "No extractable text (likely a scanned/image-only PDF). OCR is not supported; paste the text into a .txt file instead.",
            )

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
            warnings.append(f"Text was cut to the first {max_chars:,} characters to control cost.")
        if links:  # appended AFTER truncation so links are never lost
            text += "\n\n[Embedded links]\n" + "\n".join(links)

        return SourceDocument(
            doc_id=doc_id, filename=filename, source_type=source_type, text=text, page_count=pages,
            content_hash=content_hash(file_bytes), truncated=truncated, warnings=warnings,
        )
    except Exception as e:
        return _fail(doc_id, filename, source_type, f"Could not read '{filename}' ({type(e).__name__}: {str(e)[:150]}).")