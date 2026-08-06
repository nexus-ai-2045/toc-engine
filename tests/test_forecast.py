"""forecast.py のテスト。"""
from datetime import datetime, timezone

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
    assert result == [2, 3, 4]


def test_period_throughput_single_snapshot_returns_empty():
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 2)
    assert period_throughput([s1]) == []


def test_period_throughput_negative_increment_clamped_to_zero():
    s1 = _snap(datetime(2026, 1, 1, tzinfo=timezone.utc), 5)
    s2 = _snap(datetime(2026, 1, 8, tzinfo=timezone.utc), 3)  # 台帳から項目が消えた想定
    result = period_throughput([s1, s2], period_days=7.0)
    assert result == [5, 0]


def test_forecast_none_when_samples_below_min():
    samples = [1, 2, 3, 4]
    assert len(samples) < MIN_SAMPLES
    assert forecast_periods_to_clear(10, samples, trials=200) is None


def test_forecast_none_when_all_samples_zero():
    samples = [0, 0, 0, 0, 0]
    result = forecast_periods_to_clear(10, samples, trials=200)
    assert result is None


def test_forecast_none_when_remaining_zero_or_negative():
    samples = [2, 3, 2, 3, 2]
    assert forecast_periods_to_clear(0, samples, trials=200) is None
    assert forecast_periods_to_clear(-1, samples, trials=200) is None


def test_forecast_is_deterministic_with_seed():
    samples = [2, 3, 2, 3, 2, 4, 1]
    f1 = forecast_periods_to_clear(10, samples, trials=200, seed=42)
    f2 = forecast_periods_to_clear(10, samples, trials=200, seed=42)
    assert f1 == f2
    assert isinstance(f1, Forecast)


def test_forecast_percentiles_are_monotonic_non_decreasing():
    samples = [2, 3, 2, 3, 2, 4, 1, 5]
    result = forecast_periods_to_clear(20, samples, trials=200, seed=1)
    assert result is not None
    p50, p70, p85 = result.percentiles[50], result.percentiles[70], result.percentiles[85]
    assert p50 <= p70 <= p85


def test_forecast_reasonable_range_for_typical_case():
    samples = [2, 3, 2, 3, 2]
    result = forecast_periods_to_clear(10, samples, trials=500, seed=7)
    assert result is not None
    assert 3 <= result.percentiles[50] <= 7
    assert result.trials == 500
    assert result.samples_used == 5
