"""signals.py のユニットテスト: evaluate() が返す4種のレビュー招集シグナル。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from toc_engine.model import Goal, Snapshot, Stage, WorkItem
from toc_engine.signals import DECLINE_WINDOW, Signal, evaluate

_STAGES = (
    Stage("backlog", 0),
    Stage("doing", 1),
    Stage("done", 2, terminal=True),
)

_GOAL = Goal(statement="ship", throughput_unit="件", target_per_week=3.0)
_GOAL_NO_TARGET = Goal(statement="ship", throughput_unit="件")

_T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)

_KINDS_IN_ORDER = (
    "constraint_moved",
    "health_worsened",
    "throughput_stalled",
    "interval_exceeded",
)


def _item(item_id: str, stage: str, age_days: float | None = None) -> WorkItem:
    return WorkItem(item_id=item_id, title=item_id, stage=stage, source="test", age_days=age_days)


def _snapshot(taken_at: datetime, items: list[WorkItem]) -> Snapshot:
    return Snapshot(taken_at=taken_at, stages=_STAGES, items=tuple(items))


def _by_kind(signals: list[Signal]) -> dict[str, Signal]:
    return {s.kind: s for s in signals}


# --- 共通: 戻り値の形 ---------------------------------------------------


def test_evaluate_returns_four_signals_in_fixed_order():
    signals = evaluate([], _GOAL, max_interval_days=7, last_review_at=None)
    assert [s.kind for s in signals] == list(_KINDS_IN_ORDER)


def test_zero_snapshots_all_false_no_exception():
    signals = evaluate([], _GOAL, max_interval_days=7, last_review_at=None)
    assert len(signals) == 4
    assert all(s.fired is False for s in signals)
    assert all("不足" in s.detail for s in signals)


def test_one_snapshot_all_false_no_exception():
    snapshots = [_snapshot(_T0, [_item("a", "backlog")])]
    signals = evaluate(snapshots, _GOAL, max_interval_days=7, last_review_at=None)
    assert len(signals) == 4
    assert all(s.fired is False for s in signals)


# --- constraint_moved -----------------------------------------------------


def test_constraint_moved_fires_when_top_stage_changes():
    s1 = _snapshot(
        _T0,
        [
            _item("a1", "backlog", age_days=10),
            _item("a2", "backlog", age_days=8),
            _item("a3", "backlog", age_days=6),
            _item("b1", "doing", age_days=1),
        ],
    )
    s2 = _snapshot(
        _T0 + timedelta(days=1),
        [
            _item("a1", "backlog", age_days=1),
            _item("b1", "doing", age_days=20),
            _item("b2", "doing", age_days=18),
            _item("b3", "doing", age_days=16),
        ],
    )
    signals = _by_kind(evaluate([s1, s2], _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["constraint_moved"]
    assert sig.fired is True
    assert "backlog" in sig.detail and "doing" in sig.detail


def test_constraint_moved_does_not_fire_when_top_stage_same():
    s1 = _snapshot(
        _T0,
        [
            _item("a1", "backlog", age_days=10),
            _item("a2", "backlog", age_days=8),
            _item("b1", "doing", age_days=1),
        ],
    )
    s2 = _snapshot(
        _T0 + timedelta(days=1),
        [
            _item("a1", "backlog", age_days=11),
            _item("a2", "backlog", age_days=9),
            _item("a3", "backlog", age_days=5),
            _item("b1", "doing", age_days=2),
        ],
    )
    signals = _by_kind(evaluate([s1, s2], _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["constraint_moved"]
    assert sig.fired is False
    assert "backlog" in sig.detail


# --- health_worsened -------------------------------------------------------


def _completed_snapshot(taken_at: datetime, completed: int) -> Snapshot:
    items = [_item(f"d{i}", "done") for i in range(completed)]
    items.append(_item("wip1", "backlog", age_days=1))
    return _snapshot(taken_at, items)


def test_health_worsened_fires_green_to_red():
    s1 = _completed_snapshot(_T0, 0)
    s2 = _completed_snapshot(_T0 + timedelta(days=7), 3)  # 直近2件で green (rate=3.0)
    s3 = _completed_snapshot(_T0 + timedelta(days=14), 3)  # 全体だと rate=1.5 -> red
    signals = _by_kind(evaluate([s1, s2, s3], _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["health_worsened"]
    assert sig.fired is True
    assert "green" in sig.detail and "red" in sig.detail


def test_health_worsened_does_not_fire_when_zone_unchanged():
    s1 = _completed_snapshot(_T0, 0)
    s2 = _completed_snapshot(_T0 + timedelta(days=7), 3)  # green
    s3 = _completed_snapshot(_T0 + timedelta(days=14), 6)  # 全体でも rate=3.0 -> green
    signals = _by_kind(evaluate([s1, s2, s3], _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["health_worsened"]
    assert sig.fired is False
    assert sig.detail == "ゾーン変化なし"


def test_health_worsened_does_not_fire_without_target():
    s1 = _completed_snapshot(_T0, 0)
    s2 = _completed_snapshot(_T0 + timedelta(days=7), 3)
    signals = _by_kind(
        evaluate([s1, s2], _GOAL_NO_TARGET, max_interval_days=99, last_review_at=None)
    )
    sig = signals["health_worsened"]
    assert sig.fired is False
    assert sig.detail == "目標未設定"


# --- throughput_stalled -----------------------------------------------------


def test_throughput_stalled_fires_when_no_increase_over_window():
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=i), 5) for i in range(DECLINE_WINDOW)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is True


def test_throughput_stalled_does_not_fire_when_increasing():
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=i), i) for i in range(DECLINE_WINDOW)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is False
    assert "完了" in sig.detail


def test_throughput_stalled_insufficient_below_window():
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=i), 5) for i in range(DECLINE_WINDOW - 1)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is False
    assert "不足" in sig.detail


# --- interval_exceeded -------------------------------------------------------


def test_interval_exceeded_fires_when_last_review_is_old():
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=10), 1),
    ]
    last_review_at = _T0 - timedelta(days=5)
    signals = _by_kind(
        evaluate(snaps, _GOAL, max_interval_days=7, last_review_at=last_review_at)
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is True
    assert "日" in sig.detail


def test_interval_exceeded_does_not_fire_when_last_review_is_recent():
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=10), 1),
    ]
    last_review_at = _T0 + timedelta(days=9)
    signals = _by_kind(
        evaluate(snaps, _GOAL, max_interval_days=7, last_review_at=last_review_at)
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is False


def test_interval_exceeded_uses_first_snapshot_when_last_review_none():
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=40), 1),
    ]
    signals = _by_kind(
        evaluate(snaps, _GOAL, max_interval_days=30, last_review_at=None)
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is True


def test_interval_exceeded_handles_naive_last_review_as_utc():
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=10), 1),
    ]
    naive_last_review = datetime(2026, 6, 20)  # tzinfo なし
    signals = _by_kind(
        evaluate(snaps, _GOAL, max_interval_days=7, last_review_at=naive_last_review)
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is True



# --- 回帰: レポート側と同じランク基準を使うこと ---------------------------


def _stage_items(stage: str, count: int) -> list[WorkItem]:
    """滞留 0 日のアイテムを count 件作る (年齢要因を 1.0 に固定するため)。"""
    return [_item(f"{stage}{i}", stage, 0.0) for i in range(count)]


def test_constraint_moved_uses_same_ranking_basis_as_report():
    """成長重み (WIP 履歴) を無視すると、レポート表示と矛盾したシグナルが出る。

    backlog は WIP 10 で横ばい、doing は 4→6→8 と増加。
    - 成長重みなし: backlog(10) > doing(8) → 1 位は backlog のまま =「移動なし」
    - 成長重みあり: doing は 1.5 倍され 12 > 10 → 1 位が doing に移る =「移動あり」
    レポート (cli) は成長重みありで順位を出すため、signals が重みを渡していないと
    「レポートは doing が制約 / シグナルは backlog のまま」と矛盾表示になる。
    """
    from toc_engine.constraint import rank
    from toc_engine.metrics import cfd_series, stage_metrics

    snapshots = [
        _snapshot(_T0, _stage_items("backlog", 10) + _stage_items("doing", 4)),
        _snapshot(_T0 + timedelta(days=1), _stage_items("backlog", 10) + _stage_items("doing", 6)),
        _snapshot(_T0 + timedelta(days=2), _stage_items("backlog", 10) + _stage_items("doing", 8)),
    ]
    report_top = rank(stage_metrics(snapshots[-1]), cfd_series(snapshots))[0].stage_name
    assert report_top == "doing", "前提が崩れている: レポート基準では doing が 1 位のはず"

    moved = _by_kind(evaluate(snapshots, _GOAL, max_interval_days=3.0, last_review_at=None))[
        "constraint_moved"
    ]
    assert report_top in moved.detail, (
        f"レポートの制約 {report_top} が signals の detail '{moved.detail}' に現れない"
        " = ランク基準がズレている"
    )
