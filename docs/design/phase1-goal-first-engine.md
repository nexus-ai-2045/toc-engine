# toc-engine 設計書

日付: 2026-07-20（v2: 対話ループ・可視化・AI運営層を追加）
ステータス: 承認済み（設計フェーズ完了）

## 1. 目的

Goldratt『The Goal』の TOC（Theory of Constraints / 制約理論）を実行可能なロジックとして実装した
Python ライブラリ + CLI。ユーザーが対話しながらインタラクティブに、実測を土台として
Goal を定義し、制約を特定し、Five Focusing Steps のループを運転して Goal 達成へ向かえるようにする。

最初のユースケース: 作者自身の作業システム（コンテンツ制作フロー + todo/handoff タスク管理）の
全体定量化と制約特定。

将来的に public リポジトリとして公開する前提で、最初から公開可能な構造にする。

### ポジショニング（2026-07-20 調査に基づく）

- TOC 専用ロジック（DBR / バッファ管理 / フィーバーチャート）の OSS 実装は存在しない
  （フロー/Kanban 系 OSS は豊富だが TOC ロジックは空白地帯）
- フロー分析ツールへの AI 対話統合の一次情報もほぼ皆無
- → 「Goal-first + TOC ロジック + AI 対話運営」の OSS として空白を埋める初の存在を狙う

## 2. 設計原則

1. **Goal-first**: TOC の出発点は制約探しではなく「システムの Goal は何か」。
   Goal 未定義時は `toc snapshot` の実行を拒否し `toc init` へ誘導する。仕組みで思想を強制する。
2. **分析は自動、判断は人間**: 制約の特定・定量化・打ち手候補の提示はエンジンが行う。
   採否の判断は人間。エンジンは自動実行しない。
3. **レビューはシステムが呼ぶ**: 固定周期のカレンダー駆動ではなく、実測がシグナル閾値を
   越えたときにレビューを招集する。静かな時は邪魔しない（形骸化・通知疲れの防止）。
4. **定量と定性の同時間軸**: 実測メトリクスとユーザーの意見・決定を同じタイムラインに重ねる。
5. **公開境界の分離**: 個人のパス・データは gitignore された `config.local.toml` / `goal.toml` /
   ローカル状態ファイルのみに置く。リポジトリには `config.example.toml` だけをコミットする。
6. **依存最小**: stdlib 中心（設定は `tomllib` で読める TOML）。可視化は CDN 依存なしの
   自己完結 HTML。Python 3.13。

## 3. 全体構造: 3 層アーキテクチャ

```
[エンジン層]  決定論的コア（計測・制約特定・推奨ルール・シグナル判定）← テスト可能、公開の主役
[可視化層]   自己完結 HTML ダッシュボード（サーバ不要、開くだけ）
[AI運営層]   Claude 等が対話・解釈・伴走する設計（質問スキーマ・議題 JSON・skill 同梱）
```

### 運転ループ（プロダクトの背骨）

```
snapshot（実測・毎日でも軽い）
   ↓ シグナル判定（制約移動 / ゾーン悪化 / 流出低下 / 効果測定データ充足 / max_interval 超過）
   ↓ 発火時のみ
review 議題生成（JSON）→ AI と対話（解釈・意見記録・打ち手決定）→ note 記録
   ↑                                                        ↓
   └────────── 次の snapshot で打ち手の効果を実測検証 ←──────────┘
```

Five Focusing Steps を「グラフを見せて終わり」でなく運転ループとして実装する。
これが The Goal の「Process of Ongoing Improvement」の実装そのもの。

## 4. スコープ

### Phase 1（MVP）

- `toc init`: Goal 定義（質問スキーマ JSON 提供 + CLI 素朴対話 fallback）→ `goal.toml`
- `toc snapshot`: 全ソース走査 → 正規化 → 履歴追記（JSONL）→ 制約候補ランク付け
- `toc note`: ユーザーの意見・決定の 1 行記録（タイムスタンプ + その時点の制約と紐付け）
- `toc report`: 自己完結 HTML ダッシュボード + Markdown / JSON レポート生成
- if-then 推奨エンジン（打ち手候補の提示、根拠データ添付）
- アダプタ 2 種: ディレクトリ型パイプライン / Markdown タスクリスト

### Phase 2（MVP 後・有効性確認してから）

- `toc review`: シグナル判定 + 議題 JSON 生成 + レビュー記録（AI が対話進行）
- 制約移動検知（Step 5 の惰性検知）
- `toc cycle`: Five Focusing Steps のサイクル記録
- AGENTS.md / skill の充実（AI 運営層の本格化）

### Phase 3（構想）

- `toc serve`: ローカル Web ダッシュボード（対話込みのインタラクティブ UI）
- 制約移動履歴の時系列再生（playback。Epicflow のバブルグラフ的発想）

### スコープ外

- cron 常駐・時系列 DB・SaaS 化
- 打ち手の自動実行

## 5. リポジトリ構造

```
toc-engine/
├── README.md              # 出典明記（Goldratt "The Goal"）+ 非公認 disclaimer + ポジショニング
├── LICENSE                # MIT
├── pyproject.toml
├── config.example.toml    # 設定サンプル（公開用）
├── docs/superpowers/specs/ # 設計書・実装計画
├── src/toc_engine/
│   ├── model.py           # Goal / Stage / WorkItem / Snapshot / Note（正規化データモデル）
│   ├── metrics.py         # WIP・滞留時間・流入流出率・スループット・CFD 用系列
│   ├── constraint.py      # 制約候補のランク付けヒューリスティクス
│   ├── recommend.py       # if-then 推奨ルール（Exploit / Subordinate / Elevate / 惰性検知）
│   ├── signals.py         # レビュー招集シグナル判定（Phase 2 で本格化、閾値定義は P1 から）
│   ├── history.py         # スナップショット履歴（JSONL 追記・読出）
│   ├── report.py          # Markdown / JSON レポート生成
│   ├── dashboard.py       # 自己完結 HTML ダッシュボード生成
│   ├── steps.py           # Five Focusing Steps サイクル記録（Phase 2）
│   ├── adapters/
│   │   ├── base.py        # Adapter インターフェース（scan() → list[WorkItem]）
│   │   ├── dir_pipeline.py# ディレクトリ型（例: inbox→drafts→公開待ち→published）
│   │   └── md_tasks.py    # Markdown チェックボックス型（todo.md 等）
│   └── cli.py             # toc init / snapshot / note / report / review / cycle
└── tests/                 # pytest + fixture ディレクトリ
```

### コンポーネント責務

| モジュール | 責務 | 依存 |
|---|---|---|
| `model.py` | Goal / Stage / WorkItem / Snapshot / Note のデータクラス定義 | なし |
| `adapters/base.py` | `scan() → list[WorkItem]` の抽象インターフェース | model |
| `adapters/dir_pipeline.py` | ディレクトリをステージとみなし走査。mtime で滞留時間を推定 | base |
| `adapters/md_tasks.py` | Markdown のチェックボックス行をタスクとして解析 | base |
| `metrics.py` | Snapshot から工程別 WIP・滞留・流入流出率・スループット・CFD 系列を計算 | model |
| `constraint.py` | metrics を入力に制約候補をランク付け（WIP × 滞留時間 × 流出率低下） | metrics |
| `recommend.py` | 観測パターン → TOC の打ち手候補（if-then ルール、根拠添付、提案止まり） | metrics, constraint |
| `signals.py` | レビュー招集判定（制約移動 / ゾーン悪化 / 流出低下 / max_interval 超過） | history, constraint |
| `history.py` | snapshot / note / 打ち手の JSONL 追記・読出 | model |
| `report.py` | Goal 起点の Markdown / JSON レポート | model, metrics, constraint, recommend |
| `dashboard.py` | 自己完結 HTML（インライン SVG/CSS/JS、外部依存なし） | report と同入力 |
| `cli.py` | サブコマンド一式。Goal ガード | 全部 |

## 6. Goal 定義フロー（`toc init`）

本の論理をそのまま質問に落とした対話フロー:

1. このシステムは何を生み出すためにある？（Goal 文の言語化）
2. Throughput の単位は？ —「完了」と数えるものは何か（例: 公開された記事）
3. Inventory は何？ — 途中で滞留するもの（例: 下書き、未処理タスク）
4. Operating Expense は何？ — Throughput に変換するために費やすもの（例: 作業時間）

実装形態:
- エンジンは質問フローを**質問スキーマ（JSON）**として提供する
- AI（Claude Code 等）がスキーマを読み、自然言語の対話で回答を引き出して `goal.toml` を書く
- CLI 単体でも素朴なプロンプト対話で完結できる（fallback）

回答は `goal.toml`（gitignore 対象）に保存。

## 7. ダッシュボード構成（`toc report` → HTML 1 ファイル）

```
┌─────────────────────────────────────────┐
│ 🎯 Goal文 ＋ Throughput実績 vs 目標（スパークライン）  │  ← 常に最上部。Goal-first
├───────────────┬─────────────────────────┤
│ ⛔ 制約スポットライト │  CFD（累積フロー図）              │
│  「今の制約は◯◯」   │  帯の膨らみ = 制約前の行列         │
│  根拠3点＋推奨打ち手  │                              │
├───────────────┼─────────────────────────┤
│ Aging WIP       │ フィーバーチャート（Goal健全性）     │
│ 止まってる項目Top5  │ 緑/黄/赤/黒 4ゾーン              │
├───────────────┴─────────────────────────┤
│ 📓 タイムライン: 実測イベント＋意見(toc note)＋打ち手      │
└─────────────────────────────────────────┘
```

根拠（2026-07-20 調査）:
- CFD センター配置は ActionableAgile（フロー分析のデファクト）の標準構成
- CFD + バッファチャート融合は TameFlow 手法の系譜（バッファ 4 ゾーン: 緑/黄/赤/黒）
- 定量×定性の同時間軸タイムラインは既存ツールにない差別化点

## 8. if-then 推奨ルール（`recommend.py`）

| 観測パターン（if） | 提案（then） |
|---|---|
| 制約工程の流入 > 流出が継続 | Subordinate: 上流の投入を制約ペースに絞る |
| 制約工程に待ち・中断が多い | Exploit: 制約の稼働を守る（割り込み排除） |
| Exploit/Subordinate 実施済みでも改善なし | Elevate: 能力増強の投資を検討 |
| 制約が移動したのに旧制約のルールが残存 | Step 5: 惰性の検知、ルール見直し |

各提案に根拠データを添付。提案止まりで自動実行はしない。

## 9. レビュー招集シグナル（`signals.py`）

```
毎日:  snapshot だけ軽く取る（履歴が貯まる）
即時:  シグナル発火でレビュー招集
       - 制約が移動した
       - バッファゾーンが悪化した（緑→黄、黄→赤）
       - 制約工程の流出が N snapshot 連続で低下
       - 打ち手実施後、効果測定に必要なデータが溜まった
上限:  何も起きなくても max_interval_days（既定 3、可変）超過でレビュー
```

- 周期は人が決めるのではなく、実測が「今レビューする価値がある」と言ってくる方式
- `max_interval_days = 1` にすれば毎日型としても運用できる
- 設計判断の背景: AI がレビューを進行するためレビューコストが低く高頻度化が可能。
  ただし固定短周期は「変化なし」の儀式化を招くため、シグナル駆動 + 上限日数とした

## 10. データフロー

1. `toc snapshot` 実行 → `goal.toml` 存在チェック（なければ拒否 + `toc init` へ誘導）
2. `config.local.toml` の定義に従い各アダプタが対象を走査
3. 全ソースを共通の `Snapshot`（工程 × アイテム × 滞留時間）に正規化、履歴（JSONL）に追記
4. metrics 計算 → constraint がランク付け → recommend が打ち手候補生成 → signals が招集判定
5. `toc report`: Goal 文 → Throughput 実績 → 制約スポットライト → 各チャート → タイムライン

## 11. エラーハンドリング

- パス不在・読めないファイルは warn してスキップ（1 ソースの失敗で全体を落とさない）
- 設定ファイルの構文エラーは明確なメッセージで早期失敗
- Goal 未定義は明示的な誘導メッセージ付きで実行拒否
- 履歴 JSONL の壊れた行は warn してスキップ（読める行だけで継続）

## 12. テスト戦略

- TDD（pytest）で進める
- fixture ディレクトリで各アダプタの走査を検証
- 制約ランキング・推奨ルール・シグナル判定は既知の入力 → 期待出力のテーブルテスト
- Goal ガード（未定義時の拒否）のテスト
- ダッシュボードは「生成 HTML に期待要素が含まれる」のスモークテスト

## 13. 完成条件（Definition of Done）

### Phase 1: MVP

| # | 条件 | 検証方法（evidence） |
|---|---|---|
| 1 | `toc init` の対話で第三者が Goal 定義にたどり着ける | 作者自身が自分の Goal を定義できたこと |
| 2 | `toc snapshot` 1 コマンドで、コンテンツフロー + todo/handoff を横断した Goal 起点の定量化ができる | 実データで実行し、レポート実物を提示 |
| 3 | HTML ダッシュボードに Goal 文・Throughput 実績・制約スポットライト（根拠 + 推奨打ち手）・CFD・Aging WIP・タイムラインが表示される | ダッシュボード実物の目視確認（ユーザー承認） |
| 4 | `toc note` で意見を記録でき、タイムラインに実測と重なって表示される | 記録 → 表示の実演 |
| 5 | 全テスト green | `pytest` 実行ログ |
| 6 | 個人データ・実パスがリポジトリに一切入っていない | `git grep` + tracked files 確認 |
| 7 | 履歴がクリーン（そのまま public 化できる状態） | `git log` / `git status` |

注: フィーバーチャートはバッファ設定（目標設定）が前提のため、Goal に目標値がある場合のみ表示（なければ枠ごと非表示）。

### Phase 2: レビュー・ループ運用

- シグナル発火 → `toc review` の議題 JSON → AI 対話 → 記録、の 1 サイクルが実際に回ること
- 制約移動が検知・報告されること
- 検証: 実際のレビュー記録が残ること

### Public 公開 Ready（最終ゴール）

| # | 条件 |
|---|---|
| 1 | LICENSE (MIT) + README に出典明記 + 非公認 disclaimer + ポジショニング記載 |
| 2 | `config.example.toml` のみで第三者がセットアップ可能（README の手順通りに動く） |
| 3 | public-repo-readiness 監査（PUBLIC_READY.md / SECURITY.md / secrets スキャン）を PASS |
| 4 | 公開 push は毎回の明示承認 |

### 判断点

Phase 1 完了 → 実レポートを見て有効性を判断 → 有効なら Phase 2 と public 整備へ。
「これは使えない」となったら Phase 2 に進まず設計を見直す。

## 14. 法的整理（名称使用）

- 理論・手法そのものは著作権の対象外。Five Focusing Steps や T/I/OE を独自の言葉で説明・実装するのは問題ない
- 「Theory of Constraints」は記述的・一般的な用語として指名的使用の範囲で使用する
- 書籍の文章はコピーしない（要約・独自表現のみ）
- README に「Goldratt 系組織とは無関係の独立実装」と明記し、公式・公認を装わない
