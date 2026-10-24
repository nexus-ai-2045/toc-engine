"""Snapshot からフローメトリクスを計算する。"""
from __future__ import annotations

from dataclasses import dataclass

from toc_engine.model import Snapshot, Stage, WorkItem

_OLDEST_TOP_N = 5


@dataclass(frozen=True)
class StageMetrics:
    """工程 1 つ分の計測値。age 不明アイテムのみの工程は avg/max が None。"""

    stage: Stage
    wip: int
    avg_age_days: float | None
    max_age_days: float | None
    oldest: tuple[WorkItem, ...]


def stage_metrics(snapshot: Snapshot) -> list[StageMetrics]:
    """工程別の WIP・滞留時間を計算する。"""
    result: list[StageMetrics] = []
    for stage in snapshot.stages:
        items = [i for i in snapshot.items if i.stage == stage.name]
        aged = sorted(
            (i for i in items if i.age_days is not None),
            key=lambda i: i.age_days,
            reverse=True,
        )
        ages = [i.age_days for i in aged]
        result.append(
            StageMetrics(
                stage=stage,
                wip=len(items),
                avg_age_days=sum(ages) / len(ages) if ages else None,
                max_age_days=ages[0] if ages else None,
                oldest=tuple(aged[:_OLDEST_TOP_N]),
            )
        )
    return result


def throughput_total(snapshot: Snapshot) -> int:
    """terminal 工程にあるアイテム総数（完了の累計）。"""
    terminal = {s.name for s in snapshot.stages if s.terminal}
    return sum(1 for i in snapshot.items if i.stage in terminal)


def throughput_for_source(snapshot: Snapshot, source: str) -> int:
    """指定 source の terminal 工程にあるアイテム総数。

    複数ソース構成で制約フローだけの完了累計を取るときに使う。
    """
    terminal = {s.name for s in snapshot.stages if s.terminal}
    return sum(
        1
        for i in snapshot.items
        if i.source == source and i.stage in terminal
    )


def throughput_series(snapshots: list[Snapshot]) -> list[tuple[str, int]]:
    """(ISO 日時, 完了累計) の時系列。ダッシュボードのスパークライン用。"""
    return [(s.taken_at.isoformat(), throughput_total(s)) for s in snapshots]


def cfd_series(snapshots: list[Snapshot]) -> dict[str, list[int]]:
    """CFD 用: stage 名 → snapshot ごとの件数列。WIP 履歴としても使う。"""
    if not snapshots:
        return {}
    names = [st.name for st in snapshots[-1].stages]
    series: dict[str, list[int]] = {n: [] for n in names}
    for snap in snapshots:
        counts: dict[str, int] = {}
        for i in snap.items:
            counts[i.stage] = counts.get(i.stage, 0) + 1
        for n in names:
            series[n].append(counts.get(n, 0))
    return series
