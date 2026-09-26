"""Monte Carlo によるフロー完了予測。単一点予測を出さず、パーセンタイル分布で返す。"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import timedelta

from toc_engine.metrics import throughput_for_source, throughput_total
from toc_engine.model import Snapshot

logger = logging.getLogger(__name__)

MIN_SAMPLES = 5
DEFAULT_TRIALS = 10_000
PERCENTILES = (50, 70, 85)
_MAX_PERIODS = 1000  # 1 試行あたりの反復上限（無限ループ防止）


@dataclass(frozen=True)
class Forecast:
    """完了までの期間数分布。percentiles は単位=期間数。"""

    percentiles: dict[int, float]
    trials: int
    samples_used: int


def period_throughput(
    snapshots: list[Snapshot],
    period_days: float = 7.0,
    source: str | None = None,
) -> list[int]:
    """snapshot 履歴を period_days ごとのバケットに割り、各期間の完了増分を返す。

    source を渡すとその source の terminal 完了だけを数える（制約フロー限定予測用）。
    """
    if len(snapshots) < 2:
        return []
    ordered = sorted(snapshots, key=lambda s: s.taken_at)
    start = ordered[0].taken_at
    period = timedelta(days=period_days)

    def _cumulative(snap: Snapshot) -> int:
        if source is None:
            return throughput_total(snap)
        return throughput_for_source(snap, source)

    # バケット index → バケット末時点の累計完了数（同一バケット内は最後の値で上書き）
    bucket_cumulative: dict[int, int] = {}
    for snap in ordered:
        idx = int((snap.taken_at - start) / period)
        bucket_cumulative[idx] = _cumulative(snap)

    max_idx = max(bucket_cumulative)
    # バケット 0 は「基準点」であって増分ではない。ここを増分扱いすると、
    # 初回 snapshot 以前に完了済みだった在庫が偽の実績として samples に混入する。
    increments: list[int] = []
    prev_cumulative = bucket_cumulative[0]
    for idx in range(1, max_idx + 1):
        cumulative = bucket_cumulative.get(idx, prev_cumulative)
        increments.append(max(0, cumulative - prev_cumulative))
        prev_cumulative = cumulative
    return increments


def _percentile(sorted_values: list[int], p: int) -> float:
    """最近傍順位法でパーセンタイルを取り出す（sorted_values は昇順ソート済み前提）。"""
    n = len(sorted_values)
    idx = -(-(p * n) // 100) - 1  # ceil(p * n / 100) - 1 を整数演算のみで計算
    idx = max(0, min(n - 1, idx))
    return float(sorted_values[idx])


def forecast_periods_to_clear(
    remaining: int,
    samples: list[int],
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> tuple[Forecast | None, str | None]:
    """残 remaining 件の消化に必要な期間数の分布を返す。

    予測不能なら (None, 理由) を返す。理由文字列はここが SSOT で、
    呼び出し側 (cli 等) は推測し直さずそのまま表示する。
    """
    if remaining <= 0:
        return None, "残件がありません"
    if trials <= 0:
        return None, "試行回数が不正です"
    if len(samples) < MIN_SAMPLES:
        return None, f"計測期間が不足しています（{len(samples)}期間、必要 {MIN_SAMPLES}期間以上）"
    if all(s <= 0 for s in samples):
        return None, "計測期間内に完了実績がありません"

    rng = random.Random(seed)
    results: list[int] = []
    for _ in range(trials):
        total = 0
        periods = 0
        while total < remaining and periods < _MAX_PERIODS:
            total += rng.choices(samples, k=1)[0]
            periods += 1
        results.append(periods)

    results.sort()
    percentiles = {p: _percentile(results, p) for p in PERCENTILES}
    if max(percentiles.values()) >= _MAX_PERIODS:
        # 上限に張り付いた値は「予測できた」ではなく打ち切りの副産物。
        # それらしい数字を黙って返すより予測不能として扱う。
        logger.warning(
            "予測が上限 %d 期間に飽和したため予測不能として扱います (残 %d 件)",
            _MAX_PERIODS,
            remaining,
        )
        return None, f"現在のペースでは {_MAX_PERIODS} 期間以内に解消しません"
    return Forecast(percentiles=percentiles, trials=trials, samples_used=len(samples)), None
