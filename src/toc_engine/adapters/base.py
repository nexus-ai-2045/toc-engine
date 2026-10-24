"""Adapter インターフェースと snapshot 組み立て。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from toc_engine.model import Snapshot, Stage, WorkItem


class Adapter(ABC):
    """データソース走査の共通インターフェース。"""

    name: str

    @abstractmethod
    def stages(self) -> list[Stage]:
        """このソースの工程一覧（アダプタ内ローカル名）。"""

    @abstractmethod
    def scan(self) -> list[WorkItem]:
        """現時点のアイテム一覧（stage はローカル名）。"""


def take_snapshot(adapters: list[Adapter]) -> Snapshot:
    """全アダプタを走査し、stage 名を 'アダプタ名:stage名' に修飾して統合する。"""
    stages: list[Stage] = []
    items: list[WorkItem] = []
    order = 0
    for adapter in adapters:
        for st in adapter.stages():
            stages.append(Stage(f"{adapter.name}:{st.name}", order, st.terminal))
            order += 1
        for it in adapter.scan():
            items.append(
                WorkItem(
                    item_id=it.item_id,
                    title=it.title,
                    stage=f"{adapter.name}:{it.stage}",
                    source=it.source,
                    age_days=it.age_days,
                )
            )
    return Snapshot(
        taken_at=datetime.now(timezone.utc), stages=tuple(stages), items=tuple(items)
    )
