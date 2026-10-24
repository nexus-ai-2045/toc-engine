"""forecast.py のテスト。"""
from datetime import datetime, timedelta, timezone

from toc_engine.forecast import (
    MIN_SAMPLES,
    Forecast,
    forecast_periods_to_clear,
    period_throughput,
)
from toc_engine.model import Snapshot, Stage, WorkItem

_STAGES = (
    Stage("a:inbox", 0, False),
    Stage("a:done", 1, True),
)


def _snap(taken_at, done_count):
    """terminal stage に done_count 件のアイテムが積まれた snapshot を作る。"""
    items = tuple(WorkItem(f"d{i}", f"d{i}", "a:done", "src") for i in range(done_count))
    return Snapshot(taken_at=taken_at, stages=_STAGES, items=items)


def test_period_throughput_returns_increments_across_buckets():
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 2)
    s2 = _snap(datetime(2026, 1, 8, tzinfo=timezone.utc), 5)
    s3 = _snap(datetime(2026, 1, 15, tzinfo=timezone.utc), 9)
    result = period_throughput([s1, s2, s3], period_days=7.0)
    assert result == [3, 4]


def test_period_throughput_single_snapshot_returns_empty():
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 2)
    assert period_throughput([s1]) == []


def test_period_throughput_negative_increment_clamped_to_zero():
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 5)
    s2 = _snap(datetime(2026, 1, 8, tzinfo=timezone.utc), 3)  # 台帳から項目が消えた想定
    result = period_throughput([s1, s2], period_days=7.0)
    assert result == [0]


def test_period_throughput_excludes_completed_inventory_before_first_snapshot():
    """初回 snapshot 時点で既に完了していた在庫は増分に混入しない (回帰: C1)。

    初回 snapshot に完了 120 件が積まれていても、それは計測開始前の実績であり
    samples に現れてはいけない。以降の +2 / +3 だけが期間ごとの実績になる。
    """
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 120)
    s2 = _snap(datetime(2026, 1, 8, tzinfo=timezone.utc), 122)
    s3 = _snap(datetime(2026, 1, 15, tzinfo=timezone.utc), 125)
    result = period_throughput([s1, s2, s3], period_days=7.0)
    assert result == [2, 3]
    assert 120 not in result


def _snaps_at(days_and_counts):
    """(経過日数, 完了累計) の列から snapshot 列を作る。"""
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [_snap(t0 + timedelta(days=d), c) for d, c in days_and_counts]


def test_period_throughput_does_not_count_unfinished_last_period():
    """回帰: 始まったばかりの最後の期間を 1 期間として数えない。

    10 件/週の一定ペースを 0, 6.9, 13.9, 20.9, 27.9, 34.9, 35.05 日に計測する。
    旧実装は [10, 10, 10, 10, 1] を返した。末尾の 1 は 35 日目から 0.15 日分の
    端数で、これが 5 件目のサンプルになり MIN_SAMPLES=5 を通過させていた。

    新実装は「期間の境界 (0, 7, 14, ..., 35 日) で値を取る」。35.05 日時点で
    終わっている期間は 0-7, 7-14, 14-21, 21-28, 28-35 の 5 つ。各境界の値は
    その時刻以前で最も新しい snapshot の累計なので、7 日境界の値は 6.9 日時点の 9、
    35 日境界の値は 34.9 日時点の 49 になる。端数の 35.05 日の値 (50) は、まだ
    終わっていない 35-42 日の期間に属するため、どの増分にも入らない。
    """
    snaps = _snaps_at(
        [(0, 0), (6.9, 9), (13.9, 19), (20.9, 29), (27.9, 39), (34.9, 49), (35.05, 50)]
    )
    result = period_throughput(snaps, period_days=7.0)
    assert result == [9, 10, 10, 10, 10]
    assert 1 not in result  # 0.15 日分の端数がサンプルとして混入しない


def test_period_throughput_counts_first_period_completions():
    """回帰: 最初の期間に完了した分を落とさない。

    累計 100 / 110 / 115 / 120 を 0 / 6 / 13 / 20 日に計測する。旧実装は最初の
    期間の基準点に「最初の期間の最後の snapshot (6 日目の 110)」を使ったため、
    最初の週の +10 が落ちて [5, 5] になっていた。正しくは 0 日目の 100 を基準に
    7 日境界の値 110 (6 日目時点) との差 10 を数える。計測開始時点で既に完了して
    いた 100 件は、どの増分にも入らない (C1 の回帰も同時に守る)。
    """
    snaps = _snaps_at([(0, 100), (6, 110), (13, 115), (20, 120)])
    result = period_throughput(snaps, period_days=7.0)
    assert result == [10, 5]
    assert 100 not in result


def test_period_throughput_shorter_than_one_period_returns_empty():
    """1 期間に満たない計測では、終わった期間が無いので増分も無い。"""
    snaps = _snaps_at([(0, 0), (3, 4), (6.9, 9)])
    assert period_throughput(snaps, period_days=7.0) == []


def test_forecast_none_when_samples_below_min():
    samples = [1, 2, 3, 4]
    assert len(samples) < MIN_SAMPLES
    forecast, reason = forecast_periods_to_clear(10, samples, trials=200)
    assert forecast is None
    assert "計測期間が不足しています" in reason


def test_forecast_none_when_all_samples_zero():
    samples = [0, 0, 0, 0, 0]
    forecast, reason = forecast_periods_to_clear(10, samples, trials=200)
    assert forecast is None
    assert reason == "計測期間内に完了実績がありません"


def test_forecast_none_when_remaining_zero_or_negative():
    samples = [2, 3, 2, 3, 2]
    forecast0, reason0 = forecast_periods_to_clear(0, samples, trials=200)
    forecast_neg, reason_neg = forecast_periods_to_clear(-1, samples, trials=200)
    assert forecast0 is None and reason0 == "残件がありません"
    assert forecast_neg is None and reason_neg == "残件がありません"


def test_forecast_none_when_trials_invalid():
    forecast, reason = forecast_periods_to_clear(
        10, [2, 3, 2, 3, 2], trials=0, seed=1
    )
    assert forecast is None
    assert reason == "試行回数が不正です"


def test_forecast_is_deterministic_with_seed():
    samples = [2, 3, 2, 3, 2, 4, 1]
    f1, r1 = forecast_periods_to_clear(10, samples, trials=200, seed=42)
    f2, r2 = forecast_periods_to_clear(10, samples, trials=200, seed=42)
    assert f1 == f2
    assert r1 is None and r2 is None
    assert isinstance(f1, Forecast)


def test_forecast_percentiles_are_monotonic_non_decreasing():
    samples = [2, 3, 2, 3, 2, 4, 1, 5]
    result, reason = forecast_periods_to_clear(20, samples, trials=200, seed=1)
    assert result is not None
    assert reason is None
    p50, p70, p85 = result.percentiles[50], result.percentiles[70], result.percentiles[85]
    assert p50 <= p70 <= p85


def test_forecast_reasonable_range_for_typical_case():
    samples = [2, 3, 2, 3, 2]
    result, reason = forecast_periods_to_clear(10, samples, trials=500, seed=7)
    assert result is not None
    assert reason is None
    assert 3 <= result.percentiles[50] <= 7
    assert result.trials == 500
    assert result.samples_used == 5


def test_trials_zero_returns_none():
    """trials<=0 は IndexError ではなく None (公開 API の頑健性)。"""
    forecast, reason = forecast_periods_to_clear(10, [2, 3, 2, 3, 2], trials=0, seed=1)
    assert forecast is None
    assert reason is not None


def test_saturated_forecast_returns_none_with_reason(caplog):
    """上限に張り付いた予測は、それらしい数字を返さず予測不能として扱う。"""
    import logging

    with caplog.at_level(logging.WARNING):
        result, reason = forecast_periods_to_clear(
            10_000_000, [1, 1, 1, 1, 1], trials=20, seed=1
        )
    assert result is None
    assert "飽和" in caplog.text
    assert "期間以内に解消しません" in reason


def test_period_throughput_scopes_to_source():
    """他ソースの完了増分は制約フローの samples に混ぜない。"""
    stages = (
        Stage("a:inbox", 0, False),
        Stage("a:done", 1, True),
        Stage("b:inbox", 2, False),
        Stage("b:done", 3, True),
    )

    def snap(day, a_done, b_done):
        items = tuple(
            [WorkItem(f"a{i}", f"a{i}", "a:done", "a") for i in range(a_done)]
            + [WorkItem(f"b{i}", f"b{i}", "b:done", "b") for i in range(b_done)]
        )
        return Snapshot(
            taken_at=datetime(2026, 1, 1 + day, tzinfo=timezone.utc),
            stages=stages,
            items=items,
        )

    s1 = snap(0, 2, 10)
    s2 = snap(7, 5, 40)  # a +3, b +30
    s3 = snap(14, 9, 90)  # a +4, b +50
    assert period_throughput([s1, s2, s3], period_days=7.0, source="a") == [3, 4]
    assert period_throughput([s1, s2, s3], period_days=7.0) == [33, 54]
