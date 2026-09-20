from crew import guards, interview, pipelines
from models import (
    AlignmentReport, CandidateProfile, CandidateRecord, Evidence, EvidenceLevel, FollowUpSet,
    InterviewEvaluationReport, InterviewQuestion, JDRequirement, JobProfile, PoolQueryResult, QueryHit,
    QuestionType, RequirementEvidence, RequirementMatch, SourceType, UnansweredArea, Workspace,
)
from services.report import evaluation_markdown

NOTES = ("Marcus writes Python daily and described a Zomato pipeline that joins order and weather tables in SQL. "
         "He could not say how many requests per second the service handles.")
JOB = JobProfile(title="ML Engineer", requirements=[
    JDRequirement(text="Python"), JDRequirement(text="SQL"), JDRequirement(text="PDF extraction"),
    JDRequirement(text="Open source", priority="nice_to_have"),
])


def _ex(quote):
    return Evidence(source_type="interview_notes", source_id="x", quote=quote)


def _pool():
    ws = Workspace(job=JOB)
    for cid, name, text in (("ananya", "Ananya Rao", "Ananya Rao built RAG assistants with FAISS and deployed FastAPI services."),
                            ("marcus", "Marcus Chen", "Marcus Chen built dashboards in Tableau and sentiment models with BERT.")):
        ws.candidates[cid] = CandidateRecord(
            candidate_id=cid, resume_text=text, profile=CandidateProfile(full_name=name),
            alignment=AlignmentReport(matches=[RequirementMatch(req_id="R1", status="met", rationale="r")]))
    return ws


def test_mislabelled_evidence_type_is_still_checked():
    ev = Evidence(source_type="other", source_id="x", quote="Ten years at NASA leading rockets")
    kept = guards.ground_evidence([ev], guards.Corpus("Built pipelines in Python."), SourceType.RESUME, "c1_resume", guards._Stats())
    assert kept == []


def test_finalize_evaluation_fills_downgrades_and_lists_unanswered():
    rep = InterviewEvaluationReport(notes_summary="s", evidence_map=[
        RequirementEvidence(req_id="R1", level="strong", summary="ok", note_excerpts=[_ex("Marcus writes Python daily")]),
        RequirementEvidence(req_id="R2", level="strong", summary="claims", note_excerpts=[_ex("He built a Spark cluster at NASA")]),
    ])
    out, notes = interview.finalize_evaluation(rep, JOB, NOTES, "c1_notes", "c1", "Sam")
    by = {e.req_id: e for e in out.evidence_map}
    assert list(by) == ["R1", "R2", "R3", "R4"]
    assert by["R1"].level is EvidenceLevel.STRONG and by["R1"].note_excerpts[0].source_id == "c1_notes"
    assert by["R2"].level is EvidenceLevel.NOT_ASSESSED  # fabricated quote -> no rating
    assert by["R4"].priority.value == "nice_to_have"
    assert [u.req_id for u in out.unanswered_areas] == ["R2", "R3", "R4"]
    assert out.assessed_coverage == 25
    assert out.interviewer == "Sam" and out.candidate_id == "c1" and notes


def test_finalize_follow_ups_numbers_caps_and_drops_when_sufficient():
    fs = FollowUpSet(parent_question_id="wrong", answer_assessment="vague", reason="no numbers", follow_ups=[
        InterviewQuestion(question=f"q{i}", rationale="r", target_req_ids=["r1", "R9"]) for i in range(5)])
    out, _ = interview.finalize_follow_ups(fs, "Q3", {"R1", "R2"})
    assert out.parent_question_id == "Q3" and [q.question_id for q in out.follow_ups] == ["Q3-F1", "Q3-F2", "Q3-F3"]
    assert out.follow_ups[0].target_req_ids == ["R1"] and out.follow_ups[0].question_type is QuestionType.VALIDATION
    ok = FollowUpSet(parent_question_id="Q1", answer_assessment="sufficient", reason="good",
                     follow_ups=[InterviewQuestion(question="x", rationale="r")])
    assert interview.finalize_follow_ups(ok, "Q1", {"R1"})[0].follow_ups == []


def test_finalize_query_drops_unknown_candidates_and_ungrounded_quotes():
    ws = _pool()
    res = PoolQueryResult(question="x", answer="a", hits=[
        QueryHit(candidate_id="Ananya Rao", reason="RAG", evidence=[
            Evidence(source_type="other", source_id="?", quote="built RAG assistants with FAISS"),
            Evidence(source_type="resume", source_id="?", quote="led a team of ten at Google")]),
        QueryHit(candidate_id="ghost", reason="?"),
    ])
    out, _ = interview.finalize_query(res, "Who has RAG experience?", ws, ["ananya", "marcus"])
    assert [h.candidate_id for h in out.hits] == ["ananya"]
    assert len(out.hits[0].evidence) == 1 and out.hits[0].evidence[0].source_id == "ananya_resume"
    assert out.question == "Who has RAG experience?"


def test_keyword_fallback_matches_resume_text():
    res = interview.keyword_fallback("Who used FAISS?", _pool(), ["ananya", "marcus"])
    assert [h.candidate_id for h in res.hits] == ["ananya"] and res.answerable


def test_evaluate_interview_end_to_end_with_fake_stage(monkeypatch):
    ws = _pool()

    def fake(stage, agent_key, model, inputs, **kw):
        assert stage == "evaluate"
        ev = {"source_type": "interview_notes", "source_id": "x", "quote": "Ananya explained her FAISS retrieval design in detail"}
        return InterviewEvaluationReport(notes_summary="s", evidence_map=[
            RequirementEvidence(req_id="R1", level="strong", summary="ok", note_excerpts=[ev])]), "fake:m", ""

    monkeypatch.setattr(pipelines, "run_stage", fake)
    notes = "Ananya explained her FAISS retrieval design in detail and answered every follow-up question clearly."
    report, err = interview.evaluate_interview(ws, "ananya", notes, interviewer="Sam")
    rec = ws.candidates["ananya"]
    assert err == "" and report is rec.interview_evaluation and rec.interview_notes
    assert report.evidence_map[0].level is EvidenceLevel.STRONG
    assert any(e.stage.value == "evaluation" for e in ws.audit)


def test_ask_pool_falls_back_to_keywords_when_agent_fails(monkeypatch):
    monkeypatch.setattr(pipelines, "run_stage", lambda *a, **k: (None, "fake:m", "boom"))
    ws = _pool()
    res, err = interview.ask_pool(ws, "Who used FAISS?")
    assert err == "" and res.hits[0].candidate_id == "ananya" and "keyword" in res.answer.lower()
    assert ws.query_history == [res]


def test_evaluation_markdown_has_the_standard_sections():
    ev = InterviewEvaluationReport(
        notes_summary="Solid SQL.", interviewer="Sam",
        evidence_map=[RequirementEvidence(req_id="R1", requirement_text="Python", level="strong", summary="ok",
                                          note_excerpts=[_ex("writes Python daily")])],
        unanswered_areas=[UnansweredArea(req_id="R3", reason="not covered", suggested_question="Tell me about PDFs")])
    rec = CandidateRecord(candidate_id="x", profile=CandidateProfile(full_name="Marcus Chen"), interview_evaluation=ev)
    md = evaluation_markdown(JOB, rec)
    for needle in ("Interview Evaluation Report", "Decision-support", "R1", "Tell me about PDFs", "Marcus Chen"):
        assert needle in md
    assert evaluation_markdown(JOB, CandidateRecord(candidate_id="x")) == ""