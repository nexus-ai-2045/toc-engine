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

## セットアップ

### Linux / macOS

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e .
cp config.example.toml config.local.toml
# config.local.toml に自分のパイプラインのパスを書く
```

### Windows

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e .
copy config.example.toml config.local.toml
# config.local.toml に自分のパイプラインのパスを書く
```

## 使い方

venv を有効化するか、`.venv/bin` 経由で呼ぶ（未 activate の裸の `toc` は見つからない）:

```bash
# どちらか一方
source .venv/bin/activate   # Windows: .venv\Scripts\activate
# または各コマンドを .venv/bin/toc で実行

toc init --config config.local.toml       # Goal を定義（対話）
toc snapshot --config config.local.toml   # 計測して制約候補を出す
toc note --config config.local.toml "レビュー工程が辛い"   # 意見を記録
toc report --config config.local.toml     # HTML ダッシュボード生成
```

## ライセンス

MIT
