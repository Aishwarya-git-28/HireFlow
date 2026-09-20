"""ui/views.py: one function per page, plus the sidebar and navigation.

Rules this file follows:
  * All backend calls go through the `Backend` object and never raise into the UI (errors become messages).
  * Session state that must survive a page change lives in plain keys ("ws", "cid", "jd_text"), never in widget keys,
    because Streamlit deletes the state of any widget that was not drawn in the previous run.
  * Buttons that change page use callbacks (`go`), which is the only safe moment to write a widget's key.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import streamlit as st

from models import SourceType, Workspace
from services import demo, report, scoring, session
from ui import components as C

PAGES = ["Setup", "Overview", "Candidates", "Interviews", "Ask the pool", "Audit trail"]
EXAMPLES = [
    "Who has built RAG or LLM applications?",
    "Which candidates have claims that could not be verified?",
    "Who is strongest at extracting text from PDFs?",
    "Which candidates have gaps in their work history?",
]


# ───────────────────────── backend handle ─────────────────────────
@dataclass
class Backend:
    pipelines: object | None = None
    interview: object | None = None
    error: str = ""
    providers: dict = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.pipelines is not None and self.interview is not None

    @property
    def live(self) -> bool:
        return self.ready and any(self.providers.values())

    def why_not_live(self) -> str:
        if not self.ready:
            return f"The AI backend could not be loaded ({self.error or 'unknown error'}). The demo data still works."
        return "No API key was found. Add GROQ_API_KEY and GEMINI_API_KEY to .env, or use the demo data."


def detect_backend() -> Backend:
    pipelines = interview = None
    err = ""
    try:
        from crew import interview, pipelines  # noqa: F811
    except Exception as exc:  # the dashboard must still open without the AI stack
        err = f"{type(exc).__name__}: {exc}"
    providers: dict[str, bool] = {}
    try:
        import config

        for spec in config.ROLE_MODELS.values():
            p = spec.partition(":")[0]
            providers[p] = bool(config.ANTHROPIC_API_KEY) if p == "anthropic" else bool(config._PROVIDERS.get(p, {}).get("key"))
    except Exception as exc:
        err = err or f"{type(exc).__name__}: {exc}"
    return Backend(pipelines, interview, err, providers)


# ───────────────────────── state helpers and callbacks ─────────────────────────
def names(ws: Workspace) -> dict[str, str]:
    return {c: (r.profile.full_name if r.profile else r.filename or c) for c, r in ws.candidates.items()}


def screened(ws: Workspace) -> list[str]:
    return [c for c, r in ws.candidates.items() if r.profile and r.alignment]


def ranked(ws: Workspace) -> list[str]:
    return sorted(screened(ws), key=lambda c: (ws.candidates[c].alignment.fit_score, ws.candidates[c].alignment.must_have_coverage), reverse=True)


def tier_kind(rec) -> str:
    return C.tone_for(rec.alignment.fit_score) if rec.alignment else "slate"


def go(page: str, cid: str | None = None) -> None:
    st.session_state["nav"] = page
    if cid:
        st.session_state["cid"] = cid


def _clear_widget_state() -> None:
    ss = st.session_state
    for k in list(ss.keys()):
        if str(k).startswith(("jd_", "notes_", "ans_", "interviewer_", "pick_", "reqf_", "resume_upload", "ask_")):
            del ss[k]


def load_demo() -> None:
    ws, msg = demo.load_demo_workspace()
    ss = st.session_state
    _clear_widget_state()
    ss["ws"], ss["mode"], ss["nav"], ss["flash"] = ws, "demo", "Overview", msg
    ss["jd_text"] = ws.jd_text
    order = ranked(ws)
    ss["cid"] = order[0] if order else None


def restore_session() -> None:
    ws = session.load_session()
    ss = st.session_state
    if ws is None:
        ss["flash"] = "The last session could not be read."
        return
    _clear_widget_state()
    ss["ws"], ss["mode"], ss["flash"] = ws, "live", "Restored your last session."
    ss["jd_text"] = ws.jd_text
    ss["nav"] = "Overview" if screened(ws) else "Setup"


def start_fresh() -> None:
    ss = st.session_state
    _clear_widget_state()
    ss["ws"], ss["mode"], ss["nav"], ss["jd_text"], ss["flash"] = Workspace(), "live", "Setup", "", "Started a new workspace."


def _fill(key: str, text: str) -> None:
    st.session_state[key] = text


def remove_candidate(cid: str) -> None:
    session.remove_candidate(st.session_state["ws"], cid)


def pick_candidate(ws: Workspace, key: str, pool: list[str]) -> str:
    """A candidate selector whose choice survives page changes (stored in the plain key 'cid')."""
    nm = names(ws)
    cur = st.session_state.get("cid")
    if cur not in pool:
        cur = pool[0]
    choice = st.selectbox("Candidate", pool, index=pool.index(cur), format_func=lambda c: nm[c], key=key, label_visibility="collapsed")
    st.session_state["cid"] = choice
    return choice


def download(label: str, data: str, file_name: str, mime: str, key: str) -> None:
    try:
        st.download_button(label, data=data, file_name=file_name, mime=mime, key=key, on_click="ignore")
    except TypeError:  # older Streamlit without on_click="ignore"
        st.download_button(label, data=data, file_name=file_name, mime=mime, key=key)


# ───────────────────────── sidebar, top bar, navigation ─────────────────────────
def topbar_chips(be: Backend, mode: str) -> list[str]:
    chips = [C.chip("Demo data", "marker") if mode == "demo" else C.chip("Your data", "lagoon")]
    if be.ready:
        for provider, ok in be.providers.items():
            chips.append(C.chip(f"{provider.capitalize()} key {'found' if ok else 'missing'}", "good" if ok else "slate", plain=True))
    else:
        chips.append(C.chip("AI backend unavailable", "bad"))
    return chips


def render_sidebar(ws: Workspace, be: Backend) -> None:
    with st.sidebar:
        st.markdown(C.side_brand(), unsafe_allow_html=True)
        total = len(ws.candidates)
        done = sum(1 for r in ws.candidates.values() if r.alignment)
        evaluated = sum(1 for r in ws.candidates.values() if r.interview_evaluation)
        st.markdown(C.steps([
            (ws.job is not None, "Define the role", ws.job.title if ws.job else "Add a job description"),
            (total > 0, "Add candidates", f"{total} added" if total else "Upload resumes"),
            (total > 0 and done == total, "Run screening", f"{done} of {total} screened" if total else "Extract, verify, rate"),
            (evaluated > 0, "Interview and evaluate", f"{evaluated} evaluated" if evaluated else "Follow-ups and reports"),
        ]), unsafe_allow_html=True)
        st.divider()
        st.button("Load demo data", on_click=load_demo, use_container_width=True, key="side_demo")
        if session.session_exists():
            st.button("Restore last session", on_click=restore_session, use_container_width=True, key="side_restore")
        st.button("Start fresh", on_click=start_fresh, use_container_width=True, key="side_fresh")
        st.markdown(f'<p class="side-note">{C.esc("Live AI is on." if be.live else be.why_not_live())}</p>', unsafe_allow_html=True)


def nav(pages: list[str]) -> str:
    ss = st.session_state
    if ss.get("nav") not in pages:  # a deselected control leaves None behind; repair it before drawing the widget
        ss["nav"] = ss.get("_page", pages[0])
    if hasattr(st, "segmented_control"):
        choice = st.segmented_control("Page", pages, key="nav", label_visibility="collapsed")
    else:
        choice = st.radio("Page", pages, key="nav", horizontal=True, label_visibility="collapsed")
    page = choice or ss.get("_page", pages[0])
    ss["_page"] = page
    return page


# ───────────────────────── Setup ─────────────────────────
def _candidate_status(rec) -> str:
    if rec.errors:
        return C.chip("Needs attention", "bad")
    if rec.alignment and rec.interview_kit:
        return C.chip("Screened", "good")
    return C.chip("Waiting", "slate")


def run_screening(ws: Workspace, be: Backend, jd_text: str) -> None:
    ss = st.session_state
    total = 2 + 4 * max(1, len(ws.candidates))
    counter = {"n": 0}
    with st.status("Screening in progress. Keep this tab open.", expanded=True) as status:
        bar = st.progress(0.0)

        def note(msg: str) -> None:
            counter["n"] += 1
            st.write(msg)
            bar.progress(min(counter["n"] / total, 0.97))

        try:
            changed = session.jd_changed(ws, jd_text)
            if ws.job is None or changed:
                note("Reading the job description")
                err = be.pipelines.parse_job(ws, jd_text)
                if err:
                    status.update(label="The job description could not be parsed", state="error")
                    st.error(err)
                    return
                if changed:
                    session.reset_for_new_job(ws)
            be.pipelines.screen_pool(ws, progress=note)
        except Exception as exc:
            session.save_session(ws)
            status.update(label="Screening stopped", state="error")
            st.error(f"{type(exc).__name__}: {exc}. Finished stages were kept; run again to continue.")
            return
        bar.progress(1.0)
        session.save_session(ws)
        problems = [c for c, r in ws.candidates.items() if r.errors]
        status.update(label="Screening finished" if not problems else "Screening finished with issues",
                      state="complete" if not problems else "error", expanded=bool(problems))
    ss["mode"] = "live"
    ss["flash"] = "Screening finished." if not problems else "Screening finished with issues. See the candidate list."
    if not problems:
        ss["goto"] = "Overview"
    st.rerun()


def view_setup(ws: Workspace, be: Backend) -> None:
    ss = st.session_state
    if not ws.candidates and ws.job is None:
        st.markdown(C.landing(), unsafe_allow_html=True)
        c1, c2, _ = st.columns([1.5, 2.6, 2])
        c1.button("Explore demo data", type="primary", on_click=load_demo, use_container_width=True, key="hero_demo")
        c2.markdown('<p class="side-note" style="margin-top:.6rem">No keys needed. The demo runs on saved results.</p>', unsafe_allow_html=True)
    else:
        st.markdown(C.page_head("Set up the role", "Add a job description and resumes, then run the screening. Finished stages are kept, "
                                                    "so a re-run only does new work."), unsafe_allow_html=True)
    st.markdown(C.section("How the work is split", "Four agents run in order and code checks every output"), unsafe_allow_html=True)
    st.markdown(C.agent_steps(), unsafe_allow_html=True)
    st.markdown(C.section("Inputs"), unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Job description**")
        up = st.file_uploader("Upload a job description", type=["pdf", "txt", "md"], key="jd_upload", label_visibility="collapsed")
        if up is not None:
            tag = session.text_hash(f"{up.name}:{up.size}")
            if ss.get("jd_upload_seen") != tag:
                text, err = session.read_text_upload(up.name, up.getvalue(), SourceType.JOB_DESCRIPTION)
                ss["jd_upload_seen"] = tag
                if err:
                    st.error(err)
                else:
                    ss["jd_widget"] = text
        if "jd_widget" not in ss:
            ss["jd_widget"] = ss.get("jd_text", ws.jd_text or "")
        st.text_area("Job description text", key="jd_widget", height=290, label_visibility="collapsed",
                     placeholder="Paste the job description here, or upload a file above.")
        ss["jd_text"] = ss["jd_widget"]
        sample = session.sample_jd_text()
        if sample:
            st.button("Use the sample job description", on_click=_fill, args=("jd_widget", sample), key="use_sample_jd")

    with right:
        st.markdown("**Candidates**")
        files = st.file_uploader("Upload resumes", type=["pdf", "txt", "md"], accept_multiple_files=True,
                                 key="resume_upload", label_visibility="collapsed")
        added = False
        for f in files or []:
            cid, err, is_new = session.add_resume(ws, f.name, f.getvalue())
            if err:
                st.warning(err)
            added = added or is_new
        if added:
            ss["mode"] = "live"
        samples = session.sample_resume_paths()
        if samples:
            def add_samples() -> None:
                for path in samples:
                    session.add_resume(st.session_state["ws"], path.name, path.read_bytes())
                st.session_state["mode"] = "live"

            st.button(f"Add the {len(samples)} sample resumes", on_click=add_samples, key="add_samples")
        if not ws.candidates:
            st.markdown(C.empty("No candidates yet", "Upload resumes above."), unsafe_allow_html=True)
        for cid, rec in ws.candidates.items():
            c1, c2, c3 = st.columns([4.2, 2.2, 1.4], vertical_alignment="center")
            title = rec.profile.full_name if rec.profile else rec.filename or cid
            c1.markdown(f'<div style="font-weight:600">{C.esc(title)}</div><div class="rq-why" style="margin:0">{C.esc(rec.filename)}</div>',
                        unsafe_allow_html=True)
            c2.markdown(_candidate_status(rec), unsafe_allow_html=True)
            c3.button("Remove", key=f"rm_{cid}", on_click=remove_candidate, args=(cid,), use_container_width=True)
            for e in rec.errors:
                st.caption(f"{cid}: {e[:220]}")

    st.markdown(C.section("Run"), unsafe_allow_html=True)
    jd_text = (ss.get("jd_text") or "").strip()
    pending = [c for c, r in ws.candidates.items() if not (r.alignment and r.interview_kit)]
    changed = session.jd_changed(ws, jd_text)
    needs = [n for ok, n in ((bool(jd_text), "a job description"), (bool(ws.candidates), "at least one resume")) if not ok]
    work_left = ws.job is None or changed or bool(pending)
    if needs:
        msg = "Still needed: " + " and ".join(needs) + "."
    elif not be.live:
        msg = be.why_not_live()
    elif changed:
        msg = "The job description changed. Candidates will be re-rated; extraction and web checks are reused."
    elif pending:
        msg = f"{len(pending)} candidate{'s' if len(pending) != 1 else ''} to screen. This takes a few minutes per candidate on free tiers."
    elif work_left:
        msg = "The job description will be parsed first."
    else:
        msg = "Everything is up to date. Change the job description or add resumes to run again."
    label = "Run screening" if work_left else "Everything is up to date"
    c1, c2 = st.columns([1.3, 4], vertical_alignment="center")
    go_run = c1.button(label, type="primary", disabled=bool(needs) or not be.live or not work_left, key="run_btn", use_container_width=True)
    c2.markdown(f'<p class="side-note" style="margin:0">{C.esc(msg)}</p>', unsafe_allow_html=True)
    if go_run:
        run_screening(ws, be, jd_text)


# ───────────────────────── Overview ─────────────────────────
def _empty_state(title: str, body: str) -> None:
    st.markdown(C.empty(title, body), unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.3, 1.3, 3])
    c1.button("Load demo data", type="primary", on_click=load_demo, use_container_width=True, key=f"empty_demo_{title}")
    c2.button("Go to Setup", on_click=go, args=("Setup",), use_container_width=True, key=f"empty_setup_{title}")


def view_overview(ws: Workspace, be: Backend) -> None:
    order = ranked(ws)
    if not order or ws.job is None:
        st.markdown(C.page_head("Overview", "Ranking, requirement coverage and groups appear here once candidates are screened."), unsafe_allow_html=True)
        _empty_state("Nothing to show yet", "Load the demo data, or add a job description and resumes in Setup.")
        return
    job, nm = ws.job, names(ws)
    must = sum(1 for r in job.requirements if C.val(r.priority) == "must_have")
    st.markdown(C.page_head(job.title, f"{len(order)} candidate{'s' if len(order) != 1 else ''} rated against {len(job.requirements)} requirements, "
                                        f"{must} of them must-haves. Ratings rest on quotes from each resume."), unsafe_allow_html=True)
    fits = [ws.candidates[c].alignment.fit_score for c in order]
    needs = sum(len(ws.candidates[c].alignment.validation_req_ids) for c in order)
    stats = C.guardrail_stats(ws)
    st.markdown(C.brief([
        (str(len(order)), "candidates screened"), (str(fits[0]), f"top fit score, {nm[order[0]]}"),
        (str(round(sum(fits) / len(fits))), "average fit score"), (str(needs), "ratings that need validation"),
        (str(sum(n for n, _ in stats[:4])), "times code corrected or filtered a model")]), unsafe_allow_html=True)

    st.markdown(C.section("Requirement coverage", "Hover a square for the requirement and the rating"), unsafe_allow_html=True)
    rows = [(nm[c], ws.candidates[c].alignment.fit_score, ws.candidates[c].alignment) for c in order]
    st.markdown(C.coverage_matrix(job, rows), unsafe_allow_html=True)
    st.markdown(C.legend(), unsafe_allow_html=True)

    if ws.grouping:
        st.markdown(C.section("Groups", "Candidates grouped by the experience they share"), unsafe_allow_html=True)
        lanes = ""
        for g in ws.grouping.groups:
            members = [(nm[c], ws.candidates[c].alignment.fit_score) for c in g.candidate_ids if c in nm and ws.candidates[c].alignment]
            mean = sum(s for _, s in members) / len(members) if members else 0
            lanes += C.lane(g.label, g.rationale, members, C.tone_for(round(mean)))
        st.markdown(f'<div class="lanes">{lanes}</div>', unsafe_allow_html=True)

    st.markdown(C.section("Ranking", "Highest fit score first"), unsafe_allow_html=True)
    for i, cid in enumerate(order, 1):
        rec = ws.candidates[cid]
        a, p = rec.alignment, rec.profile
        bad = sum(1 for v in (rec.verification.results if rec.verification else []) if C.val(v.status) in ("not_found", "contradicted"))
        chips = []
        if a.validation_req_ids:
            chips.append(C.chip(f"{len(a.validation_req_ids)} to validate", "warn"))
        if bad:
            chips.append(C.chip(f"{bad} claim{'s' if bad != 1 else ''} not found", "bad"))
        if any(C.val(f.flag_type) == "suspicious_content" for f in p.validation_flags):
            chips.append(C.chip("Security flag", "bad"))
        if rec.interview_evaluation:
            chips.append(C.chip(f"Interviewed, {rec.interview_evaluation.assessed_coverage}% assessed", "lagoon"))
        st.markdown('<div class="hair"></div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([6, 2.7, 1.5], vertical_alignment="center")
        c1.markdown(C.candidate_row(i, p.full_name, p.headline, tier_kind(rec), scoring.tier_label(rec), a, chips), unsafe_allow_html=True)
        c2.markdown(C.meter(a.fit_score), unsafe_allow_html=True)
        c3.button("Open profile", key=f"open_{cid}", on_click=go, args=("Candidates", cid), use_container_width=True)

    st.markdown(C.section("Checks that ran on this data", "Counted from the audit trail"), unsafe_allow_html=True)
    st.markdown(C.checks(stats), unsafe_allow_html=True)
    st.markdown(C.human_note(), unsafe_allow_html=True)


# ───────────────────────── Candidates ─────────────────────────
def view_candidates(ws: Workspace, be: Backend) -> None:
    order = ranked(ws)
    if not order or ws.job is None:
        st.markdown(C.page_head("Candidates", "Open a candidate to see every rating next to the words it rests on."), unsafe_allow_html=True)
        _empty_state("No screened candidates", "Screen candidates in Setup, or load the demo data.")
        return
    cid = pick_candidate(ws, "pick_candidates", order)
    rec = ws.candidates[cid]
    p, a = rec.profile, rec.alignment
    st.markdown(C.dossier_head(rec, scoring.tier_label(rec), tier_kind(rec)), unsafe_allow_html=True)
    t_sum, t_req, t_flag, t_prof, t_kit, t_src = st.tabs(["Summary", "Requirements", "Flags and verification", "Profile", "Interview kit", "Source text"])

    with t_sum:
        st.markdown(f'<div class="lede">{C.esc(a.recruiter_summary or "No summary was generated for this candidate.")}</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="large")
        c1.markdown(C.insight_panel("Strengths", a.strengths), unsafe_allow_html=True)
        c2.markdown(C.insight_panel("Concerns", a.concerns), unsafe_allow_html=True)
        need = [m for m in a.matches if m.status.value == "unclear" or m.needs_validation]
        if need:
            st.markdown(C.section("Validate before relying on these", "Unclear, unverified or leaning on a claim that failed a check"), unsafe_allow_html=True)
            st.markdown(C.ledger([C.req_row(m) for m in need]), unsafe_allow_html=True)

    with t_req:
        st.markdown(C.strip(a.matches), unsafe_allow_html=True)
        st.markdown(C.legend(), unsafe_allow_html=True)
        choice = st.radio("Show", ["All", "Must-haves", "Needs validation", "Gaps"], horizontal=True, key=f"reqf_{cid}", label_visibility="collapsed")
        pick = {
            "All": lambda m: True,
            "Must-haves": lambda m: C.val(m.priority) == "must_have",
            "Needs validation": lambda m: m.status.value == "unclear" or m.needs_validation,
            "Gaps": lambda m: m.status.value != "met",
        }[choice]
        rows = [C.req_row(m) for m in a.matches if pick(m)]
        st.markdown(C.ledger(rows) if rows else C.empty("Nothing in this view", "Try another filter."), unsafe_allow_html=True)

    with t_flag:
        st.markdown(C.section("Flags", "Things a person should check"), unsafe_allow_html=True)
        st.markdown(C.ledger([C.flag_row(f) for f in p.validation_flags]) if p.validation_flags else C.empty("No flags", "Nothing needed a second look."),
                    unsafe_allow_html=True)
        st.markdown(C.section("Web verification", "Confirmed means a source ties this person to the claim. Exists, holder unconfirmed is the usual result for employers and certificates"),
                    unsafe_allow_html=True)
        results = rec.verification.results if rec.verification else []
        st.markdown(C.ledger([C.verify_row(r) for r in results]) if results else C.empty("No claims were checked", "Verification did not run for this candidate."),
                    unsafe_allow_html=True)

    with t_prof:
        if p.skills:
            st.markdown(C.section("Skills"), unsafe_allow_html=True)
            st.markdown(C.tags([s.name for s in p.skills]), unsafe_allow_html=True)
        if p.experience:
            st.markdown(C.section("Experience"), unsafe_allow_html=True)
            st.markdown(C.ledger(C.role_rows(p.experience)), unsafe_allow_html=True)
        if p.projects:
            st.markdown(C.section("Projects"), unsafe_allow_html=True)
            st.markdown(C.item_rows([(x.name, x.description or "No description") for x in p.projects]), unsafe_allow_html=True)
        pairs = [(f"{e.degree} {e.field_of_study}".strip() or "Education", f"{e.institution}, {e.end_year}") for e in p.education]
        pairs += [(c.name, f"{c.issuer}, {c.year}".strip(", ")) for c in p.certifications]
        if pairs:
            st.markdown(C.section("Education and certifications"), unsafe_allow_html=True)
            st.markdown(C.item_rows(pairs), unsafe_allow_html=True)

    with t_kit:
        kit = rec.interview_kit
        if kit is None:
            st.markdown(C.empty("No interview kit yet", "The kit is created during screening."), unsafe_allow_html=True)
        else:
            if kit.probing_priorities:
                st.markdown(C.section("Probe first", "In priority order"), unsafe_allow_html=True)
                st.markdown(C.item_rows([(f"{i}", t) for i, t in enumerate(kit.probing_priorities, 1)]), unsafe_allow_html=True)
            st.markdown(C.section("Questions", f"{len(kit.questions)} questions written for this candidate"), unsafe_allow_html=True)
            for q in kit.questions:
                with st.expander(f"{q.question_id}  {C.clip(q.question, 100)}"):
                    st.markdown(C.question_card(q), unsafe_allow_html=True)
            st.button("Use this kit in an interview", on_click=go, args=("Interviews", cid), key=f"kit_go_{cid}", type="primary")

    with t_src:
        quotes = C.collect_quotes(rec)
        st.markdown(C.section("Resume text", f"{len(quotes)} quotes behind ratings, flags and strengths are highlighted"), unsafe_allow_html=True)
        st.markdown(C.highlight_html(rec.resume_text, quotes) if rec.resume_text else C.empty("No source text", "This record has no resume text."),
                    unsafe_allow_html=True)


# ───────────────────────── Interviews ─────────────────────────
def render_evaluation(ws: Workspace, rec) -> None:
    ev = rec.interview_evaluation
    strengths, concerns = len(ev.strengths), len(ev.concerns)
    st.markdown(C.brief([(f"{ev.assessed_coverage}%", "of requirements assessed in the interview"), (str(strengths), "strengths with quotes"),
                         (str(concerns), "concerns with quotes"), (str(len(ev.unanswered_areas)), "areas never covered")]), unsafe_allow_html=True)
    st.markdown(f'<div class="lede" style="margin-top:1rem">{C.esc(ev.notes_summary)}</div>', unsafe_allow_html=True)
    st.markdown(C.section("What the notes show, requirement by requirement"), unsafe_allow_html=True)
    rows = []
    for e in ev.evidence_map:
        must = C.val(e.priority) == "must_have"
        pri = f'<span class="pri{" must" if must else ""}" title="{"Must-have" if must else "Nice to have"}"></span>'
        rows.append(f'<div class="rq"><div class="rq-id">{pri}{C.esc(e.req_id)}</div><div><div class="rq-t">{C.esc(e.requirement_text)}</div>'
                    f'<div class="rq-why">{C.esc(C.clip(e.summary, 240))}</div></div><div class="rq-st">{C.mapped(C.LEVEL, e.level)}</div>'
                    f'<div>{C.evidence_block(e.note_excerpts, 1)}</div></div>')
    st.markdown(C.ledger(rows), unsafe_allow_html=True)
    if ev.unanswered_areas:
        st.markdown(C.section("Still unanswered", "Ask these in the next round"), unsafe_allow_html=True)
        st.markdown(C.item_rows([(f"{u.req_id}", f"{u.reason} {('Try: ' + u.suggested_question) if u.suggested_question else ''}".strip()) for u in ev.unanswered_areas]),
                    unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="large")
    c1.markdown(C.insight_panel("Strengths", ev.strengths), unsafe_allow_html=True)
    c2.markdown(C.insight_panel("Concerns", ev.concerns), unsafe_allow_html=True)
    if ev.recommended_next_steps:
        st.markdown(C.section("Suggested next steps"), unsafe_allow_html=True)
        st.markdown(C.item_rows([(str(i), s) for i, s in enumerate(ev.recommended_next_steps, 1)]), unsafe_allow_html=True)
    md = report.evaluation_markdown(ws.job, rec)
    download("Download the evaluation report (Markdown)", md, f"{rec.candidate_id}_evaluation.md", "text/markdown", f"dl_eval_{rec.candidate_id}")
    st.markdown(f'<div class="human">{C.esc(ev.decision_note)}</div>', unsafe_allow_html=True)


def view_interviews(ws: Workspace, be: Backend) -> None:
    ss = st.session_state
    pool = [c for c, r in ws.candidates.items() if r.interview_kit and r.profile]
    if not pool or ws.job is None:
        st.markdown(C.page_head("Interviews", "Get follow-up questions during an interview, then turn your notes into an evidence-based report."), unsafe_allow_html=True)
        _empty_state("No interview kits yet", "Screen candidates first. Each one gets a kit written for their gaps.")
        return
    cid = pick_candidate(ws, "pick_interviews", pool)
    rec = ws.candidates[cid]
    kit = rec.interview_kit
    st.markdown(C.page_head(f"Interview: {rec.profile.full_name}", "Log an answer to get pointed follow-ups, then generate the report from your notes."), unsafe_allow_html=True)

    st.markdown(C.section("During the interview", "Pick the question you asked and type what the candidate said"), unsafe_allow_html=True)
    every = list(kit.questions) + [q for f in rec.follow_ups for q in f.follow_ups]
    by_id = {q.question_id: q for q in every}
    qids = list(by_id)
    cur = ss.get("qid") if ss.get("qid") in by_id else qids[0]
    qid = st.selectbox("Question asked", qids, index=qids.index(cur), key=f"pick_q_{cid}", label_visibility="collapsed",
                       format_func=lambda i: f"{i}   {C.clip(by_id[i].question, 95)}")
    ss["qid"] = qid
    st.markdown(C.question_card(by_id[qid]), unsafe_allow_html=True)
    answer = st.text_area("What did the candidate say?", key=f"ans_{cid}_{qid}", height=120, placeholder="Type or paste the answer from your notes.")
    if st.button("Suggest follow-ups", type="primary", key=f"fu_{cid}_{qid}", disabled=not be.live or len(answer.strip()) < 15):
        with st.spinner("Reading the answer against the resume and the question"):
            result, err = be.interview.suggest_follow_ups(ws, cid, qid, answer)
        if err:
            st.error(err)
        else:
            session.save_session(ws)
    if not be.live:
        st.caption(be.why_not_live())
    for f in reversed(rec.follow_ups):
        head = f'{C.mapped(C.ASSESS, f.answer_assessment)}'
        st.markdown(f'<div class="panel"><h3>Answer to {C.esc(f.parent_question_id)}</h3><div class="ins">{head} {C.esc(f.reason)}</div></div>', unsafe_allow_html=True)
        for q in f.follow_ups:
            st.markdown(C.question_card(q), unsafe_allow_html=True)
        if not f.follow_ups:
            st.markdown(C.empty("No follow-up needed", "The answer was specific enough."), unsafe_allow_html=True)

    st.markdown(C.section("After the interview", "Paste or upload your notes. Every rating must quote the notes"), unsafe_allow_html=True)
    key = f"notes_{cid}"
    if key not in ss:
        ss[key] = rec.interview_notes or ""
    up = st.file_uploader("Upload interview notes", type=["pdf", "txt", "md"], key=f"notes_up_{cid}", label_visibility="collapsed")
    if up is not None:
        tag = session.text_hash(f"{up.name}:{up.size}")
        if ss.get(f"notes_seen_{cid}") != tag:
            text, err = session.read_text_upload(up.name, up.getvalue(), SourceType.INTERVIEW_NOTES)
            ss[f"notes_seen_{cid}"] = tag
            if err:
                st.error(err)
            else:
                ss[key] = text
    sample = session.sample_notes_for(cid)
    if sample and not ss.get(key):
        st.button("Use the sample interview notes", on_click=_fill, args=(key, sample), key=f"sample_notes_{cid}")
    notes = st.text_area("Interview notes", key=key, height=230, label_visibility="collapsed", placeholder="Paste the interviewer's notes here.")
    default_name = rec.interview_evaluation.interviewer if rec.interview_evaluation else ""
    if f"interviewer_{cid}" not in ss:
        ss[f"interviewer_{cid}"] = default_name
    c1, c2 = st.columns([2, 1.4], vertical_alignment="bottom")
    who = c1.text_input("Interviewer", key=f"interviewer_{cid}", placeholder="Interviewer name")
    run = c2.button("Generate the evaluation report", type="primary", key=f"eval_{cid}", disabled=not be.live or len(notes.strip()) < 50, use_container_width=True)
    if run:
        with st.spinner("Matching the notes to each requirement"):
            result, err = be.interview.evaluate_interview(ws, cid, notes, who)
        if err:
            st.error(err)
        else:
            session.save_session(ws)
    if rec.interview_evaluation:
        render_evaluation(ws, rec)


# ───────────────────────── Ask the pool ─────────────────────────
def _ask_example(q: str) -> None:
    st.session_state["ask_pending"] = q


def view_ask(ws: Workspace, be: Backend) -> None:
    ss = st.session_state
    st.markdown(C.page_head("Ask the pool", "Ask in plain language. Answers use only the screened candidate data, and every match shows its quote."), unsafe_allow_html=True)
    if not screened(ws):
        _empty_state("No candidates to ask about", "Screen candidates first, or load the demo data.")
        return
    with st.form("ask_form", clear_on_submit=True):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        q = c1.text_input("Your question", placeholder="For example: who has shipped a model to production?", label_visibility="collapsed")
        sent = c2.form_submit_button("Ask", type="primary", use_container_width=True, disabled=not be.live)
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        col.button(ex, key=f"ex_{ex}", on_click=_ask_example, args=(ex,), use_container_width=True, disabled=not be.live)
    pending = ss.pop("ask_pending", None)
    question = pending or (q if sent else "")
    if question.strip():
        with st.spinner("Reading the candidate data"):
            result, err = be.interview.ask_pool(ws, question)
        if err:
            st.error(err)
        else:
            session.save_session(ws)
    if not be.live:
        st.caption(be.why_not_live() + " Saved answers below are still readable.")
    nm = names(ws)
    if not ws.query_history:
        st.markdown(C.section("Answers"), unsafe_allow_html=True)
        st.markdown(C.empty("No questions yet", "Try one of the examples above."), unsafe_allow_html=True)
    for res in reversed(ws.query_history):
        st.markdown(C.answer_card(res.question, res.answer, res.answerable), unsafe_allow_html=True)
        rows = []
        for h in res.hits:
            rows.append(f'<div class="item"><div class="t">{C.esc(nm.get(h.candidate_id, h.candidate_id))}</div><div><div class="d" style="margin:0">{C.esc(h.reason)}</div>'
                        f'{"".join(C.evidence_line(e) for e in h.evidence[:2])}</div></div>')
        if rows:
            st.markdown(C.ledger(rows), unsafe_allow_html=True)
        st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)


# ───────────────────────── Audit trail ─────────────────────────
def view_audit(ws: Workspace, be: Backend) -> None:
    st.markdown(C.page_head("Audit trail", "Every insight, the candidate information it used, the agent and model that produced it, and any web calls made."), unsafe_allow_html=True)
    if not ws.audit:
        _empty_state("The trail is empty", "Entries appear as soon as anything is screened.")
        return
    nm = names(ws)
    c1, c2, c3 = st.columns([2, 3, 3])
    who = c1.selectbox("Candidate", ["Everyone", "Whole pool"] + [nm[c] for c in ws.candidates])
    stage_labels = sorted({C.STAGES.get(C.val(e.stage), (str(C.val(e.stage)), ""))[0] for e in ws.audit})
    stages = c2.multiselect("Stage", stage_labels, placeholder="All stages")
    text = c3.text_input("Search the trail", placeholder="A claim, a requirement or a word")
    d1, d2, _ = st.columns([1.4, 1.4, 3], vertical_alignment="center")
    limit = d1.selectbox("Show", [25, 50, 100, 250], index=1)
    newest = d2.toggle("Newest first", value=False)
    rev = {v: k for k, v in nm.items()}

    def keep(e) -> bool:
        if who == "Whole pool" and e.candidate_id:
            return False
        if who not in ("Everyone", "Whole pool") and e.candidate_id != rev.get(who):
            return False
        if stages and C.STAGES.get(C.val(e.stage), (str(C.val(e.stage)), ""))[0] not in stages:
            return False
        if text and text.lower() not in (e.insight + " " + " ".join(x.quote for x in e.evidence)).lower():
            return False
        return True

    hits = [e for e in ws.audit if keep(e)]
    if newest:
        hits = hits[::-1]
    quotes = sum(len(e.evidence) for e in hits)
    calls = sum(len(e.tool_calls) for e in hits)
    st.markdown(C.brief([(str(len(hits)), "entries match"), (str(quotes), "source quotes attached"), (str(calls), "web or GitHub calls logged")]), unsafe_allow_html=True)
    if not hits:
        st.markdown(C.empty("No entries match", "Loosen the filters above."), unsafe_allow_html=True)
        return
    rows = [C.audit_row(e, nm.get(e.candidate_id, "Whole pool" if not e.candidate_id else e.candidate_id)) for e in hits[:limit]]
    st.markdown(C.ledger(rows), unsafe_allow_html=True)
    if len(hits) > limit:
        st.caption(f"Showing {limit} of {len(hits)}. Raise the limit above, or filter.")
    download("Download these entries (JSON)", json.dumps([e.model_dump(mode="json") for e in hits], indent=2), "hireflow_audit_trail.json",
             "application/json", "dl_audit")


# ───────────────────────── router ─────────────────────────
def render(page: str, ws: Workspace, be: Backend) -> None:
    {"Setup": view_setup, "Overview": view_overview, "Candidates": view_candidates, "Interviews": view_interviews,
     "Ask the pool": view_ask, "Audit trail": view_audit}[page](ws, be)
