"""services/session.py: workspace lifecycle helpers. Pure Python, no Streamlit imports, safe to unit-test.

Streamlit forgets everything when the browser tab is refreshed, so the workspace is also written to
.cache/last_session.json after every run and can be restored from the sidebar.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from models import CandidateRecord, SourceType, Workspace
from tools.pdf_tools import load_document

CACHE_PATH = Path(".cache/last_session.json")
SAMPLES = Path("data/samples")


def save_session(ws: Workspace) -> bool:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(ws.model_dump_json(), encoding="utf-8")
        return True
    except Exception:
        return False


def session_exists() -> bool:
    return CACHE_PATH.exists()


def load_session() -> Workspace | None:
    try:
        return Workspace.model_validate_json(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else None
    except Exception:
        return None


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:16]


def jd_changed(ws: Workspace, jd_text: str) -> bool:
    return ws.job is not None and text_hash(ws.jd_text) != text_hash(jd_text)


def reset_for_new_job(ws: Workspace) -> None:
    """Extraction and verification do not depend on the job, so they are kept (this saves API quota).
    Everything that compares a candidate to the job is cleared and will be redone."""
    for rec in ws.candidates.values():
        rec.alignment = None
        rec.interview_kit = None
        rec.interview_evaluation = None
        rec.follow_ups = []
        rec.errors = [e for e in rec.errors if not e.startswith(("align", "kit", "evaluate", "follow_up"))]
    ws.grouping = None
    ws.query_history = []


def _slug(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = re.sub(r"^(resume|cv)[\W_]*", "", stem, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") or "candidate"


def unique_cid(ws: Workspace, base: str) -> str:
    cid, n = base, 2
    while cid in ws.candidates:
        cid, n = f"{base}_{n}", n + 1
    return cid


def add_resume(ws: Workspace, filename: str, data: bytes) -> tuple[str | None, str, bool]:
    """Returns (candidate_id | None, error_message, is_new). A file already added is not added twice."""
    doc = load_document(data, filename, SourceType.RESUME)
    if not doc.ok:
        return None, f"{filename}: {doc.error}", False
    for cid, rec in ws.candidates.items():
        if rec.content_hash == doc.content_hash:
            return cid, "", False
    cid = unique_cid(ws, _slug(filename))
    ws.candidates[cid] = CandidateRecord(candidate_id=cid, filename=filename, content_hash=doc.content_hash, resume_text=doc.text)
    return cid, "", True


def read_text_upload(filename: str, data: bytes, source_type: SourceType) -> tuple[str, str]:
    """Returns (text, error_message) for a job description or interview-notes upload."""
    doc = load_document(data, filename, source_type)
    return (doc.text, "") if doc.ok else ("", f"{filename}: {doc.error}")


def remove_candidate(ws: Workspace, cid: str) -> None:
    ws.candidates.pop(cid, None)
    ws.grouping = None


def sample_jd_text() -> str:
    for path in sorted(SAMPLES.glob("jd_*.txt")):
        return path.read_text(encoding="utf-8")
    return ""


def sample_resume_paths() -> list[Path]:
    return sorted(SAMPLES.glob("resume_*.txt"))


def sample_notes_for(cid: str) -> str:
    """interview_notes_marcus.txt is offered for candidate 'marcus_chen'."""
    for path in sorted(SAMPLES.glob("interview_notes_*.txt")):
        key = path.stem.replace("interview_notes_", "").lower()
        if key and key in cid.lower():
            return path.read_text(encoding="utf-8")
    return ""
