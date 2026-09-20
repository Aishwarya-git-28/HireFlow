"""models.py: HireFlow data contracts.

Rules for this file:
  * Every CrewAI task uses one of these as `output_pydantic`.
  * Field descriptions ARE prompts (CrewAI sends the JSON schema to the LLM).
  * Strict on shape (required fields, enums), forgiving on noise (casing, extra keys, long quotes).
  * IDs and scores are computed by CODE, never trusted from the LLM.
  * Every insight carries Evidence -> the audit trail exists by construction.
"""
import hashlib
import re
import uuid
from datetime import datetime, timezone
from enum import Enum, StrEnum, auto
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, computed_field, field_validator

HUMAN_DECISION_NOTE = "Decision-support only. The hiring decision rests with the hiring team."


# ───────────────────────── helpers ─────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def content_hash(*parts: str | bytes) -> str:
    """Stable cache key for st.session_state (file bytes + JD text + model name, etc.)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode("utf-8"))
    return h.hexdigest()[:16]


def _flex(enum_cls: type[Enum]):
    """Annotated enum that tolerates 'Partially Met', 'partially-met', 'PARTIALLY_MET'."""

    def _coerce(v):
        if isinstance(v, str):
            key = re.sub(r"[\s\-/]+", "_", v.strip()).upper()
            for member in enum_cls:
                if member.name == key:
                    return member
        return v

    return Annotated[enum_cls, BeforeValidator(_coerce)]


def _clamp01(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    f = f / 100 if f > 1 else f  # tolerate 85 meaning 0.85
    return min(1.0, max(0.0, f))


Confidence = Annotated[float, BeforeValidator(_clamp01)]


class HFModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ───────────────────────── enums ─────────────────────────
class SourceType(StrEnum):
    RESUME = auto()
    JOB_DESCRIPTION = auto()
    WEB_SEARCH = auto()
    INTERVIEW_NOTES = auto()
    OTHER = auto()


class Priority(StrEnum):
    MUST_HAVE = auto()
    NICE_TO_HAVE = auto()


class ReqCategory(StrEnum):
    SKILL = auto()
    EXPERIENCE = auto()
    EDUCATION = auto()
    CERTIFICATION = auto()
    DOMAIN = auto()
    SOFT_SKILL = auto()
    OTHER = auto()


class MatchStatus(StrEnum):
    MET = auto()
    PARTIALLY_MET = auto()
    NOT_MET = auto()
    UNCLEAR = auto()  # resume is silent or ambiguous -> needs validation


class FlagType(StrEnum):
    MISSING_INFO = auto()
    UNCLEAR = auto()
    INCONSISTENT = auto()
    TIMELINE_GAP = auto()
    UNVERIFIED_CLAIM = auto()
    SUSPICIOUS_CONTENT = auto()


class ClaimType(StrEnum):
    COMPANY = auto()
    OPEN_SOURCE_PROJECT = auto()
    CERTIFICATION = auto()
    EDUCATION = auto()
    OTHER = auto()


class VerificationStatus(StrEnum):
    VERIFIED = auto()
    PARTIALLY_VERIFIED = auto()
    NOT_FOUND = auto()
    CONTRADICTED = auto()
    SEARCH_FAILED = auto()  # tool error: this is NOT evidence against the candidate


class QuestionType(StrEnum):
    TECHNICAL = auto()
    BEHAVIORAL = auto()
    SITUATIONAL = auto()
    VALIDATION = auto()  # probes a gap or an unverified claim


class AnswerAssessment(StrEnum):
    SUFFICIENT = auto()
    VAGUE = auto()
    INCONSISTENT = auto()
    UNSUPPORTED = auto()


class EvidenceLevel(StrEnum):
    STRONG = auto()
    PARTIAL = auto()
    WEAK = auto()
    CONTRADICTED = auto()
    NOT_ASSESSED = auto()


class PipelineStage(StrEnum):
    EXTRACTION = auto()
    VERIFICATION = auto()
    ALIGNMENT = auto()
    GROUPING = auto()
    INTERVIEW_KIT = auto()
    FOLLOW_UP = auto()
    EVALUATION = auto()
    POOL_QUERY = auto()


SourceTypeT = _flex(SourceType)
PriorityT = _flex(Priority)
ReqCategoryT = _flex(ReqCategory)
MatchStatusT = _flex(MatchStatus)
FlagTypeT = _flex(FlagType)
ClaimTypeT = _flex(ClaimType)
VerificationStatusT = _flex(VerificationStatus)
QuestionTypeT = _flex(QuestionType)
AnswerAssessmentT = _flex(AnswerAssessment)
EvidenceLevelT = _flex(EvidenceLevel)
PipelineStageT = _flex(PipelineStage)


# ───────────────────────── provenance (audit backbone) ─────────────────────────
class Evidence(HFModel):
    """Pointer to the exact source text behind a claim."""

    source_type: SourceTypeT
    source_id: str = Field(description="Stable ID of the document or URL, e.g. 'cand_01_resume', 'jd', or a web URL.")
    locator: str = Field(default="", description="Where in the source: page number, section heading, or line range.")
    quote: str = Field(default="", description="Verbatim excerpt (max 300 chars) that supports the claim.")

    @field_validator("quote")
    @classmethod
    def _cap_quote(cls, v: str) -> str:
        return v[:300]


class Insight(HFModel):
    """One recruiter-facing statement plus the evidence it was derived from."""

    statement: str = Field(description="A single factual, specific sentence. No hire/reject verdicts.")
    evidence: list[Evidence] = Field(default_factory=list, description="Every source excerpt that supports the statement.")


# ───────────────────────── job description ─────────────────────────
class JDRequirement(HFModel):
    req_id: str = Field(default="", description="Leave empty; IDs (R1, R2, ...) are assigned by code.")
    text: str = Field(description="One atomic, testable requirement, e.g. '3+ years building REST APIs in Python'.")
    category: ReqCategoryT = ReqCategory.OTHER
    priority: PriorityT = Field(default=Priority.MUST_HAVE, description="must_have unless the JD says preferred/bonus/nice-to-have.")
    evidence: list[Evidence] = Field(default_factory=list)


class JobProfile(HFModel):
    job_id: str = "jd"
    title: str
    seniority: str = ""
    summary: str = Field(default="", description="Two sentences on the role.")
    requirements: list[JDRequirement] = Field(min_length=1, description="Granular requirements, one skill or experience per item.")

    @field_validator("requirements")
    @classmethod
    def _assign_ids(cls, reqs: list[JDRequirement]) -> list[JDRequirement]:
        for i, r in enumerate(reqs, 1):
            r.req_id = f"R{i}"
        return reqs


# ───────────────────────── candidate profile ─────────────────────────
class Skill(HFModel):
    name: str
    years: float | None = Field(default=None, description="Years of use ONLY if stated or clearly derivable; else null.")
    evidence: list[Evidence] = Field(default_factory=list)


class WorkExperience(HFModel):
    company: str
    title: str = ""
    start_date: str = Field(default="", description="'YYYY-MM' or 'YYYY' as written; empty if absent.")
    end_date: str = Field(default="", description="'YYYY-MM', 'YYYY' or 'Present'; empty if absent.")
    duration_months: int | None = None
    achievements: list[str] = Field(default_factory=list, description="Concrete outcomes, keep numbers as written.")
    technologies: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Project(HFModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str = ""
    achievements: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Education(HFModel):
    institution: str
    degree: str = ""
    field_of_study: str = ""
    end_year: str = ""


class Certification(HFModel):
    name: str
    issuer: str = ""
    year: str = ""
    credential_url: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class ValidationFlag(HFModel):
    """Something missing, unclear or inconsistent that a human should check."""

    flag_type: FlagTypeT
    field: str = Field(description="Profile area, e.g. 'experience[1].end_date' or 'certifications'.")
    description: str
    suggested_check: str = Field(default="", description="What the recruiter should ask or verify.")
    evidence: list[Evidence] = Field(default_factory=list)


class CandidateProfile(HFModel):
    """Extraction ONLY. Never invent; leave fields empty when the resume is silent."""

    candidate_id: str = Field(default="", description="Leave empty; assigned by code.")
    full_name: str = "Unknown candidate"
    headline: str = ""
    links: list[str] = Field(default_factory=list, description="GitHub, LinkedIn, portfolio URLs found in the resume.")
    total_years_experience: float | None = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    validation_flags: list[ValidationFlag] = Field(default_factory=list)


# ───────────────────────── web verification ─────────────────────────
class VerificationResult(HFModel):
    claim: str = Field(description="The resume claim checked, e.g. 'Contributor to Apache Airflow'.")
    claim_type: ClaimTypeT = ClaimType.OTHER
    status: VerificationStatusT
    finding: str = Field(default="", description="What the search actually showed, in 1-2 sentences.")
    source_urls: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list, description="Resume excerpt for the claim + web excerpt(s) checked.")


class VerificationReport(HFModel):
    candidate_id: str = ""
    results: list[VerificationResult] = Field(default_factory=list)


# ───────────────────────── alignment & summary ─────────────────────────
MATCH_CREDIT = {MatchStatus.MET: 1.0, MatchStatus.PARTIALLY_MET: 0.5, MatchStatus.UNCLEAR: 0.0, MatchStatus.NOT_MET: 0.0}
PRIORITY_WEIGHT = {Priority.MUST_HAVE: 3, Priority.NICE_TO_HAVE: 1}


class RequirementMatch(HFModel):
    req_id: str = Field(description="Exact ID from the JobProfile, e.g. 'R3'.")
    requirement_text: str = Field(default="", description="Copy of the requirement text for display.")
    priority: PriorityT = Field(default=Priority.MUST_HAVE, description="Copy from the JobProfile.")
    status: MatchStatusT = Field(description="met | partially_met | not_met | unclear. Use unclear when the resume is silent or ambiguous.")
    rationale: str = Field(description="1-2 sentences tying the status to specific resume facts.")
    confidence: Confidence = 0.5
    needs_validation: bool = Field(default=False, description="True if a human should verify this before relying on it.")
    evidence: list[Evidence] = Field(default_factory=list, description="Resume/web excerpts used. Empty only when status is not_met/unclear.")


class AlignmentReport(HFModel):
    candidate_id: str = ""
    matches: list[RequirementMatch] = Field(min_length=1, description="Exactly one entry per JD requirement.")
    strengths: list[Insight] = Field(default_factory=list)
    concerns: list[Insight] = Field(default_factory=list)
    recruiter_summary: str = Field(default="", description="~3 sentences, factual, no hire/reject recommendation.")

    # Computed in Python so scores are reproducible. Never ask the LLM to do arithmetic.
    @computed_field
    @property
    def fit_score(self) -> int:
        total = sum(PRIORITY_WEIGHT[m.priority] for m in self.matches)
        got = sum(PRIORITY_WEIGHT[m.priority] * MATCH_CREDIT[m.status] for m in self.matches)
        return round(100 * got / total) if total else 0

    @computed_field
    @property
    def must_have_coverage(self) -> int:
        must = [m for m in self.matches if m.priority == Priority.MUST_HAVE]
        return round(100 * sum(m.status == MatchStatus.MET for m in must) / len(must)) if must else 100

    @computed_field
    @property
    def validation_req_ids(self) -> list[str]:
        return [m.req_id for m in self.matches if m.status == MatchStatus.UNCLEAR or m.needs_validation]

    @computed_field
    @property
    def decision_note(self) -> str:
        return HUMAN_DECISION_NOTE


# ───────────────────────── pool-level grouping ─────────────────────────
class CandidateGroup(HFModel):
    group_id: str = ""
    label: str = Field(description="Short human label, e.g. 'Strong backend, thin on cloud'.")
    rationale: str
    candidate_ids: list[str] = Field(min_length=1)
    shared_strength_req_ids: list[str] = Field(default_factory=list)
    shared_gap_req_ids: list[str] = Field(default_factory=list)


class GroupingResult(HFModel):
    job_id: str = "jd"
    groups: list[CandidateGroup] = Field(min_length=1)

    @field_validator("groups")
    @classmethod
    def _assign_ids(cls, groups: list[CandidateGroup]) -> list[CandidateGroup]:
        for i, g in enumerate(groups, 1):
            g.group_id = f"G{i}"
        return groups


# ───────────────────────── interview kit & follow-ups ─────────────────────────
class InterviewQuestion(HFModel):
    question_id: str = Field(default="", description="Leave empty; assigned by code.")
    question: str
    question_type: QuestionTypeT = QuestionType.TECHNICAL
    target_req_ids: list[str] = Field(default_factory=list, description="JD requirement IDs this question tests.")
    rationale: str = Field(description="Why THIS candidate gets THIS question: name the gap, claim or project being probed.")
    expected_signals: list[str] = Field(default_factory=list, description="What a strong answer contains.")
    red_flags: list[str] = Field(default_factory=list, description="What a weak or evasive answer looks like.")
    basis: list[Evidence] = Field(default_factory=list, description="Profile excerpts that motivated the question.")


class InterviewKit(HFModel):
    candidate_id: str = ""
    role_title: str = ""
    probing_priorities: list[str] = Field(default_factory=list, description="Top 3 areas to validate, most important first.")
    questions: list[InterviewQuestion] = Field(min_length=1)

    @field_validator("questions")
    @classmethod
    def _number_questions(cls, qs: list[InterviewQuestion]) -> list[InterviewQuestion]:
        for i, q in enumerate(qs, 1):
            q.question_id = f"Q{i}"
        return qs


class FollowUpSet(HFModel):
    parent_question_id: str
    answer_assessment: AnswerAssessmentT
    reason: str = Field(description="What in the answer needs deeper validation.")
    follow_ups: list[InterviewQuestion] = Field(default_factory=list)


# ───────────────────────── post-interview evaluation ─────────────────────────
class RequirementEvidence(HFModel):
    req_id: str
    requirement_text: str = "" 
    priority: PriorityT = Priority.MUST_HAVE
    level: EvidenceLevelT = Field(description="How strongly the interview notes evidence this requirement.")
    summary: str
    note_excerpts: list[Evidence] = Field(default_factory=list, description="Excerpts from the interview notes.")


class UnansweredArea(HFModel):
    req_id: str
    reason: str
    suggested_question: str = ""


class InterviewEvaluationReport(HFModel):
    candidate_id: str = ""
    interviewer: str = ""
    notes_summary: str
    evidence_map: list[RequirementEvidence] = Field(default_factory=list)
    unanswered_areas: list[UnansweredArea] = Field(default_factory=list)
    strengths: list[Insight] = Field(default_factory=list)
    concerns: list[Insight] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)

    def uncovered_req_ids(self, all_req_ids: list[str]) -> list[str]:
        """Code-side safety net: any JD requirement the LLM skipped counts as unanswered."""
        assessed = {e.req_id for e in self.evidence_map if e.level != EvidenceLevel.NOT_ASSESSED}
        return [r for r in all_req_ids if r not in assessed]

    @computed_field
    @property
    def assessed_coverage(self) -> int:
        n = len(self.evidence_map)
        done = sum(e.level != EvidenceLevel.NOT_ASSESSED for e in self.evidence_map)
        return round(100 * done / n) if n else 0

    @computed_field
    @property
    def decision_note(self) -> str:
        return HUMAN_DECISION_NOTE


# ───────────────────────── natural-language pool query ─────────────────────────
class QueryHit(HFModel):
    candidate_id: str
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)


class PoolQueryResult(HFModel):
    question: str
    answer: str = Field(description="Answer using ONLY the provided candidate data.")
    hits: list[QueryHit] = Field(default_factory=list)
    answerable: bool = Field(default=True, description="False if the pool data cannot answer the question.")


# ───────────────────────── audit trail ─────────────────────────
class ToolCallRecord(HFModel):
    tool_name: str
    input_summary: str = ""
    ok: bool = True
    output_summary: str = ""
    timestamp: str = Field(default_factory=_now)


class AuditEntry(HFModel):
    entry_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = Field(default_factory=_now)
    candidate_id: str = ""
    stage: PipelineStageT
    agent: str = ""
    model: str = ""
    insight: str
    evidence: list[Evidence] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


# ───────────────────────── session container ─────────────────────────
class CandidateRecord(HFModel):
    """Everything known about one candidate. A stage that failed stays None; the rest survives."""

    candidate_id: str
    filename: str = ""
    content_hash: str = ""
    profile: CandidateProfile | None = None
    verification: VerificationReport | None = None
    alignment: AlignmentReport | None = None
    interview_kit: InterviewKit | None = None
    interview_evaluation: InterviewEvaluationReport | None = None
    errors: list[str] = Field(default_factory=list)
    resume_text: str = ""
    interview_notes: str = ""
    follow_ups: list[FollowUpSet] = Field(default_factory=list)


class Workspace(HFModel):
    """The single object stored in st.session_state['workspace']."""

    job: JobProfile | None = None
    candidates: dict[str, CandidateRecord] = Field(default_factory=dict)
    grouping: GroupingResult | None = None
    audit: list[AuditEntry] = Field(default_factory=list)
    jd_text: str = ""
    query_history: list[PoolQueryResult] = Field(default_factory=list)

# ───────────────────────── loaded input files (Phase 2) ─────────────────────────
class SourceDocument(HFModel):
    """A loaded input file. `doc_id` is what Evidence.source_id points at."""

    doc_id: str
    filename: str = ""
    source_type: SourceTypeT = SourceType.OTHER
    text: str = ""
    page_count: int = 0
    content_hash: str = ""
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    ok: bool = True
    error: str = ""

class PlannedCheck(HFModel):
    claim_id: str = Field(description="ID of the claim this check verifies, e.g. 'C2'.")
    tool: str = Field(description="'search_web' or 'check_github'.")
    query_or_target: str = Field(description="The exact search query, or the GitHub owner/repo or URL.")
    username: str = Field(default="", description="The candidate's GitHub username (check_github only).")


class SearchPlan(HFModel):
    checks: list[PlannedCheck] = Field(default_factory=list)