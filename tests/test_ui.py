"""Offline smoke tests for the dashboard: every page renders, HTML is well formed, nothing calls a model."""
from html.parser import HTMLParser
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services import demo
from ui import components as C

APP = str(Path(__file__).resolve().parents[1] / "app.py")
PAGES = ["Setup", "Overview", "Candidates", "Interviews", "Ask the pool", "Audit trail"]


class _Balance(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()


def _problems(html: str) -> list[str]:
    p = _Balance()
    p.feed(html)
    p.close()
    return p.errors + [f"unclosed <{t}>" for t in p.stack]


def _app(page: str, cid: str = "marcus_chen") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.session_state["ws"] = demo.build_demo_workspace()
    at.session_state["mode"] = "demo"
    at.session_state["nav"] = page
    at.session_state["cid"] = cid
    return at.run()


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_demo_data(page):
    at = _app(page)
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    blocks = [m.value for m in at.markdown if m.value.lstrip().startswith("<div")]
    assert blocks, "the page drew no HTML components"
    for html in blocks:
        assert not _problems(html), (page, _problems(html), html[:200])


@pytest.mark.parametrize("cid", ["ananya_rao", "marcus_chen", "priya_nair"])
def test_candidate_dossier_renders_for_each_candidate(cid):
    at = _app("Candidates", cid)
    assert not at.exception, [str(e.value)[:300] for e in at.exception]


def test_empty_workspace_shows_landing():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Every hiring insight, traced to its source." in m.value for m in at.markdown)


def test_html_is_escaped():
    evil = '<script>alert(1)</script> & "quotes"'
    assert "<script>" not in C.chip(evil)
    assert "<script>" not in C.highlight_html(evil, ["alert 1 quotes"])
    assert "<script>" not in C.answer_card(evil, evil, True)


def test_highlight_marks_only_matching_quotes():
    out = C.highlight_html("Built a RAG assistant. Led a team.", ["Built a RAG assistant", "Never appears anywhere here"])
    assert out.count("<mark>") == 1 and "<mark>Built a RAG assistant</mark>" in out


def test_demo_quotes_are_verbatim_in_their_sources():
    import re

    def norm(s):
        return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

    ws = demo.build_demo_workspace()
    for rec in ws.candidates.values():
        text = norm(rec.resume_text)
        assert all(norm(q) in text for q in C.collect_quotes(rec)), rec.candidate_id
