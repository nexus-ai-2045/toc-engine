"""metrics.py のテスト。"""
from datetime import datetime, timezone

from toc_engine.metrics import (
    cfd_series,
    stage_metrics,
    throughput_series,
    throughput_total,
)
from toc_engine.model import Snapshot, Stage, WorkItem


def _snap(taken_at=None, items=()):
    stages = (
        Stage("a:inbox", 0, False),
        Stage("a:done", 1, True),
        Stage("t:open", 2, False),
    )
    return Snapshot(
        taken_at=taken_at or datetime(2026, 7, 20, tzinfo=timezone.utc),
        stages=stages,
        items=tuple(items),
    )


def _item(iid, stage, age=None):
    return WorkItem(iid, iid, stage, "src", age)


def test_stage_metrics_wip_and_age():
    snap = _snap(
        items=[
            _item("x1", "a:inbox", 10.0),
            _item("x2", "a:inbox", 2.0),
            _item("x3", "a:done", 1.0),
            _item("x4", "t:open", None),  # age 不明アイテム
        ]
    )
    metrics = {m.stage.name: m for m in stage_metrics(snap)}
    inbox = metrics["a:inbox"]
    assert inbox.wip == 2
    assert inbox.avg_age_days == 6.0
    assert inbox.max_age_days == 10.0
    assert inbox.oldest[0].item_id == "x1"  # age 降順
    open_m = metrics["t:open"]
    assert open_m.wip == 1
    assert open_m.avg_age_days is None  # age 不明のみなら None


def test_throughput_counts_terminal_items():
    snap = _snap(items=[_item("x", "a:done", 1.0), _item("y", "a:inbox", 1.0)])
    assert throughput_total(snap) == 1


def test_throughput_series_and_cfd():
    s1 = _snap(
        taken_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        items=[_item("x", "a:inbox", 1.0)],
    )
    s2 = _snap(
        taken_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        items=[_item("x", "a:done", 3.0), _item("y", "a:inbox", 0.5)],
    )
    series = throughput_series([s1, s2])
    assert [count for _, count in series] == [0, 1]
    cfd = cfd_series([s1, s2])
    assert cfd["a:inbox"] == [1, 1]
    assert cfd["a:done"] == [0, 1]
    assert cfd["t:open"] == [0, 0]


def test_cfd_empty():
    assert cfd_series([]) == {}
