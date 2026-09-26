# toc-engine

Goal-first な Theory of Constraints（制約理論）エンジン。
自分の作業パイプラインを計測し、システムの Goal 達成を制限している制約（ボトルネック）を根拠付きで特定する。

Eliyahu M. Goldratt『The Goal』で示された制約理論の独立実装です。
Goldratt 系組織とは無関係であり、公式・公認の実装ではありません。

## 特徴

- **Goal-first**: Goal を定義するまで計測できない。「Goal を決めずに計測するな」を仕組みで強制
- **制約スポットライト**: WIP × 滞留時間 × 増加傾向で制約候補をランク付け、根拠付きで提示
- **if-then 推奨**: 観測パターンから Exploit / Subordinate の打ち手候補を提案（判断は人間）
- **自己完結ダッシュボード**: CFD・Aging WIP・タイムラインを 1 つの HTML に生成（サーバ・外部依存なし）
- **定量 × 定性**: 実測メトリクスとあなたの意見（`toc note`）を同じタイムラインで見る
- **AI 伴走前提**: 質問スキーマ（`toc init --schema`）と JSON レポートで、AI アシスタントが運営を支援できる設計
- **シグナル駆動レビュー**: 固定周期ではなく、制約の移動・健全性の悪化・スループット停滞・上限日数の超過を検知して招集する（`toc review`）
- **予測できない時は予測しない**: Monte Carlo 完了予測はパーセンタイル（50/70/85）で示し、サンプル不足なら数字を出さず理由を返す
- **サイクル記録**: Five Focusing Steps のどの段階で何を打ったかを記録し（`toc cycle`）、次の計測で効果を検証する

## セットアップ

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e .
cp config.example.toml config.local.toml
# config.local.toml に自分のパイプラインのパスを書く
```

## 使い方

```bash
toc init --config config.local.toml       # Goal を定義（対話）
toc snapshot --config config.local.toml   # 計測して制約候補を出す
toc note --config config.local.toml "レビュー工程が辛い"   # 意見を記録
toc report --config config.local.toml     # HTML ダッシュボード生成

toc review --config config.local.toml     # シグナル判定 + 予測 → レビュー議題
toc cycle --config config.local.toml --step exploit --action "最古の項目から流した"
```

## 運転ループ

```
snapshot（実測）
   ↓ シグナル判定（制約移動 / 健全性悪化 / 停滞 / 上限日数超過）
   ↓ 発火時のみ
review（議題生成）→ 解釈・判断 → cycle（打ち手を記録）
   ↑                                   ↓
   └────── 次の snapshot で効果を検証 ──┘
```

固定周期のレビューは、変化のない回で形骸化します。実測が閾値を越えたときにだけ招集することで、
静かな時は邪魔せず、動いた時は即座に気づける状態を保ちます。

## 設計

設計判断とその根拠は [docs/design/](docs/design/) にあります。

## ライセンス

MIT
