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
def zone_for_rate(rate_per_week: float, target_per_week: float) -> str
```

- `target_per_week is None` → `zone="unknown"`
- サンプル 2 点未満、またはスパン `< MIN_SPAN_DAYS` → `zone="unknown"`, `label="計測期間が短い"`
- `rate >= target` → green / `>= target*0.7` → yellow / それ未満 → red
- この閾値は `zone_for_rate` だけが持つ。バッジ (`throughput_health`) と悪化シグナル (`signals`) は同じ関数を使う

`dashboard.py` はこのモジュールを使うよう書き換える (ロジック重複を消す)。

### 4.2 `forecast.py`

```python
PERIOD_DAYS = 7.0        # 1 期間の長さ。「期間」の定義はこの定数と period_throughput だけが持つ
MIN_SAMPLES = 5          # これ未満は予測しない (分布の裾が表現できない)
DEFAULT_TRIALS = 10_000
PERCENTILES = (50, 70, 85)

@dataclass(frozen=True)
class Forecast:
    percentiles: dict[int, float]   # {50: 12.0, 70: 18.0, 85: 25.0} 単位=期間数
    trials: int
    samples_used: int

def period_throughput(snapshots: list[Snapshot], period_days: float = PERIOD_DAYS) -> list[int]
    """snapshot 履歴から、終わった期間ごとの完了増分を出す。負の増分は 0 に丸める。

    境界 b_k = 最初の snapshot 時刻 + k * period_days で、その時刻以前で最も新しい
    snapshot の累計を取り、隣り合う境界の差を増分とする (詳細は 10.6)。
    最初の snapshot 自体が基準点なので、初回計測より前に完了していた在庫は混入しない。
    終わっていない最後の期間は数えない。
    """

def forecast_periods_to_clear(
    remaining: int,
    samples: list[int],
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> tuple[Forecast | None, str | None]   # (予測結果, 予測不能の理由)
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
| `health_worsened` | 直近 `DECLINE_WINDOW` 期間の完了ペースのゾーン (`health.zone_for_rate`) が、その直前の `DECLINE_WINDOW` 期間より悪化 (green→yellow→red)。完了した期間が `2*DECLINE_WINDOW` 未満なら発火せず期間数を返す |
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

## 10. 実装中に見つかった不具合 (再発防止のため記録)

いずれも回帰テストを付け、旧実装で落ちることを確認済み。

### 10.1 予測に計測開始前の在庫が混入していた (Critical)

`period_throughput` が最初のバケットを増分として数えていたため、計測を始める前から完了していた
在庫が 1 期間分の実績になっていた。既に 120 件完了済みの状態で計測を始めると
`samples = [120, 2, 3, 2, 3, 2]` となり、残 60 件の p85 が 26 → 11 と楽観側にズレる。

厄介なのは 3 つのガード (サンプル数・全ゼロ・残 0) をすべて通過するため、
「予測不能」にならず自信のある数字として出てしまう点。保守側であるはずの p85 が
最も大きくズレるので、安全を見たつもりの判断が一番外れる。

対策: 最初のバケットは基準点として扱い、増分は 2 番目以降から取る。

### 10.2 同じ概念を 2 箇所で計算するとズレる (同型のバグが 3 回)

| 発生箇所 | 症状 |
|---|---|
| 成長判定 | `constraint` は初回比較・`recommend` は直近ウィンドウ比較で、evidence と打ち手が食い違う |
| 制約の算出 | 同じ式が 4 箇所にコピーされ、1 枚が成長重みの引数を落として順位がズレた |
| バッジ表示 | バッジ描画条件と CSS 同梱条件が別変数を見て、スタイルの当たらないバッジが出た |

対策として「条件を揃える」ではなく **分岐できない構造にする** を選んだ。
- 成長判定 → `constraint.wip_growth()` を共有
- 制約の算出 → 上位 1 件は `constraint.current_constraint()`、候補一覧は `constraint.ranked_candidates()` を唯一の入口にする (cli からの `rank` 直接呼び出しも撤去し、テストで再混入を検出する)
- バッジ → 生成関数の戻り値が空かどうかで CSS 同梱を導出する (条件が 1 つしかない)

### 10.3 予測不能の理由を呼び出し側が推測し直していた

`forecast` が `None` を返す理由は 5 通りあるのに、CLI が外から状況を見て理由を組み立てていた。
飽和 (現在のペースでは終わらない) のケースで「ばらつきが大きい可能性」という事実と違う説明が出ていた。
理由の SSOT を `forecast` 側に置き、呼び出し側はそのまま表示する。

### 10.4 「期間」の定義が 2 つあった

`throughput_stalled` が snapshot の件数で判定していたため、短時間に連続実行しただけで誤発火した。
`forecast.period_throughput` に正しい期間バケット化が既にあったので、そちらに寄せた。
招集シグナルは誤発火した時点で価値がゼロになる。

### 10.5 健全性悪化シグナルが、短い間隔の snapshot では永久に発火しなかった

**何が起きたか**: `health_worsened` は判定窓を「直近 `DECLINE_WINDOW` 件の snapshot」で取っていた。
10.4 で `throughput_stalled` を期間数に直した時に、同じ定数 `DECLINE_WINDOW` を使う
`health_worsened` だけが件数のまま残り、1 つの定数が「件数」と「期間数」の 2 つの単位を持っていた。
12 時間間隔で snapshot を取ると窓 3 件は 1 日分しかなく、`health.MIN_SPAN_DAYS` (2 日) を満たせない。
ゾーンが `unknown` になり、何週間データが溜まっても発火しなかった
(再現: 12 時間間隔 30 件、10 日間 約 14 件/週 → 5 日間 0 件、目標 10 件/週で `fired=False`「ゾーンを判定できません」)。

**なぜ既存のガードを通過したか**: 既存テストはすべて週次間隔の snapshot で書かれていた。
週次なら「snapshot 1 件 ≒ 1 期間」なので、件数で数えても期間で数えても結果が一致する。
また `MIN_SPAN_DAYS` のガード自体は正しく働いており (短いスパンでレートを外挿しない)、
その結果が「判定できない = 発火しない」として静かに返っていた。例外もログも出ないため、
「悪化していない」と「判定できていない」が外から区別できなかった。

**どう直したか**: 期間の定義を `forecast.period_throughput` の 1 つに揃え、直近 `DECLINE_WINDOW` 期間の
完了ペースと、その直前の `DECLINE_WINDOW` 期間の完了ペースを比べる。ゾーンの閾値は
`health.zone_for_rate` に切り出し、バッジもシグナルも同じ関数で判定する (閾値を 2 箇所に持たない)。
完了した期間が `2*DECLINE_WINDOW` 未満なら発火せず、「計測期間が不足（2期間、必要 6期間以上）」の
ように期間数入りで理由を返す。回帰テストは「12 時間間隔で 7 週、前半 4 週 14 件/週・後半 3 週 0 件」で発火すること。

### 10.6 期間ごとの完了数が、終わっていない最後の期間を数え、最初の期間を落としていた

**何が起きたか**: `period_throughput` は snapshot を期間ごとのバケットに割り、各バケットの最後の値を
そのバケットの累計として使っていた。これには 2 つの誤りがあった。

1. 最後のバケットは、まだ終わっていない期間でも 1 サンプルとして数えた。10 件/週の一定ペースを
   0, 6.9, 13.9, 20.9, 27.9, 34.9, 35.05 日に計測すると `[10, 10, 10, 10, 1]` になる。
   末尾の 1 は 35 日目からの 0.15 日分の端数で、これが予測の 1 サンプルとして混ざる
2. 最初の期間の基準点が「最初のバケットの最後の snapshot」だった。累計 100 / 110 / 115 / 120 を
   0 / 6 / 13 / 20 日に計測すると `[5, 5]` になり、最初の週の +10 が落ちる

**なぜ既存のガードを通過したか**: 既存テストは snapshot をちょうど期間の境界 (0, 7, 14 日) で取っていた。
その場合「バケットの最後の値」と「境界での値」は一致するため、誤りが表に出ない。
10.1 の修正 (最初のバケットを基準点にする) も、最初のバケットに snapshot が 1 件しかない前提で正しかった。
予測側のガード (サンプル数・全ゼロ・残 0) はサンプルの個数と値しか見ず、各サンプルが
1 期間まるごとを表しているかは確かめていなかった。

**どう直したか**: 期間の境界で値を取る方式にした。境界 b_k = 最初の snapshot 時刻 + k × 期間
(k = 0..K、b_K は最後の snapshot 時刻以下の最大の境界)。各境界の値は「その時刻以前で最も新しい snapshot の累計」、
増分 k = max(0, 値(b_k) − 値(b_{k−1}))。これで (1) 終わっていない最後の期間は数えない
(2) 最初の期間の完了を数える (3) 計測開始前から完了していた在庫は数えない (10.1 の回帰テストもそのまま通る)。
上の 2 例はそれぞれ `[9, 10, 10, 10, 10]` と `[10, 5]` になる。前者の 9 は、7 日の境界の値として
6.9 日時点の累計を使うためで、境界ちょうどに snapshot が無い時の近似である。
なお前者は直した後もサンプルが 5 個あり予測が出る。35.05 日時点で 0〜35 日の 5 期間が実際に終わっているためで、
直したのは「端数の 1 期間を数えること」であって、サンプル数の判定ではない。

### 10.7 採用しなかった指摘

| 対象 | 判断 | 理由 |
|---|---|---|
| 手書きで壊れた `cycle` 行の扱い | 変えない (行ごとスキップのまま) | `toc cycle` は書き込み時に `steps.validate_step` で step を検証するため、通常の操作では壊れた行は生まれない。手で履歴を書き換えて壊れた行は、読み込み時に行番号付きの warning に残るので、黙って消えることはない |
| `Health.target_set` | 変えない (残す) | バッジを出すかどうかの判定点を 1 つにするため、意図的に置いた。目標未設定の判定は `throughput_health` だけが行い、バッジ側はその結果を見るだけにしている。消すとバッジ側が `target_per_week` を見て判定し直すことになり、判定点が 2 つになる |
