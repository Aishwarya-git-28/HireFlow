"""services/audit.py: flatten stage outputs into AuditEntry rows. Every Insight already carries Evidence,
so the trail is a flattening step, not a separate LLM call."""
from models import (
    AlignmentReport, AuditEntry, CandidateProfile, FollowUpSet, GroupingResult, InterviewEvaluationReport,
    InterviewKit, JobProfile, PipelineStage, PoolQueryResult, ToolCallRecord, VerificationReport,
)

STAGE_MAP = {
    "jd_parse": PipelineStage.EXTRACTION, "extract": PipelineStage.EXTRACTION,
    "verify": PipelineStage.VERIFICATION, "align": PipelineStage.ALIGNMENT,
    "kit": PipelineStage.INTERVIEW_KIT, "group": PipelineStage.GROUPING,
    "follow_up": PipelineStage.FOLLOW_UP, "evaluate": PipelineStage.EVALUATION,
    "query": PipelineStage.POOL_QUERY,
}


def entries_for(stage: str, candidate_id: str, agent: str, model: str, obj,
                tool_calls: list[ToolCallRecord] | None = None, notes: list[str] | None = None) -> list[AuditEntry]:
    base = dict(stage=STAGE_MAP[stage], agent=agent, model=model)
    out: list[AuditEntry] = []

    def add(insight: str, evidence=None, calls=None, cid: str | None = None) -> None:
        out.append(AuditEntry(candidate_id=cid or candidate_id, insight=insight[:300],
                              evidence=evidence or [], tool_calls=calls or [], **base))

    for n in notes or []:
        add(n)
    if isinstance(obj, JobProfile):
        for r in obj.requirements:
            add(f"{r.req_id} [{r.priority.value}] {r.text}", r.evidence)
    elif isinstance(obj, CandidateProfile):
        add(f"Extracted {len(obj.skills)} skills, {len(obj.experience)} roles, {len(obj.projects)} projects, "
            f"{len(obj.certifications)} certifications.")
        for f in obj.validation_flags:
            add(f"Flag [{f.flag_type.value}] {f.field}: {f.description}", f.evidence)
    elif isinstance(obj, VerificationReport):
        for r in obj.results:
            add(f"Claim '{r.claim}' -> {r.status.value}: {r.finding}", r.evidence)
    elif isinstance(obj, AlignmentReport):
        for m in obj.matches:
            add(f"{m.req_id} {m.status.value} (confidence {m.confidence:.2f}): {m.rationale}", m.evidence)
        for s in obj.strengths:
            add("Strength: " + s.statement, s.evidence)
        for c in obj.concerns:
            add("Concern: " + c.statement, c.evidence)
    elif isinstance(obj, InterviewKit):
        for q in obj.questions:
            add(f"{q.question_id} ({q.question_type.value}): {q.question} | Why: {q.rationale}", q.basis)
    elif isinstance(obj, GroupingResult):
        for g in obj.groups:
            add(f"{g.group_id} '{g.label}': {', '.join(g.candidate_ids)}. {g.rationale}")
    elif isinstance(obj, FollowUpSet):
        add(f"Answer to {obj.parent_question_id} assessed as {obj.answer_assessment.value}: {obj.reason}")
        for q in obj.follow_ups:
            add(f"{q.question_id}: {q.question} | Why: {q.rationale}", q.basis)
    elif isinstance(obj, InterviewEvaluationReport):
        add("Interview summary: " + obj.notes_summary)
        for e in obj.evidence_map:
            add(f"{e.req_id} [{e.level.value}] {e.summary}", e.note_excerpts)
        for u in obj.unanswered_areas:
            add(f"Unanswered {u.req_id}: {u.reason}")
        for s in obj.strengths:
            add("Strength: " + s.statement, s.evidence)
        for c in obj.concerns:
            add("Concern: " + c.statement, c.evidence)
    elif isinstance(obj, PoolQueryResult):
        add(f"Question: {obj.question} | Answer: {obj.answer}")
        for h in obj.hits:
            add(f"Matched {h.candidate_id}: {h.reason}", h.evidence, cid=h.candidate_id)
    if tool_calls:
        add(f"{len(tool_calls)} tool call(s) made during this stage.", calls=tool_calls)
    return out