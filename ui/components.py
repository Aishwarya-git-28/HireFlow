"""ui/components.py: pure functions that return HTML strings. No Streamlit calls in here.

Every string starts with a <div> and contains no blank lines, so Markdown never rewrites it.
Every piece of model or resume text goes through esc() first.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse


# ───────────────────────── small helpers ─────────────────────────
def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def clip(s, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def val(x):
    """Enum or plain string -> its string value."""
    return getattr(x, "value", x)


def tone_for(score: int) -> str:
    return "good" if score >= 70 else "warn" if score >= 40 else "bad"


STATUS = {"met": ("Met", "good"), "partially_met": ("Partly met", "warn"), "unclear": ("Unclear", "slate"), "not_met": ("Not met", "bad")}
VERIFY = {"verified": ("Confirmed", "good"), "partially_verified": ("Exists, holder unconfirmed", "warn"),
          "not_found": ("Not found", "bad"), "contradicted": ("Contradicted", "bad"), "search_failed": ("Not checked", "slate")}
LEVEL = {"strong": ("Strong", "good"), "partial": ("Partial", "warn"), "weak": ("Weak", "bad"),
         "contradicted": ("Contradicted", "bad"), "not_assessed": ("Not assessed", "slate")}
FLAG = {"suspicious_content": ("Security", "bad"), "inconsistent": ("Inconsistent", "bad"), "timeline_gap": ("Timeline gap", "warn"),
        "unverified_claim": ("Unverified claim", "warn"), "missing_info": ("Missing info", "slate"), "unclear": ("Unclear", "slate")}
QTYPE = {"technical": ("Technical", "lagoon"), "behavioral": ("Behavioral", "marker"), "situational": ("Situational", "lagoon"),
         "validation": ("Validation", "warn")}
STAGES = {"extraction": ("Extraction", "lagoon"), "verification": ("Verification", "warn"), "alignment": ("Alignment", "good"),
          "grouping": ("Grouping", "lagoon"), "interview_kit": ("Interview kit", "marker"), "follow_up": ("Follow-up", "marker"),
          "evaluation": ("Evaluation", "good"), "pool_query": ("Pool question", "lagoon")}
ASSESS = {"sufficient": ("Sufficient", "good"), "vague": ("Vague", "warn"), "inconsistent": ("Inconsistent", "bad"),
          "unsupported": ("Unsupported", "bad")}
SOURCE = {"resume": "Resume", "job_description": "Job description", "web_search": "Web", "interview_notes": "Interview notes", "other": "Source"}


def chip(text, kind: str = "slate", plain: bool = False) -> str:
    return f'<span class="chip {kind}{" plain" if plain else ""}">{esc(text)}</span>'


def mapped(table: dict, key) -> str:
    k = val(key)
    label, kind = table.get(k, (str(k).replace("_", " ").capitalize(), "slate"))
    return chip(label, kind)


# ───────────────────────── page furniture ─────────────────────────
LOGO = ('<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true"><rect x="1" y="1" width="26" height="26" rx="7" fill="#0F5C63"/>'
        '<rect x="6" y="11" width="16" height="6" rx="1.5" fill="#FFE066"/>'
        '<path d="M6 7.5h9M6 21h12" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".85"/></svg>')


def topbar(chips: list[str]) -> str:
    return f'<div class="topbar"><div class="brand">{LOGO}<span>HireFlow</span></div><div class="topbar-r">{"".join(chips)}</div></div>'


def side_brand() -> str:
    return (f'<div class="side-brand">{LOGO}<span>HireFlow</span></div>'
            '<p class="side-note">Screen faster, interview sharper. Every rating shows the words it rests on, and people make the decision.</p>')


def steps(items: list[tuple[bool, str, str]]) -> str:
    lis = "".join(f'<li class="{"done" if done else ""}"><span class="n">{"&#10003;" if done else i}</span>'
                  f'<div><b>{esc(t)}</b><small>{esc(s)}</small></div></li>' for i, (done, t, s) in enumerate(items, 1))
    return f'<div><ul class="steps">{lis}</ul></div>'


def page_head(title: str, sub: str = "") -> str:
    p = f"<p>{esc(sub)}</p>" if sub else ""
    return f'<div class="phead"><h1>{esc(title)}</h1>{p}</div>'


def section(title: str, note: str = "") -> str:
    n = f"<span>{esc(note)}</span>" if note else ""
    return f'<div class="sh"><h2>{esc(title)}</h2>{n}</div>'


def empty(title: str, body: str) -> str:
    return f'<div class="empty"><b>{esc(title)}</b>{esc(body)}</div>'


def human_note() -> str:
    return ('<div class="human">HireFlow supports a hiring decision; it never makes one. It does not recommend hiring or rejecting '
            'anyone, and every rating can be checked against the quote behind it.</div>')


def landing() -> str:
    return (
        '<div class="landing"><div>'
        '<h1>Every hiring insight, traced to its source.</h1>'
        '<p>HireFlow reads resumes against your job description, checks the claims that can be checked, and shows the exact words '
        'behind every rating. You keep the decision.</p></div>'
        '<div class="specimen">'
        '<p class="spec-cap">From the resume</p>'
        '<div class="spec-doc">Designed a <mark>retrieval-augmented generation (RAG) assistant over 200K internal documents</mark> '
        'using FAISS and an LLM API; cut analyst search time by 60%.</div>'
        '<div class="spec-link"></div>'
        '<div class="spec-req">Experience with LLM applications, including RAG</div>'
        f'<div class="spec-row">{chip("Met", "good")}{chip("Quote found in the resume", "marker")}{chip("Claim not yet verified on the web", "warn")}</div>'
        '</div></div>')


AGENTS = [
    ("Fact Auditor", "Reads each resume and checks employers, certifications and open-source claims on the web."),
    ("Alignment Architect", "Splits the job into requirements and rates every candidate against them, with quotes."),
    ("Interview Strategist", "Writes questions aimed at each candidate's gaps and unverified claims."),
    ("Interview Evaluator", "Turns interview notes into an evidence map and lists what was never asked."),
]


def agent_steps() -> str:
    lis = "".join(f'<li><span class="n">{i}</span><b>{esc(n)}</b><p>{esc(d)}</p></li>' for i, (n, d) in enumerate(AGENTS, 1))
    return f'<div class="agents"><ol>{lis}</ol></div>'


def brief(items: list[tuple[str, str]]) -> str:
    cells = "".join(f"<div><b>{esc(v)}</b><span>{esc(label)}</span></div>" for v, label in items)
    return f'<div class="brief">{cells}</div>'


# ───────────────────────── scores and coverage ─────────────────────────
def meter(score: int, ticks: int = 20, big: bool = False) -> str:
    score = int(max(0, min(100, score)))
    on = round(score / 100 * ticks)
    cells = "".join(f'<i class="{"on" if i < on else ""}" style="--d:{i}"></i>' for i in range(ticks))
    return f'<div class="meter {tone_for(score)}{" lg" if big else ""}"><b>{score}</b><span class="ticks">{cells}</span></div>'


def strip(matches) -> str:
    cells = ""
    for m in matches:
        label, kind = STATUS.get(val(m.status), ("Unclear", "slate"))
        nice = " nice" if val(m.priority) == "nice_to_have" else ""
        tip = esc(f"{m.req_id}: {clip(m.requirement_text, 70)} ({label})")
        cells += f'<i class="cell {kind}{nice}" title="{tip}"></i>'
    return f'<div class="strip">{cells}</div>'


def legend() -> str:
    items = "".join(f'<span><i class="sw {k}"></i>{esc(t)}</span>' for t, k in
                    (("Met", "good"), ("Partly met", "warn"), ("Unclear or not assessed", "slate"), ("Not met", "bad")))
    return f'<div class="legend">{items}<span>Tall bars and dark headers are must-haves</span></div>'


def coverage_matrix(job, rows) -> str:
    """rows: list of (name, fit_score, AlignmentReport)."""
    reqs = job.requirements
    head = "".join(f'<th class="{"must" if val(r.priority) == "must_have" else "nice"}" title="{esc(r.text)}">{esc(r.req_id)}</th>' for r in reqs)
    body = ""
    for n, (name, fit, al) in enumerate(rows):
        by = {m.req_id: m for m in al.matches}
        cells = ""
        for j, r in enumerate(reqs):
            m = by.get(r.req_id)
            label, kind = STATUS.get(val(m.status), ("Unclear", "slate")) if m else ("Not assessed", "slate")
            cells += (f'<td class="c {kind}" style="--d:{n * len(reqs) + j}" '
                      f'title="{esc(name)}, {esc(r.req_id)}: {esc(clip(r.text, 60))} ({label})"></td>')
        body += f'<tr><td class="name">{esc(name)}</td>{cells}<td class="fit">{int(fit)}</td></tr>'
    return f'<div class="mxwrap"><table class="mx"><thead><tr><th>Candidate</th>{head}<th>Fit</th></tr></thead><tbody>{body}</tbody></table></div>'


def candidate_row(rank: int, name: str, headline: str, tier_kind: str, tier_label: str, al, extra_chips: list[str]) -> str:
    chips = "".join(extra_chips)
    row = f'<div class="row">{chip(tier_label, tier_kind)}{chips}</div>'
    return (f'<div class="cand"><div class="rank">{rank}</div><div><div class="nm">{esc(name)}</div>'
            f'<div class="sub">{esc(clip(headline, 90))}</div>{strip(al.matches)}{row}</div></div>')


def lane(label: str, rationale: str, members: list[tuple[str, int]], tone: str) -> str:
    colour = {"good": "var(--good)", "warn": "#E2AE49", "bad": "var(--bad)"}.get(tone, "var(--lagoon)")
    rows = "".join(f'<div class="m"><b>{esc(n)}</b><span>{s}</span></div>' for n, s in members)
    return f'<div class="lane" style="--tone:{colour}"><h3>{esc(label)}</h3><p>{esc(clip(rationale, 140))}</p>{rows}</div>'


def checks(items: list[tuple[int, str]]) -> str:
    rows = "".join(f'<div class="chk"><b>{n}</b><span>{esc(t)}</span></div>' for n, t in items)
    return f'<div class="ledger">{rows}</div>'


# ───────────────────────── evidence ─────────────────────────
def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "") or url
    except Exception:
        return url


def evidence_line(e) -> str:
    """One quote in the marker style, with where it came from."""
    stype = val(e.source_type)
    label = SOURCE.get(stype, "Source")
    src = str(e.source_id or "")
    if stype == "web_search" and src.startswith("http"):
        where = f'<a href="{esc(src)}" target="_blank" rel="noopener noreferrer">{esc(_domain(src))}</a>'
    else:
        where = esc(label)
    loc = f", {esc(e.locator)}" if getattr(e, "locator", "") else ""
    return f'<div class="ev"><span class="hl">{esc(clip(e.quote, 260))}</span><span class="from">{where}{loc}</span></div>'


def evidence_block(evs, limit: int = 2) -> str:
    if not evs:
        return '<span class="none">No supporting quote</span>'
    return "".join(evidence_line(e) for e in evs[:limit])


def req_row(m) -> str:
    label, kind = STATUS.get(val(m.status), ("Unclear", "slate"))
    must = val(m.priority) == "must_have"
    pri = f'<span class="pri{" must" if must else ""}" title="{"Must-have" if must else "Nice to have"}"></span>'
    nv = '<span class="note-nv">Needs validation</span>' if m.needs_validation else ""
    return (f'<div class="rq"><div class="rq-id">{pri}{esc(m.req_id)}</div>'
            f'<div><div class="rq-t">{esc(m.requirement_text)}</div><div class="rq-why">{esc(clip(m.rationale, 260))}</div></div>'
            f'<div class="rq-st">{chip(label, kind)}{nv}</div><div>{evidence_block(m.evidence)}</div></div>')


def ledger(rows: list[str]) -> str:
    return f'<div class="ledger">{"".join(rows)}</div>'


def flag_row(f) -> str:
    ask = f'<div class="ask">Check: {esc(f.suggested_check)}</div>' if f.suggested_check else ""
    ev = "".join(evidence_line(e) for e in f.evidence[:1])
    ev_html = f'<div class="d">{ev}</div>' if ev else ""
    return (f'<div class="item"><div>{mapped(FLAG, f.flag_type)}</div>'
            f'<div><div class="t">{esc(f.description)}</div>{ask}{ev_html}</div></div>')


def verify_row(r) -> str:
    links = ""
    for u in r.source_urls[:2]:
        if str(u).startswith("http"):
            links += f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(_domain(u))}</a> '
    src = f'<div class="ask">Sources: {links}</div>' if links else ""
    return (f'<div class="item"><div>{mapped(VERIFY, r.status)}</div>'
            f'<div><div class="t">{esc(clip(r.claim, 120))}</div><div class="d">{esc(clip(r.finding, 240))}</div>{src}</div></div>')


def item_rows(pairs: list[tuple[str, str]]) -> str:
    """Two-column ledger: bold label on the left, plain description on the right."""
    rows = "".join(f'<div class="item"><div class="t">{esc(a)}</div><div class="d" style="margin:0">{esc(b)}</div></div>' for a, b in pairs)
    return f'<div class="ledger">{rows}</div>'


def dossier_head(rec, tier_label: str, tier_kind: str) -> str:
    p, a = rec.profile, rec.alignment
    years = f"About {p.total_years_experience:g} years of experience, from the listed dates" if p.total_years_experience else "Years of experience not stated"
    must = [m for m in a.matches if val(m.priority) == "must_have"]
    met = sum(1 for m in must if val(m.status) == "met")
    chips = [chip(tier_label, tier_kind), chip(f"{met} of {len(must)} must-haves met", "plain")]
    if a.validation_req_ids:
        chips.append(chip(f"{len(a.validation_req_ids)} ratings need validation", "warn"))
    if p.validation_flags:
        chips.append(chip(f"{len(p.validation_flags)} flags", "warn"))
    links = "".join(chip(l, "plain") for l in p.links[:3])
    return (f'<div class="dossier"><div><h1>{esc(p.full_name)}</h1><div class="sub">{esc(p.headline)}</div>'
            f'<div class="sub">{esc(years)}</div><div class="row">{"".join(chips)}</div><div class="row">{links}</div></div>'
            f'<div>{meter(a.fit_score, big=True)}<div class="cap">Fit score, computed from the ratings below</div></div></div>')


def insight_panel(title: str, items) -> str:
    if not items:
        return f'<div class="panel"><h3>{esc(title)}</h3><div class="ins"><span class="none">Nothing recorded.</span></div></div>'
    rows = "".join(f'<div class="ins">{esc(i.statement)}{"".join(evidence_line(e) for e in i.evidence[:1])}</div>' for i in items)
    return f'<div class="panel"><h3>{esc(title)}</h3>{rows}</div>'


def role_rows(experience) -> list[str]:
    rows = []
    for e in experience:
        when = " to ".join(x for x in (e.start_date, e.end_date) if x) or "Dates not given"
        dur = f'<br>{esc(e.duration_months)} months' if e.duration_months else ""
        ach = "".join(f"<li>{esc(clip(a, 180))}</li>" for a in e.achievements[:3])
        tech = "".join(f'<span class="tag">{esc(t)}</span>' for t in e.technologies[:8])
        rows.append(f'<div class="role"><div class="when">{esc(when)}{dur}</div><div><div class="who">{esc(e.title or "Role")}, {esc(e.company)}</div>'
                    f'<ul>{ach}</ul><div style="margin-top:.5rem">{tech}</div></div></div>')
    return rows


def tags(names) -> str:
    inner = "".join(f'<span class="tag">{esc(n)}</span>' for n in names)
    return f"<div>{inner}</div>"


def question_card(q, extra: str = "") -> str:
    label, kind = QTYPE.get(val(q.question_type), ("Question", "lagoon"))
    reqs = "".join(chip(r, "plain") for r in q.target_req_ids)
    sig = "".join(f"<li>{esc(s)}</li>" for s in q.expected_signals) or "<li>None listed</li>"
    red = "".join(f"<li>{esc(s)}</li>" for s in q.red_flags) or "<li>None listed</li>"
    return (f'<div class="qcard"><div style="display:flex;gap:.4rem;flex-wrap:wrap">{chip(label, kind)}{reqs}</div>'
            f'<div class="q">{esc(q.question)}</div><div class="rq-why">{esc(q.rationale)}</div>'
            f'<div class="cols"><div><h4>A strong answer includes</h4><ul>{sig}</ul></div><div><h4>Warning signs</h4><ul>{red}</ul></div></div>{extra}</div>')


def answer_card(question: str, answer: str, answerable: bool) -> str:
    note = "" if answerable else f'<div style="margin-top:.5rem">{chip("The data cannot answer this", "warn")}</div>'
    return f'<div class="ans"><div class="q">{esc(question)}</div><div class="a">{esc(answer)}</div>{note}</div>'


def audit_row(e, who: str) -> str:
    label, kind = STAGES.get(val(e.stage), (str(val(e.stage)), "lagoon"))
    ts = str(e.timestamp or "")
    when = f'{esc(ts[11:19])}<br>{esc(ts[:10])}'
    ev = "".join(evidence_line(x) for x in e.evidence[:2])
    calls = ""
    if e.tool_calls:
        calls = '<div class="meta" style="margin-top:.4rem">' + "".join(
            chip(f"{c.tool_name}: {clip(c.input_summary, 40)}", "plain" if c.ok else "bad") for c in e.tool_calls[:6]) + "</div>"
    return (f'<div class="au"><div class="when">{when}</div><div><div class="meta">{chip(label, kind)}<span>{esc(who)}</span>'
            f'<span>{esc(e.agent)}</span><span>{esc(e.model)}</span></div><div class="what">{esc(clip(e.insight, 300))}</div>{ev}{calls}</div></div>')


# ───────────────────────── source view with highlighted quotes ─────────────────────────
def highlight_html(text: str, quotes: list[str]) -> str:
    """Return the document as escaped HTML with every evidence quote marked. Unmatched quotes are simply not marked."""
    spans: list[tuple[int, int]] = []
    for q in quotes:
        toks = re.findall(r"[A-Za-z0-9]+", q or "")
        if len(toks) < 3:
            continue
        m = re.search(r"\W+".join(re.escape(t) for t in toks), text, re.I)
        if m:
            spans.append((m.start(), m.end()))
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, pos = [], 0
    for s, e in merged:
        out.append(esc(text[pos:s]))
        out.append(f"<mark>{esc(text[s:e])}</mark>")
        pos = e
    out.append(esc(text[pos:]))
    return f'<div class="srcbox">{"".join(out)}</div>'


def collect_quotes(rec) -> list[str]:
    """Every resume quote used anywhere in a candidate's results."""
    found: list[str] = []

    def take(evs):
        for e in evs or []:
            if val(e.source_type) == "resume" and e.quote:
                found.append(e.quote)

    p, a = rec.profile, rec.alignment
    if p:
        for coll in (p.skills, p.experience, p.projects, p.certifications, p.validation_flags):
            for item in coll:
                take(item.evidence)
    if a:
        for m in a.matches:
            take(m.evidence)
        for s in list(a.strengths) + list(a.concerns):
            take(s.evidence)
    return list(dict.fromkeys(found))


def guardrail_stats(ws) -> list[tuple[int, str]]:
    """Counts of the moments code overruled or filtered a model, read from the audit trail."""
    quotes = corrections = injections = dates = 0
    for e in ws.audit:
        t = e.insight
        m = re.match(r"Integrity check: dropped (\d+) of", t)
        if m:
            quotes += int(m.group(1))
            continue
        m = re.match(r"Integrity check: (\d+) ", t)
        if m:
            corrections += int(m.group(1))
            continue
        if t.startswith("Security check"):
            injections += 1
            continue
        m = re.match(r"Timeline check \(code\): (\d+)", t)
        if m:
            dates += int(m.group(1))
    unverified = sum(1 for r in ws.candidates.values() if r.verification
                     for v in r.verification.results if val(v.status) in ("not_found", "contradicted"))
    return [
        (quotes, "quotes removed because they could not be found in the source document"),
        (corrections, "ratings or results corrected because the evidence behind them was missing"),
        (injections, "resumes containing instructions aimed at the AI, which were ignored and flagged"),
        (dates, "date problems found by code instead of by a model"),
        (unverified, "claims that searches could not confirm, surfaced for a human to check"),
    ]
