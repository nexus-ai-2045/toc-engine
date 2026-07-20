"""if-then 推奨ルール。提案のみで自動実行はしない（判断は人間）。"""
from __future__ import annotations

from dataclasses import dataclass

from toc_engine.constraint import ConstraintCandidate
from toc_engine.metrics import StageMetrics

EXPLOIT_AGE_DAYS = 14.0  # これ以上滞留したら Exploit を疑う
_GROWTH_WINDOW = 3       # WIP 増加判定に使う直近 snapshot 数


@dataclass(frozen=True)
class Recommendation:
    """TOC の打ち手候補。step: exploit / subordinate / identify"""

    step: str
    text: str
    evidence: tuple[str, ...]


def recommend(
    candidates: list[ConstraintCandidate],
    metrics: list[StageMetrics],
    wip_history: dict[str, list[int]] | None = None,
) -> list[Recommendation]:
    """制約候補トップに対する打ち手を if-then ルールで提案する。"""
    if not candidates:
        return [
            Recommendation(
                "identify",
                "制約候補が見つかりません。データソース設定を確認してください。",
                (),
            )
        ]
    top = candidates[0]
    by_name = {m.stage.name: m for m in metrics}
    m = by_name[top.stage_name]
    recs: list[Recommendation] = []

    # if: 制約の WIP が増え続けている → then: Subordinate（上流を絞る）
    hist = (wip_history or {}).get(top.stage_name, [])
    if len(hist) >= _GROWTH_WINDOW and hist[-1] > hist[-_GROWTH_WINDOW]:
        recs.append(
            Recommendation(
                "subordinate",
                f"制約 '{top.stage_name}' の WIP が増え続けています。"
                "上流の投入を制約の処理ペースに絞ってください (Subordinate)。",
                (f"WIP 推移: {hist[-_GROWTH_WINDOW:]}",),
            )
        )

    # if: 閾値を超えて滞留するアイテムがある → then: Exploit（制約の稼働を守る）
    if m.max_age_days is not None and m.max_age_days >= EXPLOIT_AGE_DAYS:
        oldest = m.oldest[0]
        recs.append(
            Recommendation(
                "exploit",
                f"制約 '{top.stage_name}' に {m.max_age_days:.0f} 日滞留している"
                "アイテムがあります。制約の稼働を守り、最古のアイテムから流してください"
                " (Exploit)。",
                (f"最古: {oldest.title} ({m.max_age_days:.0f} 日)",),
            )
        )

    # ルールが 1 つも発火しない → Identify（まず観察）
    if not recs:
        recs.append(
            Recommendation(
                "identify",
                f"現在の制約候補は '{top.stage_name}' です。"
                "まずこの工程の観察から始めてください (Identify)。",
                top.evidence,
            )
        )
    return recs
