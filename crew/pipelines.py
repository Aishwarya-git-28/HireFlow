"""crew/pipelines.py: orchestration. One-agent Sequential crew per stage, plain Python in between.

Public API (all safe to call from Streamlit; none raise):
    parse_job(ws, jd_text)        -> error string or None
    screen_candidate(ws, cid)     -> CandidateRecord (extract -> verify -> align -> interview kit)
    group_pool(ws)                -> GroupingResult or None
    screen_pool(ws)               -> screen every candidate, then group them
"""

import re
import json
import time
from typing import Callable

from crewai import Crew, Process

import config
from crew import guards
from crew.agents import build_agent
from crew.tasks import build_task
from models import (
    AlignmentReport, CandidateProfile, GroupingResult, InterviewKit, JobProfile, VerificationReport, Workspace,
)
from services import audit, scoring
from tools import web_tools

# Which model role runs which stage (roles are configured in .env).
STAGE_ROLE = {"jd_parse": "extract", "extract": "extract", "verify": "light",
              "align": "extract", "kit": "reason", "group": "light"}
RATE_HINTS = ("429", "rate limit", "rate_limit", "too many requests", "tokens per minute", "quota", "resource_exhausted")
DAILY_HINTS = ("perday", "per day", "daily", "requests per day")
TOO_LARGE = ("413", "request too large", "reduce your message size", "context length", "context_length")
_DEAD: set[str] = set()


def _noop(_: str) -> None:
    pass


# ───────────────────────── helpers ─────────────────────────
def _strip_evidence(x):
    if isinstance(x, dict):
        return {k: _strip_evidence(v) for k, v in x.items() if k not in ("evidence", "basis", "note_excerpts")}
    if isinstance(x, list):
        return [_strip_evidence(i) for i in x]
    return x


def compact_json(obj) -> str:
    """Model -> compact JSON without evidence lists (saves tokens when passing context to later stages)."""
    return json.dumps(_strip_evidence(obj.model_dump(mode="json")), separators=(",", ":"))


def _loose_parse(raw: str, model):
    """Second chance: pull a JSON object out of raw text (code fences, chatter) and validate it."""
    try:
        s = (raw or "").strip()
        a, b = s.find("{"), s.rfind("}")
        return model.model_validate_json(s[a:b + 1]) if 0 <= a < b else None
    except Exception:
        return None


# ───────────────────────── the stage runner ─────────────────────────
def _retry_seconds(msg: str, default: float = 20.0) -> float:
    """Parse 'try again in 7.6s' / 'retry in 1m3.5s' from a provider's rate-limit message."""
    m = re.search(r"(?:try again|retry) in (?:(\d+)m)?(\d+(?:\.\d+)?)(ms|s)", msg, re.I)
    if not m:
        return default
    secs = int(m.group(1) or 0) * 60 + float(m.group(2)) / (1000 if m.group(3).lower() == "ms" else 1)
    return min(max(secs, 1.0), 65.0)


def run_stage(stage: str, agent_key: str, output_model, inputs: dict, *, tools=None,
              llm_role: str = "reason", fallback: bool = True):
    """Run ONE specialist on ONE task (a one-agent Sequential crew). Never raises. Free-tier aware:
      - a DAILY quota error retires that model for this run and hops to the next one
      - a PER-MINUTE limit waits as long as the provider asks, then retries the same model
      - 'request too large' hops to a different model (waiting cannot shrink the request)
    Returns (output | None, model_used, error)."""
    queue = [llm_role, llm_role]
    if fallback and llm_role != "fallback":
        queue.append("fallback")
    model_used, last_err, waits = config.ROLE_MODELS.get(llm_role, llm_role), "", 0
    while queue:
        role = queue.pop(0)
        spec = config.ROLE_MODELS.get(role, role)
        if not config.role_available(role):
            last_err = f"No API key configured for role '{role}'."
            continue
        if spec in _DEAD:
            last_err = f"{spec}: daily free quota already used up."
            continue
        model_used = spec
        try:
            agent = build_agent(agent_key, config.build_llm(role), tools)
            task = build_task(stage, agent, output_model)
            crew = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                        verbose=False, max_rpm=config.MAX_RPM)
            result = crew.kickoff(inputs=inputs)
            out = getattr(result, "pydantic", None) or _loose_parse(getattr(result, "raw", ""), output_model)
            if out is not None:
                return out, model_used, ""
            last_err = f"{model_used} returned output that did not match the {output_model.__name__} schema."
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            last_err = f"{model_used}: {type(e).__name__}: {msg[:160]}"
            if any(h in low for h in TOO_LARGE):
                queue = [r for r in queue if config.ROLE_MODELS.get(r, r) != spec]
            elif any(h in low for h in RATE_HINTS):
                if any(h in low for h in DAILY_HINTS):
                    _DEAD.add(spec)
                    queue = [r for r in queue if config.ROLE_MODELS.get(r, r) not in _DEAD]
                elif waits < 4:
                    waits += 1
                    wait = _retry_seconds(msg) + 1
                    print(f"  ...{spec} is rate-limited; waiting {wait:.0f}s", flush=True)
                    time.sleep(wait)
                    queue.insert(0, role)
                else:
                    queue = [r for r in queue if config.ROLE_MODELS.get(r, r) != spec]
    return None, model_used, last_err
# ───────────────────────── stages ─────────────────────────
def parse_job(ws: Workspace, jd_text: str) -> str | None:
    out, model, err = run_stage("jd_parse", "alignment_architect", JobProfile, {"jd_text": jd_text},
                                llm_role=STAGE_ROLE["jd_parse"])
    if out is None:
        return f"Job description parsing failed: {err}"
    out.job_id = "jd"
    notes = guards.finalize_job(out, jd_text)
    ws.job, ws.jd_text = out, jd_text
    ws.audit.extend(audit.entries_for("jd_parse", "", "alignment_architect", model, out, notes=notes))
    return None


def screen_candidate(ws: Workspace, cid: str, progress: Callable[[str], None] = _noop):
    """Extract -> verify -> align -> interview kit. Each stage is isolated: a failure is recorded on the
    record and later stages degrade gracefully instead of crashing. Finished stages are never re-run."""
    rec, job = ws.candidates[cid], ws.job
    if job is None:
        rec.errors.append("The job description has not been parsed yet.")
        return rec
    doc_id, label = f"{cid}_resume", rec.filename or cid

    if rec.profile is None:
        progress(f"{label}: extracting profile")
        out, model, err = run_stage("extract", "fact_auditor", CandidateProfile,
                                    {"resume_text": rec.resume_text, "doc_id": doc_id}, llm_role=STAGE_ROLE["extract"])
        if out is None:
            rec.errors.append(f"extract failed: {err}")
            return rec  # nothing else can run without a profile
        rec.profile, notes = guards.finalize_profile(out, rec.resume_text, doc_id, cid)
        ws.audit.extend(audit.entries_for("extract", cid, "fact_auditor", model, rec.profile, notes=notes))

    if rec.verification is None:
        claims = guards.build_claims(rec.profile)
        report, model, calls, vnotes = VerificationReport(), "", [], []
        if claims:
            progress(f"{label}: verifying {len(claims)} claims on the web")
            from crew import verification  # imported here to avoid a circular import
            out, model, calls, vnotes, err = verification.verify_claims(
                claims, guards.github_username(rec.profile, rec.resume_text))
            if out is None:
                rec.errors.append(f"verify failed: {err}")  # graceful: every claim becomes search_failed
            else:
                report = out
        rec.verification, notes = guards.finalize_verification(report, claims, cid, len(calls))
        ws.audit.extend(audit.entries_for("verify", cid, "fact_auditor", model, rec.verification,
                                          tool_calls=calls, notes=vnotes + notes))

    if rec.alignment is None:
        progress(f"{label}: mapping against job requirements")
        inputs = {"jd_json": compact_json(job), "profile_json": compact_json(rec.profile),
                  "verification_json": compact_json(rec.verification),
                  "resume_text": rec.resume_text, "doc_id": doc_id}
        out, model, err = run_stage("align", "alignment_architect", AlignmentReport, inputs, llm_role=STAGE_ROLE["align"])
        if out is None:
            rec.errors.append(f"align failed: {err}")
            return rec
        rec.alignment, notes = guards.finalize_alignment(out, job, rec.resume_text, doc_id, cid, rec.profile)
        ws.audit.extend(audit.entries_for("align", cid, "alignment_architect", model, rec.alignment, notes=notes))

    if rec.interview_kit is None:
        progress(f"{label}: writing interview kit")
        inputs = {"jd_json": compact_json(job), "profile_json": compact_json(rec.profile),
                  "alignment_json": compact_json(rec.alignment), "verification_json": compact_json(rec.verification)}
        out, model, err = run_stage("kit", "interview_strategist", InterviewKit, inputs, llm_role=STAGE_ROLE["kit"])
        if out is None:
            rec.errors.append(f"kit failed: {err}")
        else:
            rec.interview_kit, notes = guards.finalize_kit(out, job, cid)
            ws.audit.extend(audit.entries_for("kit", cid, "interview_strategist", model, rec.interview_kit, notes=notes))
    return rec


def group_pool(ws: Workspace, progress: Callable[[str], None] = _noop):
    scored = {cid: r for cid, r in ws.candidates.items() if r.alignment and r.profile}
    if not scored or ws.job is None:
        return None
    model, notes = "", []
    result = None
    if len(scored) >= 2:
        progress("Grouping candidates")
        out, model, err = run_stage("group", "alignment_architect", GroupingResult,
                                    {"jd_json": compact_json(ws.job), "pool_text": scoring.pool_lines(scored)},
                                    llm_role=STAGE_ROLE["group"])
        if out is not None:
            result = scoring.enforce_partition(out, list(scored))
        else:
            notes.append(f"Grouping agent failed ({err[:100]}); used score-based tiers instead.")
    if result is None:  # deterministic fallback: tiers from the computed fit score
        result = scoring.tier_groups(scored)
    ws.grouping = scoring.sort_groups(result, scored)
    ws.audit.extend(audit.entries_for("group", "", "alignment_architect", model, ws.grouping, notes=notes))
    return ws.grouping


def screen_pool(ws: Workspace, progress: Callable[[str], None] = _noop):
    for cid in list(ws.candidates):
        try:
            screen_candidate(ws, cid, progress)
        except Exception as e:  # last-resort net: one candidate can never sink the batch
            ws.candidates[cid].errors.append(f"unexpected error: {type(e).__name__}: {str(e)[:150]}")
    return group_pool(ws, progress)