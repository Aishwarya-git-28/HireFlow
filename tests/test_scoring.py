from models import AlignmentReport, CandidateGroup, CandidateProfile, CandidateRecord, GroupingResult, RequirementMatch
from services import scoring


def _rec(cid, statuses):
    matches = [RequirementMatch(req_id=f"R{i}", status=s, rationale="x") for i, s in enumerate(statuses, 1)]
    return CandidateRecord(candidate_id=cid, profile=CandidateProfile(full_name=cid), alignment=AlignmentReport(matches=matches))


def test_tier_groups_use_computed_scores():
    recs = {"a": _rec("a", ["MET"] * 5), "b": _rec("b", ["MET", "NOT_MET", "UNCLEAR", "NOT_MET"]), "c": _rec("c", ["NOT_MET"] * 4)}
    labels = {g.label: g.candidate_ids for g in scoring.tier_groups(recs).groups}
    assert labels["Strong fit"] == ["a"] and labels["Limited fit"] == ["b", "c"]


def test_enforce_partition_repairs_llm_mistakes():
    bad = GroupingResult(groups=[
        CandidateGroup(label="X", rationale="r", candidate_ids=["a", "a", "ghost"]),
        CandidateGroup(label="Y", rationale="r", candidate_ids=["ghost2"]),
    ])
    fixed = scoring.enforce_partition(bad, ["a", "b", "c"])
    assert sorted(i for g in fixed.groups for i in g.candidate_ids) == ["a", "b", "c"]


def test_sort_groups_best_first():
    recs = {"c": _rec("c", ["NOT_MET"] * 4), "a": _rec("a", ["MET"] * 5)}
    s = scoring.sort_groups(scoring.tier_groups(recs), recs)
    assert [g.label for g in s.groups] == ["Strong fit", "Limited fit"] and s.groups[0].group_id == "G1"