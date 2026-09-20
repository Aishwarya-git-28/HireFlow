from crew import pipelines
from models import (
    AlignmentReport, CandidateProfile, CandidateRecord, InterviewKit, InterviewQuestion, JDRequirement,
    JobProfile, RequirementMatch, WorkExperience, Workspace,
)

RESUME = "Ananya Rao. Built a PDF pipeline processing 40,000 invoices per month using Python and SQL on Google Cloud Run."


def _workspace():
    ws = Workspace(job=JobProfile(title="ML Engineer", requirements=[JDRequirement(text="Python"), JDRequirement(text="SQL")]))
    ws.candidates["c1"] = CandidateRecord(candidate_id="c1", filename="r.txt", resume_text=RESUME)
    return ws


def test_failed_verification_degrades_gracefully(monkeypatch):
    def fake(stage, agent_key, model, inputs, **kw):
        if stage == "extract":
            return CandidateProfile(full_name="Ananya", experience=[WorkExperience(company="Infosys", start_date="Jan 2022", end_date="Present")]), "fake:m", ""
        if stage in ("verify_plan", "verify_judge"):
            return None, "fake:m", "boom"
        if stage == "align":
            ev = {"source_type": "resume", "source_id": "x", "quote": "processing 40,000 invoices per month using Python"}
            return AlignmentReport(matches=[RequirementMatch(req_id="R1", status="met", rationale="r", evidence=[ev])]), "fake:m", ""
        if stage == "kit":
            return InterviewKit(questions=[InterviewQuestion(question="q", rationale="r")]), "fake:m", ""
        raise AssertionError(stage)

    monkeypatch.setattr(pipelines, "run_stage", fake)
    from tools import web_tools
    monkeypatch.setattr(web_tools, "search_web_impl", lambda q: "Error: offline test")
    monkeypatch.setattr(web_tools, "check_github_impl", lambda t, u="": "Error: offline test")
    ws = _workspace()
    rec = pipelines.screen_candidate(ws, "c1")
    assert rec.profile and rec.profile.candidate_id == "c1"
    assert any("verify" in e for e in rec.errors)
    assert rec.verification and all(r.status.value == "search_failed" for r in rec.verification.results)
    assert [m.req_id for m in rec.alignment.matches] == ["R1", "R2"]
    assert rec.alignment.matches[1].status.value == "unclear"  # R2 was skipped by the agent
    assert rec.interview_kit and rec.interview_kit.candidate_id == "c1"
    assert ws.audit


def test_extract_failure_stops_that_candidate_only(monkeypatch):
    monkeypatch.setattr(pipelines, "run_stage", lambda *a, **k: (None, "fake:m", "model returned garbage"))
    rec = pipelines.screen_candidate(_workspace(), "c1")
    assert rec.profile is None and "extract" in rec.errors[0]


def test_grouping_falls_back_to_score_tiers(monkeypatch):
    ws = _workspace()
    for cid in ("c1", "c2"):
        ws.candidates[cid] = CandidateRecord(
            candidate_id=cid, profile=CandidateProfile(full_name=cid),
            alignment=AlignmentReport(matches=[RequirementMatch(req_id="R1", status="met", rationale="r")]))
    monkeypatch.setattr(pipelines, "run_stage", lambda *a, **k: (None, "fake:m", "boom"))
    result = pipelines.group_pool(ws)
    assert result is ws.grouping and sorted(i for g in result.groups for i in g.candidate_ids) == ["c1", "c2"]