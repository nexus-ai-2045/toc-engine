"""スループット健全性ゾーン判定。dashboard.py 等から共通利用する SSOT。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

MIN_SPAN_DAYS = 2.0  # これ未満のスパンではレート外挿しない


@dataclass(frozen=True)
class Health:
    """健全性判定の結果。"""

    zone: str  # "green" | "yellow" | "red" | "unknown"
    rate_per_week: float | None
    label: str  # 表示用の日本語
    target_set: bool = True  # 目標未設定の時だけ False。バッジ表示可否の判定に使う


def throughput_health(
    throughput: list[tuple[str, float]],
    target_per_week: float | None,
) -> Health:
    """スループット時系列と週次目標から健全性ゾーンを判定する。"""
    if target_per_week is None:
        return Health("unknown", None, "目標未設定", target_set=False)
    if len(throughput) < 2:
        return Health("unknown", None, "データ不足")

    try:
        t0 = datetime.fromisoformat(throughput[0][0])
        t1 = datetime.fromisoformat(throughput[-1][0])
    except (ValueError, TypeError) as e:
        # 黙殺しない: 運用者がどの入力で壊れたかログから追えるようにする
        logger.warning(
            "健全性判定の日時を解析できずスキップ: %r / %r (%s)",
            throughput[0][0],
            throughput[-1][0],
            e,
        )
        return Health("unknown", None, "日時を解析できません")

    span_days = (t1 - t0).total_seconds() / 86400
    if span_days < MIN_SPAN_DAYS:
        return Health("unknown", None, "計測期間が短い")

    weeks = span_days / 7
    rate = (throughput[-1][1] - throughput[0][1]) / weeks
    if rate >= target_per_week:
        return Health("green", rate, "順調")
    if rate >= target_per_week * 0.7:
        return Health("yellow", rate, "注意")
    return Health("red", rate, "危険")
