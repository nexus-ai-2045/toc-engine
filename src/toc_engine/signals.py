"""レビュー招集シグナル。固定 4 種のみ判定する（設定で増やせない）。

制約理論のレビューを固定周期で回すと形骸化する。代わりに実測が閾値を
超えたときにシステム側が招集する。種別を増やすと組み合わせが爆発するため
種別数はここに固定し、呼び出し側からは増減できない。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from toc_engine.constraint import current_constraint
from toc_engine.forecast import period_throughput
from toc_engine.health import throughput_health
from toc_engine.metrics import throughput_series
from toc_engine.model import Goal, Snapshot

DECLINE_WINDOW = 3  # スループット停滞判定に使う直近 snapshot 数
_MIN_SNAPSHOTS = 2  # 比較に最低限必要な snapshot 数

_ZONE_SEVERITY = {"green": 0, "yellow": 1, "red": 2}  # 悪化判定用の重症度順


@dataclass(frozen=True)
class Signal:
    """レビュー招集シグナル 1 件。"""

    kind: str  # 4 種固定
    fired: bool
    detail: str  # 発火根拠、または非発火理由（日本語）


def evaluate(
    snapshots: list[Snapshot],
    goal: Goal,
    max_interval_days: float,
    last_review_at: datetime | None,
    now: datetime | None = None,
) -> list[Signal]:
    """4 種のシグナルを固定順で判定する。snapshot 不足でも例外を投げず常に4件返す。

    now は interval_exceeded の壁時計。省略時は UTC 現在時刻。テスト注入用。
    """
    clock = now if now is not None else datetime.now(timezone.utc)
    return [
        _constraint_moved(snapshots),
        _health_worsened(snapshots, goal),
        _throughput_stalled(snapshots),
        _interval_exceeded(snapshots, max_interval_days, last_review_at, now=clock),
    ]


def _insufficient(kind: str, count: int) -> Signal:
    """snapshot 不足時に共通で使う非発火 Signal。"""
    return Signal(kind, False, f"snapshot が不足（{count}件）")


def _constraint_moved(snapshots: list[Snapshot]) -> Signal:
    """直近2 snapshot で制約 1 位 stage 名が変わったか判定する。"""
    if len(snapshots) < _MIN_SNAPSHOTS:
        return _insufficient("constraint_moved", len(snapshots))
    prev_top = current_constraint(snapshots[:-1])
    curr_top = current_constraint(snapshots)
    if prev_top is None or curr_top is None:
        return Signal("constraint_moved", False, "制約候補が特定できません")
    if prev_top != curr_top:
        return Signal(
            "constraint_moved", True, f"制約が {prev_top} → {curr_top} に変化"
        )
    return Signal("constraint_moved", False, f"制約は {curr_top} のまま")


def _health_worsened(snapshots: list[Snapshot], goal: Goal) -> Signal:
    """直近 DECLINE_WINDOW 期間のゾーンが、その直前の同幅ウィンドウより悪化したか判定する。

    throughput_health 自体は初回 snapshot からの累計平均のままでよい（バッジ表示は
    それで解釈できる）。しかし累計平均は履歴が伸びるほど直近の変化が薄まり、
    直近でペースが落ちても検知できない。ここでは直近ウィンドウ同士だけを比較する。
    """
    if len(snapshots) < _MIN_SNAPSHOTS:
        return _insufficient("health_worsened", len(snapshots))
    if goal.target_per_week is None:
        return Signal("health_worsened", False, "目標未設定")
    prev_window = snapshots[-DECLINE_WINDOW - 1 : -1]
    curr_window = snapshots[-DECLINE_WINDOW:]
    prev_zone = throughput_health(
        throughput_series(prev_window), goal.target_per_week
    ).zone
    curr_zone = throughput_health(
        throughput_series(curr_window), goal.target_per_week
    ).zone
    if prev_zone not in _ZONE_SEVERITY or curr_zone not in _ZONE_SEVERITY:
        return Signal("health_worsened", False, "ゾーンを判定できません")
    if _ZONE_SEVERITY[curr_zone] > _ZONE_SEVERITY[prev_zone]:
        return Signal(
            "health_worsened", True, f"ゾーンが {prev_zone} → {curr_zone} に悪化"
        )
    return Signal("health_worsened", False, "ゾーン変化なし")


def _throughput_stalled(snapshots: list[Snapshot]) -> Signal:
    """直近 DECLINE_WINDOW 期間で完了増分の合計が 0 か判定する。

    forecast.period_throughput と同じ「期間」の定義を使う。snapshot 件数で数えると
    短時間に何度も snapshot しただけで誤発火するため、週次バケットの増分で見る。
    """
    periods = period_throughput(snapshots)
    if len(periods) < DECLINE_WINDOW:
        return Signal(
            "throughput_stalled", False, f"計測期間が不足（{len(periods)}期間）"
        )
    completed = sum(periods[-DECLINE_WINDOW:])
    if completed <= 0:
        return Signal(
            "throughput_stalled", True, f"直近{DECLINE_WINDOW}期間で完了増分なし"
        )
    return Signal("throughput_stalled", False, f"直近で{completed}件完了")


def _as_aware_utc(dt: datetime) -> datetime:
    """naive datetime は UTC とみなして aware にする。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _interval_exceeded(
    snapshots: list[Snapshot],
    max_interval_days: float,
    last_review_at: datetime | None,
    now: datetime | None = None,
) -> Signal:
    """前回レビューからの経過日数が max_interval_days を超えたか判定する。

    終点は最新 snapshot ではなく壁時計 now。計測が止まっている期間でも
    max_interval_days のフォールバックが発火するようにする。
    """
    if len(snapshots) < _MIN_SNAPSHOTS:
        return _insufficient("interval_exceeded", len(snapshots))
    baseline = last_review_at if last_review_at is not None else snapshots[0].taken_at
    end = now if now is not None else datetime.now(timezone.utc)
    elapsed_days = max(
        0.0,
        (_as_aware_utc(end) - _as_aware_utc(baseline)).total_seconds() / 86400,
    )
    detail = f"前回レビューから{elapsed_days:.1f}日"
    return Signal("interval_exceeded", elapsed_days > max_interval_days, detail)
