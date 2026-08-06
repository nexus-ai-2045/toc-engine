# toc-engine Phase 2 設計書 — レビュー・ループと事前予測

日付: 2026-08-07
ステータス: 設計確定
前提: Phase 1 (MVP) 完了・受け入れ済み。`2026-07-20-toc-engine-design.md` の Phase 2 節を具体化する。

## 1. 目的

Phase 1 は「計測して制約を出す」までだった。Phase 2 は **Five Focusing Steps を運転ループとして回す** 部分を実装する。

1. **予測**: 現在の制約が今のペースで解消するまでどれくらいか (MPC 的な事前予測)
2. **シグナル**: レビューすべき状態変化をシステム側が検知して招集する
3. **サイクル記録**: どの Step で何を打ったかを記録し、次の計測で効果を検証する

## 2. 事前調査の結論 (2026-08-07 実施)

車輪の再発明チェック (`engineering_brain route` → `reinvention_check`) の証跡。

| 調査対象 | 結果 | 判断 |
|---|---|---|
| Monte Carlo 完了予測の PyPI ライブラリ | 成熟したものは**存在しない** (個人 notebook repo のみ) | stdlib 自前実装 |
| TOC バッファ管理 / フィーバーチャートの Python OSS | **皆無** | 自前一択 |
| workspace 内 `shared/lib/event_ledger.py` (JSONL 差分) | 機能は近い | **流用しない** — 公開予定の本 repo が private workspace lib に依存すると配布時に壊れる |
| workspace 内 `cos_patrol.py` (経過時間しきい値判定) | パターンが近い | **パターンのみ移植**、コード依存はしない |

依存追加はゼロ。`random.choices` + `statistics.quantiles` (どちらも stdlib) で足りる。

### 予測実装に対する運用上の制約 (調査由来・仕組みで強制する)

1. **サンプル不足時は予測しない** — 5 サンプル未満は分布の裾が表現できない。`None` + 理由を返す
2. **単一点予測を出さない** — 平均値ではなくパーセンタイル (50/70/85) で提示する
3. **正規分布を仮定しない** — 実績のブートストラップ復元抽出のみ (throughput は zero-bound かつ右に裾を引く)

## 3. 次元の呪いの回避方針

シグナル・予測は設定項目を増やすほど組み合わせ爆発を起こし、調整不能になる。次を守る。

- **シグナルは固定 4 種のみ**。設定で増やせるようにしない
- **しきい値は module 定数**。`config.local.toml` に露出させるのは既存の `max_interval_days` だけ
- **予測のパーセンタイルは固定** (50/70/85)。選ばせない
- 新しい軸を足したくなったら、まず既存 4 種で足りない実例を出す

## 4. モジュール構成 (追加分)

```
src/toc_engine/
├── health.py     # スループット率と健全性ゾーン (dashboard との重複を解消)
├── forecast.py   # Monte Carlo 完了予測 (stdlib のみ)
├── signals.py    # レビュー招集シグナル 4 種
└── steps.py      # Five Focusing Steps サイクル記録
```

### 4.1 `health.py`

Phase 1 レビューで指摘済みの重複 (`dashboard.py` の `need_badge` 判定が 2 箇所) を解消する。

```python
MIN_SPAN_DAYS = 2.0   # これ未満のスパンではレート外挿しない

@dataclass(frozen=True)
class Health:
    zone: str            # "green" | "yellow" | "red" | "unknown"
    rate_per_week: float | None
    label: str           # 表示用 (日本語)

def throughput_health(throughput: list[tuple[str, int]], target_per_week: float | None) -> Health
```

- `target_per_week is None` → `zone="unknown"`
- サンプル 2 点未満、またはスパン `< MIN_SPAN_DAYS` → `zone="unknown"`, `label="計測期間が短い"`
- `rate >= target` → green / `>= target*0.7` → yellow / それ未満 → red

`dashboard.py` はこのモジュールを使うよう書き換える (ロジック重複を消す)。

### 4.2 `forecast.py`

```python
MIN_SAMPLES = 5          # これ未満は予測しない (分布の裾が表現できない)
DEFAULT_TRIALS = 10_000
PERCENTILES = (50, 70, 85)

@dataclass(frozen=True)
class Forecast:
    percentiles: dict[int, float]   # {50: 12.0, 70: 18.0, 85: 25.0} 単位=期間数
    trials: int
    samples_used: int

def period_throughput(snapshots: list[Snapshot], period_days: float = 7.0) -> list[int]
    """snapshot 履歴から期間ごとの完了増分を出す。負の増分は 0 に丸める。"""

def forecast_periods_to_clear(
    remaining: int,
    samples: list[int],
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> Forecast | None
    """残 remaining 件を消化するのに必要な期間数の分布。
    サンプル不足 (< MIN_SAMPLES) または全サンプルが 0 なら None。
    """
```

- 実装は `random.choices(samples, k=1)` の復元抽出を残数が尽きるまで累積、を `trials` 回
- `seed` はテストの決定性のためだけに使う (本番は None)
- 全サンプルが 0 の場合は無限ループになるため `None` を返す (**必ずガードする**)

### 4.3 `signals.py`

固定 4 種。それぞれ「発火したか」+「根拠」を返す。

```python
DECLINE_WINDOW = 3        # スループット低下判定に使う直近期間数

@dataclass(frozen=True)
class Signal:
    kind: str        # "constraint_moved" | "health_worsened" | "throughput_stalled" | "interval_exceeded"
    fired: bool
    detail: str

def evaluate(
    snapshots: list[Snapshot],
    goal: Goal,
    max_interval_days: float,
    last_review_at: datetime | None,
) -> list[Signal]
```

| kind | 発火条件 |
|---|---|
| `constraint_moved` | 直近 2 snapshot で制約候補 1 位の stage 名が変わった |
| `health_worsened` | `health.throughput_health` のゾーンが前回より悪化 (green→yellow→red) |
| `throughput_stalled` | 直近 `DECLINE_WINDOW` 期間で完了増分が 0 |
| `interval_exceeded` | `last_review_at` から `max_interval_days` 超過 (未レビューなら初回 snapshot から) |

`evaluate` は常に 4 件返す (`fired` の真偽で判別)。呼び出し側が「どれが発火したか」を数える。

### 4.4 `steps.py`

Five Focusing Steps のサイクル記録。エンジンは記録係に徹し、判断はしない。

```python
STEPS = ("identify", "exploit", "subordinate", "elevate", "reevaluate")

@dataclass(frozen=True)
class CycleEntry:
    at: datetime
    step: str
    constraint: str
    action: str

def validate_step(step: str) -> str   # 未知の step は ValueError
```

履歴には `history.py` の JSONL に `type: "cycle"` として追記する (`append_cycle` / `read_history` の拡張)。

## 5. CLI 追加

```
toc review [--config PATH]
  → シグナル評価 + 予測 + 議題 JSON (state_dir/review.json) + Markdown を stdout
    AI が対話レビューを進行するための入力になる

toc cycle --step <step> --action "<打ち手>" [--config PATH]
  → 現在の制約に紐付けて Five Focusing Steps の記録を追加
```

`toc review` は Goal ガード対象 (Goal 未定義なら拒否)。

## 6. レポート / ダッシュボードへの反映

- レポート dict に `forecast` と `signals` を追加
- ダッシュボードに「予測」カード (パーセンタイル 3 点、予測不能なら理由を表示) と「シグナル」カード
- 既存の健全性バッジは `health.py` 経由に置き換え (重複解消)

## 7. テスト戦略

- 全モジュール TDD
- `forecast` は `seed` 固定で決定的にテストする。サンプル不足・全ゼロ・正常系の 3 系統
- `signals` は snapshot 履歴を組み立てたテーブルテストで 4 種それぞれの発火/非発火を検証
- `health` は既存 dashboard テストが通り続けることを回帰として使う
- CLI は `toc review` / `toc cycle` の統合テスト

## 8. 完成条件 (DoD)

| # | 条件 | 検証 |
|---|---|---|
| 1 | 全テスト green (Phase 1 の 54 件を含む) | `pytest -q` 実測ログ |
| 2 | `toc review` がシグナル 4 種と予測を含む議題を出す | 実データ実行 |
| 3 | `toc cycle` で打ち手を記録でき、履歴に残る | 実行 → `read_history` 確認 |
| 4 | ダッシュボードに予測とシグナルが表示される | 実物の目視 |
| 5 | 健全性バッジの重複ロジックが解消 | `dashboard.py` に zone 判定が残っていない |
| 6 | サンプル不足時に単一点予測を出さない | テストで保証 |
| 7 | 個人データがコミットに含まれない | `git ls-files` / `git grep` |
| 8 | closeout の verification が ok | `engineering_brain closeout` |

## 9. 停止線

- push / PR 作成 / GitHub repo 作成 / public 化 は current-turn の明示承認まで実行しない
- 本 repo にはまだ remote が無い。PR を出すには repo 作成が必要 = 承認対象
