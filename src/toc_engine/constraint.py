"""制約候補のランク付けヒューリスティクス。"""
from __future__ import annotations

from dataclasses import dataclass

from toc_engine.metrics import StageMetrics

_AGE_WEIGHT_DAYS = 7.0   # 滞留 1 週間ごとに重み +1
_GROWTH_FACTOR = 1.5     # WIP 増加傾向の重み


@dataclass(frozen=True)
class ConstraintCandidate:
    """制約候補。score 降順で並べて使う。"""

    stage_name: str
    score: float
    evidence: tuple[str, ...]


def rank(
    metrics: list[StageMetrics],
    wip_history: dict[str, list[int]] | None = None,
) -> list[ConstraintCandidate]:
    """非 terminal 工程を WIP × 滞留 × 成長でスコア化し降順に返す。

    鎖の最も弱い輪を探す: WIP が積み上がり・滞留が長く・増え続けている工程が
    システムの出力を制限している可能性が高い。
    """
    candidates: list[ConstraintCandidate] = []
    for m in metrics:
        if m.stage.terminal or m.wip == 0:
            continue  # 完了置き場と空工程は制約ではない
        evidence = [f"WIP {m.wip} 件"]
        age_factor = 1.0
        if m.avg_age_days is not None:
            age_factor += m.avg_age_days / _AGE_WEIGHT_DAYS
            evidence.append(f"平均滞留 {m.avg_age_days:.1f} 日")
        growth_factor = 1.0
        hist = (wip_history or {}).get(m.stage.name, [])
        if len(hist) >= 2 and hist[-1] > hist[0]:
            growth_factor = _GROWTH_FACTOR
            evidence.append(f"WIP 増加傾向 ({hist[0]} → {hist[-1]})")
        score = round(m.wip * age_factor * growth_factor, 2)
        candidates.append(
            ConstraintCandidate(m.stage.name, score, tuple(evidence))
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)
