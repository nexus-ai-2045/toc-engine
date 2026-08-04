"""config.local.toml の読込とアダプタ構築。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from toc_engine.adapters.base import Adapter
from toc_engine.adapters.dir_pipeline import DirPipelineAdapter
from toc_engine.adapters.json_ledger import JsonLedgerAdapter
from toc_engine.adapters.md_tasks import MdTasksAdapter


@dataclass(frozen=True)
class Config:
    """実行設定。state_dir に goal.toml / history.jsonl / 出力物を置く。"""

    state_dir: Path
    sources: tuple[dict, ...]
    max_interval_days: float = 3.0


def load_config(path: Path) -> Config:
    """config.local.toml を読む。構文エラーは tomllib が明確に報告する。"""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    core = data.get("core", {})
    state_dir = (path.parent / core.get("state_dir", ".toc")).resolve()
    return Config(
        state_dir=state_dir,
        sources=tuple(data.get("source", [])),
        max_interval_days=float(core.get("max_interval_days", 3.0)),
    )


def build_adapters(config: Config, base: Path) -> list[Adapter]:
    """設定からアダプタ群を構築する。相対パスは base 起点で解決。"""
    adapters: list[Adapter] = []
    for src in config.sources:
        kind = src.get("type")
        if kind == "dir_pipeline":
            specs = [
                {
                    "name": s["name"],
                    "path": str(base / s["path"]),
                    "terminal": bool(s.get("terminal", False)),
                }
                for s in src["stages"]
            ]
            adapters.append(DirPipelineAdapter(src["name"], specs))
        elif kind == "md_tasks":
            adapters.append(MdTasksAdapter(src["name"], str(base / src["path"])))
        elif kind == "json_ledger":
            adapters.append(
                JsonLedgerAdapter(
                    src["name"],
                    str(base / src["path"]),
                    stage=src.get("stage", "done"),
                    records_key=src.get("records_key", ""),
                    id_field=src.get("id_field", "id"),
                    title_field=src.get("title_field", "title"),
                    timestamp_field=src.get("timestamp_field", "published_at"),
                )
            )
        else:
            raise ValueError(f"未知の source type: {kind}")
    return adapters
