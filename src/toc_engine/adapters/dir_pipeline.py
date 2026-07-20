"""ディレクトリをステージとみなすアダプタ。ファイル 1 つ = WorkItem 1 つ。"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from toc_engine.adapters.base import Adapter
from toc_engine.model import Stage, WorkItem

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400.0


class DirPipelineAdapter(Adapter):
    """例: inbox → drafts → ready → published のようなファイル移動フロー。"""

    def __init__(self, name: str, stage_specs: list[dict]) -> None:
        self.name = name
        self._specs = stage_specs

    def stages(self) -> list[Stage]:
        return [
            Stage(name=s["name"], order=i, terminal=bool(s.get("terminal", False)))
            for i, s in enumerate(self._specs)
        ]

    def scan(self) -> list[WorkItem]:
        now = time.time()
        items: list[WorkItem] = []
        for spec in self._specs:
            root = Path(spec["path"])
            if not root.is_dir():
                logger.warning("stage パスが見つからずスキップ: %s", root)
                continue
            for f in sorted(root.iterdir()):
                if f.name.startswith(".") or not f.is_file():
                    continue
                age = max(0.0, (now - f.stat().st_mtime) / _SECONDS_PER_DAY)
                items.append(
                    WorkItem(
                        item_id=f"{self.name}:{spec['name']}:{f.name}",
                        title=f.stem,
                        stage=spec["name"],
                        source=self.name,
                        age_days=age,
                    )
                )
        return items
