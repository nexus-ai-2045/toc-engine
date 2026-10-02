"""constraint.py のテスト: スコアリングと除外規則。"""
from datetime import datetime, timezone

from toc_engine.constraint import current_constraint, rank, ranked_candidates
from toc_engine.metrics import StageMetrics
from toc_engine.model import Snapshot, Stage, WorkItem


def _m(name, wip, avg_age=None, terminal=False, order=0):
    return StageMetrics(
        stage=Stage(name, order, terminal),
        wip=wip,
        avg_age_days=avg_age,
        max_age_days=avg_age,
        oldest=(),
    )


def test_rank_orders_by_wip_times_age():
    metrics = [
        _m("a:inbox", wip=10, avg_age=14.0),  # 10 * (1 + 14/7) = 30
        _m("a:drafts", wip=20, avg_age=0.0),  # 20 * 1 = 20
        _m("t:open", wip=5),                  # age 不明 → 5 * 1 = 5
    ]
    result = rank(metrics)
    assert [c.stage_name for c in result] == ["a:inbox", "a:drafts", "t:open"]
    assert result[0].score == 30.0
    assert any("平均滞留 14.0 日" in e for e in result[0].evidence)


def test_rank_excludes_terminal_and_empty():
    metrics = [
        _m("a:published", wip=100, avg_age=30.0, terminal=True),  # 完了置き場は制約でない
        _m("a:inbox", wip=0),                                     # 空工程も除外
        _m("a:drafts", wip=1),
    ]
    result = rank(metrics)
    assert [c.stage_name for c in result] == ["a:drafts"]


def test_rank_growth_factor_from_history():
    metrics = [_m("a:inbox", wip=4), _m("a:drafts", wip=4)]
    history = {"a:inbox": [1, 2, 4], "a:drafts": [4, 4, 4]}
    result = rank(metrics, wip_history=history)
    # 同 WIP でも増加傾向のある方が上位
    assert result[0].stage_name == "a:inbox"
    assert any("増加傾向" in e for e in result[0].evidence)


def test_rank_growth_uses_recent_window_not_first_snapshot():
    # 昔増えて最近は横ばい/減少なら成長扱いしない
    metrics = [_m("a:inbox", wip=4)]
    history = {"a:inbox": [0, 5, 5, 4]}  # hist[-3]=5, hist[-1]=4 → 成長なし
    result = rank(metrics, wip_history=history)
    assert not any("増加傾向" in e for e in result[0].evidence)


# --- current_constraint (回帰: I2 SSOT 化) --------------------------------


_STAGES = (Stage("inbox", 0), Stage("done", 1, terminal=True))


def _snapshot(taken_at, inbox_count):
    items = tuple(
        WorkItem(f"i{i}", f"i{i}", "inbox", "src") for i in range(inbox_count)
    )
    return Snapshot(taken_at=taken_at, stages=_STAGES, items=items)


def test_current_constraint_returns_none_for_empty_history():
    assert current_constraint([]) is None


def test_current_constraint_returns_top_stage_name():
    snapshots = [
        _snapshot(datetime(2026, 1, 1, tzinfo=timezone.utc), 4),
        _snapshot(datetime(2026, 1, 2, tzinfo=timezone.utc), 6),
    ]
    assert current_constraint(snapshots) == "inbox"


# --- ranked_candidates (候補一覧の唯一の入口) -------------------------------


def test_ranked_candidates_returns_empty_for_empty_history():
    assert ranked_candidates([]) == []


def test_ranked_candidates_uses_latest_snapshot_with_wip_history():
    """末尾 snapshot のメトリクスと全履歴の WIP 推移 (成長重み) で順位を出す。"""
    from toc_engine.metrics import cfd_series, stage_metrics

    stages = (Stage("a", 0), Stage("b", 1), Stage("done", 2, terminal=True))

    def snap(day, a_count, b_count):
        items = tuple(
            [WorkItem(f"a{i}", f"a{i}", "a", "src", 0.0) for i in range(a_count)]
            + [WorkItem(f"b{i}", f"b{i}", "b", "src", 0.0) for i in range(b_count)]
        )
        return Snapshot(datetime(2026, 1, 1 + day, tzinfo=timezone.utc), stages, items)

    # a は 10 で横ばい、b は 4 → 6 → 8 と増加。成長重みで b (12) が a (10) を上回る
    snapshots = [snap(0, 10, 4), snap(1, 10, 6), snap(2, 10, 8)]
    result = ranked_candidates(snapshots)
    assert result == rank(stage_metrics(snapshots[-1]), cfd_series(snapshots))
    assert [c.stage_name for c in result] == ["b", "a"]
    assert current_constraint(snapshots) == result[0].stage_name
