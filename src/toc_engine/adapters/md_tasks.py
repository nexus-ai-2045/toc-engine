"""Markdown チェックボックスをタスクとみなすアダプタ。"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from toc_engine.adapters.base import Adapter
from toc_engine.model import Stage, WorkItem

logger = logging.getLogger(__name__)

_CHECKBOX = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*\S)\s*$")
_TITLE_MAX = 80


class MdTasksAdapter(Adapter):
    """todo.md 等のチェックボックス行を open / done の 2 工程として読む。"""

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self._path = Path(path)

    def stages(self) -> list[Stage]:
        return [Stage("open", 0, terminal=False), Stage("done", 1, terminal=True)]

    def scan(self) -> list[WorkItem]:
        if not self._path.is_file():
            logger.warning("タスクファイルが見つからずスキップ: %s", self._path)
            return []
        items: list[WorkItem] = []
        text = self._path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            m = _CHECKBOX.match(line)
            if not m:
                continue
            stage = "done" if m.group(1).lower() == "x" else "open"
            items.append(
                WorkItem(
                    item_id=f"{self.name}:{lineno}",
                    title=m.group(2)[:_TITLE_MAX],
                    stage=stage,
                    source=self.name,
                    age_days=None,
                )
            )
        return items
