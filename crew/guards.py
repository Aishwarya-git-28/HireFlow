"""crew/guards.py: deterministic guardrails around every LLM output.

The LLM proposes, code disposes:
  * quotes must really exist in the source document (no fabricated evidence)
  * dates, gaps and total experience are computed in Python (LLMs are bad at date maths)
  * outputs are forced complete and correctly labelled (IDs, priorities, one match per requirement)
  * text aimed at manipulating the screener is flagged
Every finalize_* function returns (object, notes). Notes become audit-trail entries.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from models import (
    AlignmentReport, CandidateProfile, ClaimType, Evidence, FlagType, Insight, InterviewKit, JobProfile,
    MatchStatus, RequirementMatch, SourceType, ValidationFlag, VerificationReport, VerificationResult,
    VerificationStatus,
)


# ───────────────────────── quote grounding ─────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


class Corpus:
    """Normalized source text used to check that a quote really appears in it."""

    def __init__(self, text: str):
        self.norm = _norm(text)
        self.tokens = self.norm.split()

    def supports(self, quote: str, threshold: float = 0.7) -> bool:
        parts = [p for p in re.split(r"\.\.\.|…", quote) if len(_norm(p)) >= 8]
        return bool(parts) and all(self._supports_one(p, threshold) for p in parts)
        
    def _supports_one(self, quote: str, threshold: float) -> bool:
        q = _norm(quote)
        if q in self.norm:
            return True
        qt = q.split()  # word-level fuzzy match tolerates small typos and dropped words
        m = SequenceMatcher(None, qt, self.tokens, autojunk=False).find_longest_match(0, len(qt), 0, len(self.tokens))
        return m.size >= 3 and m.size / len(qt) >= threshold


@dataclass
class _Stats:
    seen: int = 0
    dropped: int = 0
    examples: list[str] = field(default_factory=list)


def ground_evidence(evs: list[Evidence], corpus: Corpus, source_type: SourceType, doc_id: str, stats: _Stats) -> list[Evidence]:
    """Keep only evidence whose quote is really in the document. Code also owns source_id.
    The only evidence exempt from the check is web evidence that carries a URL (or 'github')."""
    kept = []
    for e in evs:
        if e.source_type == SourceType.WEB_SEARCH and e.source_id.lower().startswith(("http", "github")):
            kept.append(e)
            continue
        e.source_type = source_type  # a mislabelled type must not dodge the check
        stats.seen += 1
        if corpus.supports(e.quote):
            e.source_id = doc_id
            kept.append(e)
        else:
            stats.dropped += 1
            if len(stats.examples) < 2:
                stats.examples.append(e.quote[:70])
    return kept


def _dropped_note(st: _Stats, what: str) -> list[str]:
    if not st.dropped:
        return []
    ex = "; e.g. " + " | ".join(f"'{q}'" for q in st.examples) if st.examples else ""
    return [f"Integrity check: dropped {st.dropped} of {st.seen} evidence quotes that could not be found in the {what}{ex}."]


# ───────────────────────── prompt-injection scan ─────────────────────────
_INJECTION = re.compile(
    r"(ignore\b[^.\n]{0,40}\b(?:instructions|requirements|rules|criteria)"
    r"|(?:note|message|instruction)s?\s+(?:to|for)\s+(?:the\s+)?(?:ai|llm|model|assistant|screening|system)"
    r"|rate\s+(?:every|all|this)[^.\n]{0,60}\b(?:met|highest|perfect)"
    r"|you\s+are\s+now\b|system\s+prompt"
    r"|disregard\b[^.\n]{0,30}\b(?:above|previous|instructions))",
    re.I,
)
_CODE_OWNED = re.compile(
    r"\bdates?\b|\btimeline\b|\bgaps?\b|\bgraduat|\byears? of experience\b|employment is not listed|\bmanipulat|screening system",
    re.I,
)

def injection_flags(text: str, doc_id: str) -> list[ValidationFlag]:
    flags = []
    for line in text.splitlines():
        if _INJECTION.search(line):
            flags.append(ValidationFlag(
                flag_type=FlagType.SUSPICIOUS_CONTENT,
                field="resume_text",
                description="Text aimed at an AI screening system was found in the document and was ignored.",
                suggested_check="Read the resume manually; this may be an attempt to manipulate automated screening.",
                evidence=[Evidence(source_type=SourceType.RESUME, source_id=doc_id, quote=line.strip()[:300])],
            ))
    return flags[:3]


# ───────────────────────── dates & timeline (pure Python) ─────────────────────────
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def parse_ym(s: str, *, end: bool, today: date) -> tuple[int, int, bool] | None:
    """'Apr 2023', '2022-03', '2021', 'Present' -> (year, month, month_is_precise)."""
    t = (s or "").strip().lower()
    if not t:
        return None
    if re.search(r"present|current|now|ongoing|till date", t):
        return today.year, today.month, True
    m = re.match(r"^(\d{4})[-/](\d{1,2})$", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2)), True
    y = re.search(r"\b(?:19|20)\d{2}\b", t)
    if not y:
        return None
    year = int(y.group())
    mon = re.search(r"\b(" + "|".join(_MONTHS) + r")[a-z]*", t)
    if mon:
        return year, _MONTHS.index(mon.group(1)) + 1, True
    return year, (12 if end else 1), False


def _ym(idx: int) -> str:
    return f"{(idx - 1) // 12}-{(idx - 1) % 12 + 1:02d}"


def timeline_flags(profile: CandidateProfile, today: date) -> tuple[list[ValidationFlag], float | None]:
    """Flags impossible dates and gaps over 6 months; returns total years of experience (overlaps merged)."""
    flags: list[ValidationFlag] = []
    spans: list[tuple[int, int, bool, bool]] = []
    for i, e in enumerate(profile.experience):
        s = parse_ym(e.start_date, end=False, today=today)
        en = parse_ym(e.end_date, end=True, today=today)
        if not (s and en):
            if not e.start_date and not e.end_date:
                flags.append(ValidationFlag(
                    flag_type=FlagType.MISSING_INFO, field=f"experience[{i}].dates",
                    description=f"No dates are given for the role at {e.company}.",
                    suggested_check="Ask for start and end dates.", evidence=e.evidence))
            continue
        si, ei = s[0] * 12 + s[1], en[0] * 12 + en[1]
        if ei < si:
            flags.append(ValidationFlag(
                flag_type=FlagType.INCONSISTENT, field=f"experience[{i}].end_date",
                description=f"The end date ({e.end_date}) is before the start date ({e.start_date}) for the role at {e.company}.",
                suggested_check="Ask for the correct dates.", evidence=e.evidence))
            continue
        e.duration_months = ei - si + 1
        spans.append((si, ei, s[2], en[2]))

    spans.sort()
    total, cur_s, cur_e, cur_ep = 0, None, None, True
    for si, ei, sp, ep in spans:
        if cur_e is None:
            cur_s, cur_e, cur_ep = si, ei, ep
        elif si <= cur_e + 1:  # overlapping or adjacent: merge
            if ei > cur_e:
                cur_e, cur_ep = ei, ep
        else:
            gap = si - cur_e - 1
            if gap > 6 and cur_ep and sp:
                flags.append(ValidationFlag(
                    flag_type=FlagType.TIMELINE_GAP, field="experience",
                    description=f"About {gap} months with no listed role or activity between {_ym(cur_e)} and {_ym(si)}.",
                    suggested_check="Ask what the candidate did during this period."))
            total += cur_e - cur_s + 1
            cur_s, cur_e, cur_ep = si, ei, ep
    if cur_e is not None:
        total += cur_e - cur_s + 1
    return flags, (round(total / 12, 1) if spans else None)


# ───────────────────────── stage finalizers ─────────────────────────
def finalize_job(job: JobProfile, jd_text: str) -> list[str]:
    corpus, st = Corpus(jd_text), _Stats()
    for r in job.requirements:
        r.evidence = ground_evidence(r.evidence, corpus, SourceType.JOB_DESCRIPTION, "jd", st)
    return _dropped_note(st, "job description")


def finalize_profile(profile: CandidateProfile, resume_text: str, doc_id: str, candidate_id: str,
                     today: date | None = None) -> tuple[CandidateProfile, list[str]]:
    corpus, st = Corpus(resume_text), _Stats()
    profile.candidate_id = candidate_id
    for f in profile.validation_flags:  # only the code-side injection scan may use this type
        if f.flag_type == FlagType.SUSPICIOUS_CONTENT:
            f.flag_type = FlagType.UNVERIFIED_CLAIM
    # code owns date, timeline and manipulation flags; drop the model's duplicates of them
    profile.validation_flags = [f for f in profile.validation_flags if not _CODE_OWNED.search(f.description)]
    for coll in (profile.skills, profile.experience, profile.projects, profile.certifications, profile.validation_flags):
        for item in coll:
            item.evidence = ground_evidence(item.evidence, corpus, SourceType.RESUME, doc_id, st)
    notes = _dropped_note(st, "resume")
    date_flags, years = timeline_flags(profile, today or date.today())
    inj = injection_flags(resume_text, doc_id)
    profile.validation_flags += date_flags + inj
    if years is not None:
        profile.total_years_experience = years  # computed, not trusted from the LLM
    profile.links = list(dict.fromkeys(x.strip() for x in profile.links if x.strip()))
    if date_flags:
        notes.append(f"Timeline check (code): {len(date_flags)} date issue(s) found.")
    if inj:
        notes.append("Security check: text aimed at the AI screener was found in the resume and ignored.")
    return profile, notes


def build_claims(profile: CandidateProfile, max_claims: int = 6) -> list[str]:
    """Deterministically choose which claims the Fact Auditor must verify."""
    claims: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        if text.lower() not in seen and len(claims) < max_claims:
            seen.add(text.lower())
            claims.append(text)

    for e in profile.experience[:3]:
         if e.company and not re.search(r"freelanc|self[- ]employed|independent|confidential", e.company, re.I):
              add(f"Employer: {e.company}" + (f" - {e.title}" if e.title else ""))

    for c in profile.certifications[:3]:
        add(f"Certification: {c.name}" + (f" issued by {c.issuer}" if c.issuer else ""))
    for p in profile.projects:
        blob = f"{p.name} {p.description}".lower()
        if p.url or "open source" in blob or "open-source" in blob or "contributor" in blob:
            add(f"Project: {p.name}" + (f" ({p.url})" if p.url else "") + (f" - {p.description[:100]}" if p.description else ""))
    return claims


def github_username(profile: CandidateProfile, resume_text: str) -> str:
    for src in [*profile.links, resume_text]:
        m = re.search(r"github\.com/([A-Za-z0-9-]+)", src, re.I)
        if m:
            return m.group(1)
    return ""


_KIND_TYPE = {"employer": ClaimType.COMPANY, "certification": ClaimType.CERTIFICATION, "project": ClaimType.OPEN_SOURCE_PROJECT}


def finalize_verification(report: VerificationReport, claims: list[str], candidate_id: str,
                          tool_calls_made: int) -> tuple[VerificationReport, list[str]]:
    by_num: dict[int, VerificationResult] = {}
    for r in report.results:
        m = re.match(r"\s*C(\d+)\b", r.claim)
        if m and 1 <= int(m.group(1)) <= len(claims) and int(m.group(1)) not in by_num:
            by_num[int(m.group(1))] = r  # results for invented claims are dropped
    results, missing, discarded, weakened = [], 0, 0, 0
    for i, text in enumerate(claims, start=1):
        r = by_num.get(i)
        if r is None:
            r = VerificationResult(claim=text, status=VerificationStatus.SEARCH_FAILED,
                                   finding="Not checked: the verification agent did not report on this claim.")
            missing += 1
        r.claim = text
        if r.claim_type is ClaimType.OTHER:
            r.claim_type = _KIND_TYPE.get(text.split(":", 1)[0].lower(), ClaimType.OTHER)
        if tool_calls_made == 0 and r.status is not VerificationStatus.SEARCH_FAILED:
            r.status, r.finding = VerificationStatus.SEARCH_FAILED, "No tool calls were made, so this result was discarded."
            discarded += 1
        elif r.status is VerificationStatus.VERIFIED and not (r.source_urls or r.evidence):
            r.status = VerificationStatus.PARTIALLY_VERIFIED  # 'verified' with no source is not verified
            weakened += 1
        results.append(r)
    report.results, report.candidate_id = results, candidate_id
    notes = []
    if missing:
        notes.append(f"Integrity check: {missing} claim(s) were not reported by the agent and are marked search_failed.")
    if discarded:
        notes.append(f"Integrity check: {discarded} result(s) discarded because the agent made no tool calls.")
    if weakened:
        notes.append(f"Integrity check: {weakened} 'verified' result(s) had no source and were downgraded to partially_verified.")
    return report, notes


def finalize_alignment(report: AlignmentReport, job: JobProfile, resume_text: str, doc_id: str,
                       candidate_id: str, profile: CandidateProfile) -> tuple[AlignmentReport, list[str]]:
    corpus, st = Corpus(resume_text), _Stats()
    req_by_id = {r.req_id: r for r in job.requirements}
    kept: dict[str, RequirementMatch] = {}
    for m in report.matches:
        rid = m.req_id.strip().upper()
        if rid in req_by_id and rid not in kept:  # unknown or duplicate IDs are dropped
            m.req_id = rid
            kept[rid] = m
    filled = downgraded = 0
    for rid, req in req_by_id.items():
        m = kept.get(rid)
        if m is None:
            m = RequirementMatch(req_id=rid, status=MatchStatus.UNCLEAR, needs_validation=True,
                                 rationale="The agent did not assess this requirement; treat it as unverified.")
            kept[rid] = m
            filled += 1
        m.requirement_text, m.priority = req.text, req.priority  # code owns these fields
        m.evidence = ground_evidence(m.evidence, corpus, SourceType.RESUME, doc_id, st)
        if m.status in (MatchStatus.MET, MatchStatus.PARTIALLY_MET) and not m.evidence:
            m.status, m.needs_validation = MatchStatus.UNCLEAR, True
            m.rationale = (m.rationale + " [Downgraded to unclear: no verifiable quote from the resume.]").strip()
            downgraded += 1
    report.matches = [kept[r.req_id] for r in job.requirements]

    strengths = []
    for s in report.strengths:
        s.evidence = ground_evidence(s.evidence, corpus, SourceType.RESUME, doc_id, st)
        if s.evidence:  # a strength without a real quote is not a strength
            strengths.append(s)
    report.strengths = strengths[:4]
    for c in report.concerns:
        c.evidence = ground_evidence(c.evidence, corpus, SourceType.RESUME, doc_id, st)
    report.concerns = report.concerns[:4]

    injected = [f for f in profile.validation_flags if f.flag_type == FlagType.SUSPICIOUS_CONTENT]
    for f in injected:
        report.concerns.append(Insight(
            statement="The resume contains text aimed at manipulating automated screening; it was ignored. Review this candidate manually.",
            evidence=f.evidence))
    if injected:  # nothing on this resume is taken at face value
        for m in report.matches:
            if m.status is not MatchStatus.NOT_MET:
                m.needs_validation = True
    report.candidate_id = candidate_id

    notes = _dropped_note(st, "resume")
    if downgraded:
        notes.append(f"Integrity check: {downgraded} requirement(s) claimed as met had no verifiable quote and were downgraded to unclear.")
    if filled:
        notes.append(f"Integrity check: {filled} requirement(s) were skipped by the agent and are marked unclear.")
    return report, notes


def finalize_kit(kit: InterviewKit, job: JobProfile, candidate_id: str) -> tuple[InterviewKit, list[str]]:
    valid = {r.req_id for r in job.requirements}
    kit.candidate_id, kit.role_title = candidate_id, kit.role_title or job.title
    kit.probing_priorities = kit.probing_priorities[:3]
    for q in kit.questions:
        q.target_req_ids = [x.strip().upper() for x in q.target_req_ids if x.strip().upper() in valid]
    notes = []
    if len(kit.questions) > 10:
        kit.questions = kit.questions[:10]
        notes.append("Trimmed the interview kit to 10 questions.")
    return kit, notes