"""python check_pipeline.py bakeoff   compare your models on one resume (uses ~3 model calls)
python check_pipeline.py full      JD + all sample resumes end to end (uses many more tokens)"""
import sys
import time
from pathlib import Path

import config
from crew import guards, pipelines
from crew.pipelines import run_stage
import logging

from models import CandidateProfile, CandidateRecord, GroupingResult, SourceType, Workspace

logging.disable(logging.CRITICAL)
from tools.pdf_tools import load_document, slugify

SAMPLES = Path("data/samples")


def _bake(role: str, stage: str, agent: str, model_cls, inputs: dict):
    t0 = time.time()
    out, model, err = run_stage(stage, agent, model_cls, inputs, llm_role=role, fallback=False)
    return out, model, err, time.time() - t0


def bakeoff() -> None:
    resume = (SAMPLES / "resume_ananya_rao.txt").read_text(encoding="utf-8")
    print("Big-schema test (full profile extraction):")
    for role in ("extract", "reason", "fallback"):
        if not config.role_available(role):
            print(f"  {role:9} SKIP (no key)")
            continue
        out, model, err, secs = _bake(role, "extract", "fact_auditor", CandidateProfile,
                                      {"resume_text": resume, "doc_id": "bake_resume"})
        if out is None:
            print(f"  {role:9} {model:38} FAIL {secs:5.1f}s  {err[:150]}")
            continue
        prof, notes = guards.finalize_profile(out, resume, "bake_resume", "bake")
        print(f"  {role:9} {model:38} OK   {secs:5.1f}s  skills={len(prof.skills)} roles={len(prof.experience)} "
              f"projects={len(prof.projects)} certs={len(prof.certifications)} years={prof.total_years_experience}")
        for n in notes:
            print("           ", n)

    print("\nSmall-schema test (candidate grouping) for the light role:")
    pool = ("a | Ananya Rao | ML Engineer | 5.1y | fit 82 | R1=met,R2=met | Python, FAISS\n"
            "b | Marcus Chen | Data Scientist | 5.8y | fit 41 | R1=met,R2=unclear | SQL, Tableau\n"
            "c | Priya Nair | Frontend Developer | 2y | fit 12 | R1=not_met,R2=not_met | React")
    if config.role_available("light"):
        out, model, err, secs = _bake("light", "group", "alignment_architect", GroupingResult,
                                      {"jd_json": '{"title":"ML Engineer"}', "pool_text": pool})
        print(f"  light     {model:38} {'OK  ' if out else 'FAIL'} {secs:5.1f}s  "
              + (f"groups={len(out.groups)}" if out else err[:150]))
    else:
        print("  light     SKIP (no key)")


def show(ws: Workspace, cid: str) -> None:
    r = ws.candidates[cid]
    print(f"\n=== {cid} ===")
    if r.errors:
        print("  ERRORS:", r.errors)
    if r.profile:
        p = r.profile
        print(f"  {p.full_name} | {p.total_years_experience} yrs | {len(p.skills)} skills")
        for f in p.validation_flags:
            print(f"  FLAG   {f.flag_type.value:18} {f.description[:100]}")
    if r.verification:
        for v in r.verification.results:
            print(f"  VERIFY {v.status.value:18} {v.claim[:70]}")
    if r.alignment:
        a = r.alignment
        print(f"  FIT {a.fit_score} | must-have coverage {a.must_have_coverage}% | needs validation: {a.validation_req_ids}")
        for m in a.matches:
            print(f"  {m.req_id:3} {m.status.value:14} evidence={len(m.evidence)}  {m.requirement_text[:55]}")
    if r.interview_kit:
        qs = r.interview_kit.questions
        print(f"  KIT: {len(qs)} questions. First: {qs[0].question[:110]}")


def full() -> None:
    t0 = time.time()
    ws = Workspace()
    err = pipelines.parse_job(ws, (SAMPLES / "jd_ml_engineer.txt").read_text(encoding="utf-8"))
    if err:
        print(err)
        return
    print("JD requirements:")
    for r in ws.job.requirements:
        print(f"  {r.req_id} [{r.priority.value}] {r.text}")
    for f in sorted(SAMPLES.glob("resume_*.txt")):
        doc = load_document(f.read_bytes(), f.name, SourceType.RESUME)
        cid = slugify(f.stem.replace("resume_", ""))
        ws.candidates[cid] = CandidateRecord(candidate_id=cid, filename=f.name, content_hash=doc.content_hash,
                                             resume_text=doc.text)
    pipelines.screen_pool(ws, progress=print)
    for cid in ws.candidates:
        show(ws, cid)
    if ws.grouping:
        print("\nGROUPS")
        for g in ws.grouping.groups:
            print(f"  {g.group_id} {g.label}: {g.candidate_ids}")
    print("\nINTEGRITY NOTES")
    for e in ws.audit:
        if e.insight.startswith(("Integrity", "Timeline", "Security", "Grouping agent failed")):
            print(f"  [{e.candidate_id or 'pool'}] {e.insight}")
        Path(".cache").mkdir(exist_ok=True)
    Path(".cache/workspace.json").write_text(ws.model_dump_json(), encoding="utf-8")
    print("Saved .cache/workspace.json (used by check_interview.py)")        
    print(f"\n{len(ws.audit)} audit entries | {time.time() - t0:.0f}s total")


if __name__ == "__main__":
    {"bakeoff": bakeoff, "full": full}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()