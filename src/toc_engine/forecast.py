"""Monte Carlo によるフロー完了予測。単一点予測を出さず、パーセンタイル分布で返す。"""
from __future__ import annotations

import bisect
import logging
import random
from dataclasses import dataclass
from datetime import timedelta

from toc_engine.metrics import throughput_for_source, throughput_total
from toc_engine.model import Snapshot

logger = logging.getLogger(__name__)

PERIOD_DAYS = 7.0  # 「1 期間」の長さ。期間の定義はここと period_throughput だけが持つ
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
    period_days: float = PERIOD_DAYS,
    source: str | None = None,
) -> list[int]:
    """snapshot 履歴から、終わった期間ごとの完了増分を古い順に返す。

    期間の境界 b_k = 最初の snapshot 時刻 + k * period_days (k = 0..K) で累計を取る。
    b_K は最後の snapshot 時刻以下の最大の境界。境界での累計は「その時刻以前で
    最も新しい snapshot の累計」とし、増分 k = max(0, 累計(b_k) - 累計(b_{k-1}))。

    - 終わっていない最後の期間 (b_K より後) は数えない。端数の期間を 1 サンプルに
      すると、数時間分の完了が 1 期間の実績として予測に混ざる
    - 基準点は最初の snapshot 自体 (b_0)。計測開始前から完了していた在庫は
      どの増分にも入らず、最初の期間内の完了は落とさない

    source を渡すとその source の terminal 完了だけを数える（制約フロー限定予測用）。
    """
    if period_days <= 0:
        raise ValueError(f"period_days は正の数が必要です: {period_days!r}")
    if len(snapshots) < 2:
        return []
    ordered = sorted(snapshots, key=lambda s: s.taken_at)
    times = [s.taken_at for s in ordered]
    start = times[0]
    period = timedelta(days=period_days)
    finished_periods = (times[-1] - start) // period

    def _cumulative_at(boundary_index: int) -> int:
        boundary = start + boundary_index * period
        snap = ordered[bisect.bisect_right(times, boundary) - 1]
        if source is None:
            return throughput_total(snap)
        return throughput_for_source(snap, source)

    values = [_cumulative_at(k) for k in range(finished_periods + 1)]
    return [max(0, curr - prev) for prev, curr in zip(values, values[1:])]


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
