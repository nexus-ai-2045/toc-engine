"""recommend.py のテスト: if-then ルールの発火条件。"""
from toc_engine.constraint import ConstraintCandidate
from toc_engine.metrics import StageMetrics
from toc_engine.model import Stage, WorkItem


from toc_engine.recommend import recommend


def _metrics(name, wip=5, max_age=None, oldest_title="old-item"):
    oldest = (
        (WorkItem("id1", oldest_title, name, "src", max_age),)
        if max_age is not None
        else ()
    )
    return StageMetrics(
        stage=Stage(name, 0, False),
        wip=wip,
        avg_age_days=max_age,
        max_age_days=max_age,
        oldest=oldest,
    )


def _top(name, score=10.0):
    return ConstraintCandidate(name, score, ("WIP 5 件",))


def test_subordinate_when_wip_keeps_growing():
    recs = recommend(
        [_top("a:inbox")],
        [_metrics("a:inbox")],
        wip_history={"a:inbox": [2, 3, 5]},
    )
    assert any(r.step == "subordinate" for r in recs)
    sub = next(r for r in recs if r.step == "subordinate")
    assert "上流の投入" in sub.text


def test_exploit_when_item_stalls_over_threshold():
    recs = recommend([_top("a:inbox")], [_metrics("a:inbox", max_age=20.0)])
    assert any(r.step == "exploit" for r in recs)
    exp = next(r for r in recs if r.step == "exploit")
    assert "old-item" in exp.evidence[0]


def test_identify_fallback_when_no_rule_fires():
    recs = recommend([_top("a:inbox")], [_metrics("a:inbox", max_age=1.0)])
    assert [r.step for r in recs] == ["identify"]


def test_no_candidates_returns_identify_guidance():
    recs = recommend([], [])
    assert recs[0].step == "identify"
    assert "データソース" in recs[0].text
