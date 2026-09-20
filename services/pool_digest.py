"""services/pool_digest.py: compact per-candidate text for pool-level questions (about 300 tokens each)."""
from models import VerificationStatus, Workspace


def query_digest(ws: Workspace, max_candidates: int = 15) -> tuple[str, list[str]]:
    """Returns (digest text, candidate ids included). Highest fit score first."""
    ranked = sorted(
        ((cid, r) for cid, r in ws.candidates.items() if r.profile and r.alignment),
        key=lambda x: (x[1].alignment.fit_score, x[1].alignment.must_have_coverage), reverse=True,
    )[:max_candidates]
    blocks, ids = [], []
    for cid, r in ranked:
        p, a = r.profile, r.alignment
        roles = "; ".join(f"{e.title or 'role'} @ {e.company} ({e.start_date}-{e.end_date})" for e in p.experience[:4])
        highlights = " | ".join(x[:160] for e in p.experience[:3] for x in e.achievements[:2])
        bad = "; ".join(v.claim[:60] for v in (r.verification.results if r.verification else [])
                        if v.status in (VerificationStatus.NOT_FOUND, VerificationStatus.CONTRADICTED))
        flags = ", ".join(sorted({f.flag_type.value for f in p.validation_flags}))
        lines = [
            f"[{cid}] {p.full_name} | {p.headline[:70]} | {p.total_years_experience} yrs | fit {a.fit_score} | must-have coverage {a.must_have_coverage}%",
            f"  skills: {', '.join(s.name for s in p.skills[:15])}",
            f"  roles: {roles}",
            f"  highlights: {highlights}",
            f"  projects: {'; '.join(x.name for x in p.projects[:4])} | certifications: {'; '.join(c.name for c in p.certifications[:4])}",
            f"  requirements: {' '.join(f'{m.req_id}={m.status.value}' for m in a.matches)}",
            f"  flags: {flags or 'none'} | unverified claims: {bad or 'none'}",
        ]
        ev = r.interview_evaluation
        if ev:
            lines.append(f"  interview: {ev.assessed_coverage}% of requirements assessed; "
                         + " ".join(f"{e.req_id}={e.level.value}" for e in ev.evidence_map))
        blocks.append("\n".join(lines))
        ids.append(cid)
    return "\n".join(blocks), ids