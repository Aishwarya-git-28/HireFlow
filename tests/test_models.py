import pytest

from models import (
    AlignmentReport, Evidence, InterviewEvaluationReport, InterviewKit, InterviewQuestion,
    JDRequirement, JobProfile, MatchStatus, RequirementEvidence, RequirementMatch,
)


def _m(rid, status, prio="MUST_HAVE"):
    return RequirementMatch(req_id=rid, status=status, priority=prio, rationale="x")


def test_enums_accept_messy_llm_casing():
    m = RequirementMatch(req_id="R1", status="Partially Met", priority="must have", rationale="x")
    assert m.status is MatchStatus.PARTIALLY_MET


def test_fit_score_is_computed_in_python():
    rep = AlignmentReport(matches=[_m("R1", "MET"), _m("R2", "NOT_MET"), _m("R3", "MET", "NICE_TO_HAVE")])
    assert rep.fit_score == 57          # (3*1 + 3*0 + 1*1) / 7
    assert rep.must_have_coverage == 50


def test_extra_keys_ignored_and_quote_capped():
    ev = Evidence(source_type="resume", source_id="c1", quote="x" * 999, hallucinated="?")
    assert len(ev.quote) == 300


def test_ids_assigned_by_code():
    jd = JobProfile(title="ML Engineer", requirements=[JDRequirement(text="Python"), JDRequirement(req_id="R1", text="SQL")])
    assert [r.req_id for r in jd.requirements] == ["R1", "R2"]
    kit = InterviewKit(questions=[InterviewQuestion(question="a", rationale="r"), InterviewQuestion(question="b", rationale="r")])
    assert [q.question_id for q in kit.questions] == ["Q1", "Q2"]


def test_empty_alignment_is_rejected():
    with pytest.raises(Exception):
        AlignmentReport(matches=[])


def test_uncovered_requirements_detected():
    rep = InterviewEvaluationReport(notes_summary="s", evidence_map=[RequirementEvidence(req_id="R1", level="strong", summary="ok")])
    assert rep.uncovered_req_ids(["R1", "R2"]) == ["R2"]