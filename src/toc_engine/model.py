"""正規化データモデル。全モジュールの共通語彙。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class GoalNotDefinedError(Exception):
    """Goal 未定義のまま計測しようとした時に送出する。"""


@dataclass(frozen=True)
class Goal:
    """システムの Goal。TOC の出発点。"""

    statement: str
    throughput_unit: str
    inventory: str = ""
    operating_expense: str = ""
    target_per_week: float | None = None


@dataclass(frozen=True)
class Stage:
    """工程。terminal=True は完了置き場（スループットとして数える）。"""

    name: str
    order: int
    terminal: bool = False


@dataclass(frozen=True)
class WorkItem:
    """1 つの作業アイテム。age_days は不明なら None。"""

    item_id: str
    title: str
    stage: str
    source: str
    age_days: float | None = None


@dataclass(frozen=True)
class Snapshot:
    """ある時点の全ソース横断の計測結果。"""

    taken_at: datetime
    stages: tuple[Stage, ...]
    items: tuple[WorkItem, ...]


@dataclass(frozen=True)
class Note:
    """ユーザーの意見・決定の定性記録。"""

    at: datetime
    text: str
    constraint: str | None = None


def _toml_str(value: str) -> str:
    """最小限の TOML 文字列エスケープ（flat な goal schema 専用）。"""
    escaped = (value
        .replace("\\", "\\\\")  # バックスラッシュを最初にエスケープ
        .replace("\n", "\\n")   # 改行をエスケープ
        .replace("\r", "\\r")   # キャリッジリターンをエスケープ
        .replace("\t", "\\t")   # タブをエスケープ
        .replace('"', '\\"'))   # ダブルクォートをエスケープ
    return f'"{escaped}"'


def save_goal(goal: Goal, path: Path) -> None:
    """Goal を goal.toml として保存する。"""
    lines = [
        f"statement = {_toml_str(goal.statement)}",
        f"throughput_unit = {_toml_str(goal.throughput_unit)}",
        f"inventory = {_toml_str(goal.inventory)}",
        f"operating_expense = {_toml_str(goal.operating_expense)}",
    ]
    if goal.target_per_week is not None:
        lines.append(f"target_per_week = {goal.target_per_week}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_goal(path: Path) -> Goal:
    """goal.toml を読む。無ければ GoalNotDefinedError（Goal-first の強制）。"""
    if not path.exists():
        raise GoalNotDefinedError(
            f"Goal が未定義です ({path} がありません)。"
            "先に `toc init` で Goal を定義してください。"
        )
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    target = data.get("target_per_week")
    return Goal(
        statement=data["statement"],
        throughput_unit=data["throughput_unit"],
        inventory=data.get("inventory", ""),
        operating_expense=data.get("operating_expense", ""),
        target_per_week=float(target) if target is not None else None,
    )
