from crew import pipelines, verification
from models import Evidence, PlannedCheck, SearchPlan, VerificationReport, VerificationResult


def test_default_plan_covers_every_claim_by_type():
    claims = ["Employer: Infosys (Senior ML Engineer)",
              "Certification: Google Professional ML Engineer issued by Google",
              "Project: DocParse-lite (github.com/ananyarao-demo/docparse-lite) - library",
              "Project: Contributor to scikit-learn - fixed bugs"]
    plan = verification.default_plan(claims, "ananya")
    assert [p.claim_id for p in plan] == ["C1", "C2", "C3", "C4"]
    assert plan[0].tool == "search_web" and "Infosys" in plan[0].query_or_target and "(" not in plan[0].query_or_target
    assert plan[2].tool == "check_github" and plan[2].query_or_target == "ananyarao-demo/docparse-lite"
    assert plan[2].username == "ananya" and plan[3].tool == "search_web"


def test_plan_checks_normalises_and_fills_missing(monkeypatch):
    claims = ["Employer: Infosys", "Certification: Google ML issued by Google"]
    fake_plan = SearchPlan(checks=[
        PlannedCheck(claim_id="c1", tool="Search Web", query_or_target="Infosys about"),
        PlannedCheck(claim_id="C9", tool="search_web", query_or_target="junk"),  # no such claim
    ])
    monkeypatch.setattr(pipelines, "run_stage", lambda *a, **k: (fake_plan, "fake:m", ""))
    checks, notes, _ = verification.plan_checks(claims, "")
    assert [(c.claim_id, c.tool) for c in checks] == [("C1", "search_web"), ("C2", "search_web")]
    assert notes


def test_ground_results_drops_invented_urls_and_quotes():
    text = "C1: Employer: Infosys\n  result: 1. Infosys | https://www.infosys.com Infosys is a global IT services company."
    rep = VerificationReport(results=[VerificationResult(
        claim="C1: x", status="verified", source_urls=["https://www.infosys.com", "https://fake.example"],
        evidence=[Evidence(source_type="web_search", source_id="https://www.infosys.com", quote="Infosys is a global IT services company"),
                  Evidence(source_type="web_search", source_id="https://fake.example", quote="Infosys was founded on the moon")])])
    r = verification.ground_results(rep, text).results[0]
    assert r.source_urls == ["https://www.infosys.com"] and len(r.evidence) == 1