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


def _weekly_snapshots(counts: list[int]) -> list[Snapshot]:
    """週次 (7 日間隔) の snapshot 列。counts[i] は i 週目時点の完了累計。"""
    return [
        _completed_snapshot(_T0 + timedelta(days=7 * i), c) for i, c in enumerate(counts)
    ]


# 以下 3 件は、判定窓を「snapshot 件数」から「期間数」に直した時にデータを作り直した。
# 旧実装は snapshot 3 件 (= 週次なら 2 期間) で比較できたが、新実装は直近
# DECLINE_WINDOW 期間とその直前の DECLINE_WINDOW 期間を比べるため、
# 2 * DECLINE_WINDOW (= 6) 期間 = 週次 snapshot 7 件が要る。検証している性質は同じ。


def test_health_worsened_fires_green_to_red():
    # 前半 3 期間は 3 件/週 (目標 3 → green)、後半 3 期間は 0 件/週 (red)
    snaps = _weekly_snapshots([0, 3, 6, 9, 9, 9, 9])
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["health_worsened"]
    assert sig.fired is True
    assert "green" in sig.detail and "red" in sig.detail


def test_health_worsened_does_not_fire_when_zone_unchanged():
    # 全期間 3 件/週 → 前後とも green
    snaps = _weekly_snapshots([0, 3, 6, 9, 12, 15, 18])
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
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


def test_health_worsened_fires_on_recent_window_when_cumulative_average_would_hide_it():
    """回帰: I4。累計平均では長い好調期に薄まって検知できない直近の急減速を検知する。

    7 期間は 4 件/週で積み上がった後、直近 3 期間だけ 1 件/週に急減速する。
    初回からの累計平均は 31 件 / 10 週 = 3.1 件/週で green のまま変わらないが、
    期間単位の窓同士の比較なら green→red の悪化として捉えられる。

    旧データ [0, 2, 5, 9, 14, 20, 20, 30, 31, 32] は「直近 snapshot 3 件 (= 2 期間)」
    の窓を前提にしていた。期間数の窓 (直近 3 期間 = +10, +1, +1 で 4 件/週) では
    減速にならないため、同じ性質を検証できるデータに作り直した。
    """
    from toc_engine.health import throughput_health
    from toc_engine.metrics import throughput_series

    snaps = _weekly_snapshots([0, 4, 8, 12, 16, 20, 24, 28, 29, 30, 31])
    cumulative = throughput_health(throughput_series(snaps), _GOAL.target_per_week)
    assert cumulative.zone == "green", "前提: 累計平均では悪化が見えない"
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["health_worsened"]
    assert sig.fired is True
    assert "green" in sig.detail and "red" in sig.detail


_GOAL_10 = Goal(statement="ship", throughput_unit="件", target_per_week=10.0)


def _half_day_snapshots(days: float, completed_at) -> list[Snapshot]:
    """12 時間間隔の snapshot 列。completed_at(経過日数) がその時点の完了累計を返す。"""
    count = int(days * 2) + 1
    return [
        _completed_snapshot(_T0 + timedelta(hours=12 * i), completed_at(i / 2))
        for i in range(count)
    ]


def test_health_worsened_fires_with_half_day_snapshots():
    """回帰: 2 日未満の間隔で snapshot を取っても、ペース急落で発火する。

    旧実装は判定窓を「snapshot の件数」(直近 DECLINE_WINDOW 件) で取っていた。
    12 時間間隔だと 3 件 = 1 日しかなく、health.MIN_SPAN_DAYS (2 日) を満たせず
    ゾーンが unknown になり、何週間データが溜まっても永久に発火しなかった。

    49 日間 (7 週)、前半 4 週は 12 時間に 1 件 (14 件/週)、後半 3 週は 0 件。
    目標 10 件/週に対し、直前 3 期間は green、直近 3 期間は red。
    """
    snaps = _half_day_snapshots(49, lambda day: int(min(day, 28) * 2))
    sig = _by_kind(evaluate(snaps, _GOAL_10, max_interval_days=99, last_review_at=None))[
        "health_worsened"
    ]
    assert sig.fired is True, sig.detail
    assert "green" in sig.detail and "red" in sig.detail


def test_health_worsened_reports_period_count_when_insufficient():
    """完了した期間が 2*DECLINE_WINDOW 未満なら発火せず、期間数入りの理由を返す。

    元の不具合の再現条件 (12 時間間隔 30 件、10 日間 約 14 件/週 → 5 日間 0 件) は
    約 2 週間 = 2 期間しかない。比較には直近 DECLINE_WINDOW 期間とその直前の
    DECLINE_WINDOW 期間が要るため、判定不能ではなく「期間不足」と件数付きで返す。
    """
    snaps = _half_day_snapshots(14.5, lambda day: int(min(day, 10) * 2))
    assert len(snaps) == 30
    sig = _by_kind(evaluate(snaps, _GOAL_10, max_interval_days=99, last_review_at=None))[
        "health_worsened"
    ]
    assert sig.fired is False
    assert "2期間" in sig.detail
    assert f"{2 * DECLINE_WINDOW}期間" in sig.detail


# --- throughput_stalled -----------------------------------------------------


def test_throughput_stalled_fires_when_no_increase_over_window():
    # period_days=7.0(既定)基準で DECLINE_WINDOW+1 個のバケットを作る(週次間隔)。
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=7 * i), 5)
        for i in range(DECLINE_WINDOW + 1)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is True


def test_throughput_stalled_does_not_fire_when_increasing():
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=7 * i), i)
        for i in range(DECLINE_WINDOW + 1)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is False
    assert "完了" in sig.detail


def test_throughput_stalled_insufficient_below_window():
    snaps = [
        _completed_snapshot(_T0 + timedelta(days=7 * i), 5) for i in range(DECLINE_WINDOW)
    ]
    signals = _by_kind(evaluate(snaps, _GOAL, max_interval_days=99, last_review_at=None))
    sig = signals["throughput_stalled"]
    assert sig.fired is False
    assert "不足" in sig.detail


def test_throughput_stalled_short_interval_snapshots_do_not_fire():
    """短時間 (分単位) の連続 snapshot は同一期間バケットに収まり誤発火しない (回帰: I3)。

    以前は snapshots[-DECLINE_WINDOW:] を「件数」で見ていたため、1 分間隔で
    DECLINE_WINDOW 回 snapshot しただけで『停滞』と誤発火していた。
    """
    snaps = [
        _completed_snapshot(_T0 + timedelta(minutes=i), 5) for i in range(DECLINE_WINDOW)
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
        evaluate(
            snaps, _GOAL, max_interval_days=7, last_review_at=last_review_at,
            now=_T0 + timedelta(days=10),
        )
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
        evaluate(
            snaps, _GOAL, max_interval_days=7, last_review_at=last_review_at,
            now=_T0 + timedelta(days=10),
        )
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is False


def test_interval_exceeded_uses_first_snapshot_when_last_review_none():
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=40), 1),
    ]
    signals = _by_kind(
        evaluate(
            snaps, _GOAL, max_interval_days=30, last_review_at=None,
            now=_T0 + timedelta(days=40),
        )
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
        evaluate(
            snaps, _GOAL, max_interval_days=7, last_review_at=naive_last_review,
            now=_T0 + timedelta(days=10),
        )
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is True


def test_interval_exceeded_clamps_negative_elapsed_to_zero():
    """回帰: M2。review 直後の再実行では『-0.0日』ではなく 0.0日と出る。"""
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=10), 1),
    ]
    last_review_at = _T0 + timedelta(days=15)  # 最新 snapshot より後 = review 直後想定
    signals = _by_kind(
        evaluate(
            snaps, _GOAL, max_interval_days=7, last_review_at=last_review_at,
            now=last_review_at,
        )
    )
    sig = signals["interval_exceeded"]
    assert sig.fired is False
    assert sig.detail == "前回レビューから0.0日"


def test_interval_exceeded_uses_wall_clock_not_latest_snapshot():
    """計測が止まったあとでも壁時計で max_interval が発火する。"""
    snaps = [
        _completed_snapshot(_T0, 0),
        _completed_snapshot(_T0 + timedelta(days=1), 1),
    ]
    # 最新 snapshot 基準なら 1 日 < 7 で非発火。壁時計を +10 日にすると発火。
    signals = _by_kind(
        evaluate(
            snaps, _GOAL, max_interval_days=7, last_review_at=_T0,
            now=_T0 + timedelta(days=10),
        )
    )
    assert signals["interval_exceeded"].fired is True



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
    from toc_engine.constraint import ranked_candidates

    snapshots = [
        _snapshot(_T0, _stage_items("backlog", 10) + _stage_items("doing", 4)),
        _snapshot(_T0 + timedelta(days=1), _stage_items("backlog", 10) + _stage_items("doing", 6)),
        _snapshot(_T0 + timedelta(days=2), _stage_items("backlog", 10) + _stage_items("doing", 8)),
    ]
    # レポート (cli) は ranked_candidates で候補一覧を出す
    report_top = ranked_candidates(snapshots)[0].stage_name
    assert report_top == "doing", "前提が崩れている: レポート基準では doing が 1 位のはず"

    moved = _by_kind(evaluate(snapshots, _GOAL, max_interval_days=3.0, last_review_at=None))[
        "constraint_moved"
    ]
    assert report_top in moved.detail, (
        f"レポートの制約 {report_top} が signals の detail '{moved.detail}' に現れない"
        " = ランク基準がズレている"
    )
