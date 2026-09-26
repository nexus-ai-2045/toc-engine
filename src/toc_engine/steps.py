"""Five Focusing Steps のサイクル記録。エンジンは記録係に徹し、判断はしない（判断は人間）。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STEPS = ("identify", "exploit", "subordinate", "elevate", "reevaluate")


@dataclass(frozen=True)
class CycleEntry:
    """Five Focusing Steps の 1 サイクル分の記録。"""

    at: datetime
    step: str  # STEPS のいずれか
    constraint: str  # 記録時点の制約 stage 名（不明なら ""）
    action: str  # 打ち手の記述


def validate_step(step: str) -> str:
    """STEPS に含まれるか検証して正規化（小文字化）した値を返す。未知なら ValueError。"""
    normalized = step.lower()
    if normalized not in STEPS:
        valid = ", ".join(STEPS)
        raise ValueError(
            f"未知の step です: {step!r}。有効な値: {valid}"
        )
    return normalized
