"""python check_interview.py   (needs .cache/workspace.json, created by `python check_pipeline.py full`)"""
from pathlib import Path

from crew import interview
from models import Workspace
from services.report import evaluation_markdown

CID = "marcus_chen"
VAGUE = ("It was mostly a team effort. I helped with the models and we shipped things that improved the metrics. "
         "Nothing specific comes to mind right now.")


def main() -> None:
    cache = Path(".cache/workspace.json")
    if not cache.exists():
        print("Run `python check_pipeline.py full` first (it saves .cache/workspace.json).")
        return
    ws = Workspace.model_validate_json(cache.read_text(encoding="utf-8"))
    rec = ws.candidates.get(CID)
    if rec is None or rec.interview_kit is None:
        print(f"'{CID}' has no interview kit in the cache. Check the ERRORS printed by the full run.")
        return

    print("\n--- 1. follow-up questions ---")
    qs = rec.interview_kit.questions
    q = next((x for x in qs if x.question_type.value == "validation"), qs[0])
    print(f"Asked ({q.question_id}): {q.question}\nAnswer given: {VAGUE}")
    fs, err = interview.suggest_follow_ups(ws, CID, q.question_id, VAGUE)
    if fs:
        print(f"Assessment: {fs.answer_assessment.value} | {fs.reason}")
        for f in fs.follow_ups:
            print(f"  {f.question_id}: {f.question}")
    else:
        print("FAILED:", err)

    print("\n--- 2. interview evaluation ---")
    notes = Path("data/samples/interview_notes_marcus.txt").read_text(encoding="utf-8")
    report, err = interview.evaluate_interview(ws, CID, notes, interviewer="Sam K.")
    if report:
        print(f"Coverage {report.assessed_coverage}% | {report.notes_summary[:160]}")
        for e in report.evidence_map:
            print(f"  {e.req_id:3} {e.level.value:13} quotes={len(e.note_excerpts)}  {e.requirement_text[:55]}")
        print("Unanswered:", [u.req_id for u in report.unanswered_areas])
        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        path = out_dir / f"{CID}_evaluation.md"
        path.write_text(evaluation_markdown(ws.job, rec), encoding="utf-8")
        print("Wrote", path)
    else:
        print("FAILED:", err)

    print("\n--- 3. pool queries ---")
    for question in ("Who has experience building RAG or LLM applications?",
                     "Which candidates have claims that could not be verified?",
                     "Who has worked with Kubernetes?"):
        res, err = interview.ask_pool(ws, question)
        print(f"\nQ: {question}")
        if res:
            print(f"A: {res.answer}\n   answerable={res.answerable} hits={[(h.candidate_id, len(h.evidence)) for h in res.hits]}")
        else:
            print("FAILED:", err)
    print(f"\nAudit entries now: {len(ws.audit)}")
    Path("data").mkdir(exist_ok=True)
    Path("data/demo_workspace.json").write_text(ws.model_dump_json(), encoding="utf-8")
    print("Saved data/demo_workspace.json (offline demo data for the dashboard)")


if __name__ == "__main__":
    main()