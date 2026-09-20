"""services/scoring.py: deterministic grouping helpers. The LLM may name groups; code guarantees they are valid."""
from models import CandidateGroup, CandidateRecord, GroupingResult


def fit(rec: CandidateRecord) -> int:
    return rec.alignment.fit_score if rec.alignment else -1


def tier_label(rec: CandidateRecord) -> str:
    a = rec.alignment
    if a is None:
        return "Not yet scored"
    if a.fit_score >= 70 and a.must_have_coverage >= 60:
        return "Strong fit"
    if a.fit_score >= 40:
        return "Partial fit (needs validation)"
    return "Limited fit"


def tier_groups(recs: dict[str, CandidateRecord]) -> GroupingResult:
    """Fallback grouping straight from computed scores (used when the grouping agent fails)."""
    buckets: dict[str, list[str]] = {}
    for cid, r in recs.items():
        buckets.setdefault(tier_label(r), []).append(cid)
    return GroupingResult(groups=[
        CandidateGroup(label=label, rationale=f"Grouped by computed fit score ({len(ids)} candidate(s)).", candidate_ids=ids)
        for label, ids in buckets.items()
    ])


def enforce_partition(result: GroupingResult, all_ids: list[str]) -> GroupingResult:
    """Every candidate in exactly one group: drop unknown and duplicate IDs, collect leftovers."""
    lookup = {i.lower(): i for i in all_ids}
    seen: set[str] = set()
    groups = []
    for g in result.groups:
        ids = []
        for raw in g.candidate_ids:
            cid = lookup.get(raw.strip().lower())
            if cid and cid not in seen:
                seen.add(cid)
                ids.append(cid)
        if ids:
            g.candidate_ids = ids
            groups.append(g)
    missing = [i for i in all_ids if i not in seen]
    if missing:
        groups.append(CandidateGroup(label="Other candidates", rationale="Not placed by the grouping agent.",
                                     candidate_ids=missing))
    return GroupingResult(job_id=result.job_id, groups=groups)


def sort_groups(result: GroupingResult, recs: dict[str, CandidateRecord]) -> GroupingResult:
    """Best group first, by mean fit score. Rebuilding renumbers group IDs G1, G2, ..."""
    def mean_fit(g: CandidateGroup) -> float:
        vals = [fit(recs[i]) for i in g.candidate_ids if i in recs]
        return sum(vals) / len(vals) if vals else -1
    return GroupingResult(job_id=result.job_id, groups=sorted(result.groups, key=mean_fit, reverse=True))


def pool_lines(recs: dict[str, CandidateRecord]) -> str:
    lines = []
    for cid, r in recs.items():
        a, p = r.alignment, r.profile
        statuses = ",".join(f"{m.req_id}={m.status.value}" for m in a.matches)
        skills = ", ".join(s.name for s in p.skills[:8])
        lines.append(f"{cid} | {p.full_name} | {p.headline[:60]} | {p.total_years_experience}y | fit {a.fit_score} | {statuses} | {skills}")
    return "\n".join(lines)