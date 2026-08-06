"""toc コマンド: init / snapshot / note / report。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from toc_engine.adapters.base import take_snapshot
from toc_engine.config import Config, build_adapters, load_config
from toc_engine.constraint import rank
from toc_engine.dashboard import render_html
from toc_engine.history import append_note, append_snapshot, read_history
from toc_engine.metrics import cfd_series, stage_metrics, throughput_series
from toc_engine.model import Goal, GoalNotDefinedError, Note, load_goal, save_goal
from toc_engine.recommend import recommend
from toc_engine.report import build_report, render_markdown

# AI が対話を進行するための質問スキーマ（toc init --schema で取得）
QUESTION_SCHEMA = {
    "version": 1,
    "purpose": "TOC の出発点となる Goal の定義。回答を toc init の非対話フラグで渡す。",
    "questions": [
        {"key": "statement", "flag": "--statement", "required": True,
         "prompt": "このシステムは何を生み出すためにありますか？（Goal を 1 文で）"},
        {"key": "throughput_unit", "flag": "--throughput-unit", "required": True,
         "prompt": "Throughput の単位は？（『完了』と数えるもの。例: 公開された記事）"},
        {"key": "inventory", "flag": "--inventory", "required": False,
         "prompt": "Inventory は何ですか？（途中で滞留するもの）"},
        {"key": "operating_expense", "flag": "--operating-expense", "required": False,
         "prompt": "Operating Expense は何ですか？（Throughput に変換するために費やすもの）"},
        {"key": "target_per_week", "flag": "--target-per-week", "required": False,
         "type": "number", "prompt": "週あたりの目標 Throughput（数値、任意）"},
    ],
}


def _goal_path(config: Config) -> Path:
    return config.state_dir / "goal.toml"


def _history_path(config: Config) -> Path:
    return config.state_dir / "history.jsonl"


def _cmd_init(args: argparse.Namespace) -> int:
    if args.schema:
        print(json.dumps(QUESTION_SCHEMA, ensure_ascii=False, indent=2))
        return 0
    config = load_config(Path(args.config))
    if args.statement and args.throughput_unit:
        # 非対話モード（AI 運営層が使う経路）
        goal = Goal(
            statement=args.statement,
            throughput_unit=args.throughput_unit,
            inventory=args.inventory or "",
            operating_expense=args.operating_expense or "",
            target_per_week=args.target_per_week,
        )
    else:
        # CLI 素朴対話 fallback
        answers: dict[str, str] = {}
        for q in QUESTION_SCHEMA["questions"]:
            while True:
                value = input(f"{q['prompt']}\n> ").strip()
                if value or not q["required"]:
                    break
                print("(必須項目です)")
            answers[q["key"]] = value
        target = answers.get("target_per_week", "")
        goal = Goal(
            statement=answers["statement"],
            throughput_unit=answers["throughput_unit"],
            inventory=answers.get("inventory", ""),
            operating_expense=answers.get("operating_expense", ""),
            target_per_week=float(target) if target else None,
        )
    save_goal(goal, _goal_path(config))
    print(f"Goal を保存しました: {_goal_path(config)}")
    return 0


def _load_goal_or_exit(config: Config) -> Goal | None:
    try:
        return load_goal(_goal_path(config))
    except GoalNotDefinedError as e:
        print(str(e), file=sys.stderr)
        return None


def _cmd_snapshot(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_config(config_path)
    goal = _load_goal_or_exit(config)
    if goal is None:
        return 1  # Goal-first: 計測を拒否
    adapters = build_adapters(config, base=config_path.parent)
    snap = take_snapshot(adapters)
    append_snapshot(_history_path(config), snap)
    snapshots, notes, _ = read_history(_history_path(config))
    wip_history = cfd_series(snapshots)
    metrics = stage_metrics(snap)
    candidates = rank(metrics, wip_history)
    recs = recommend(candidates, metrics, wip_history)
    report = build_report(goal, snap, metrics, candidates, recs, notes)
    report_path = config.state_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(render_markdown(report))
    print(f"(JSON: {report_path})")
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    snapshots, _, _ = read_history(_history_path(config))
    constraint = None
    if snapshots:
        candidates = rank(stage_metrics(snapshots[-1]), cfd_series(snapshots))
        if candidates:
            constraint = candidates[0].stage_name
    note = Note(at=datetime.now(timezone.utc), text=args.text, constraint=constraint)
    append_note(_history_path(config), note)
    print(f"記録しました (制約: {constraint or 'なし'})")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_config(config_path)
    goal = _load_goal_or_exit(config)
    if goal is None:
        return 1
    snapshots, notes, _ = read_history(_history_path(config))
    if not snapshots:
        print("履歴がありません。先に `toc snapshot` を実行してください。", file=sys.stderr)
        return 1
    snap = snapshots[-1]
    wip_history = cfd_series(snapshots)
    metrics = stage_metrics(snap)
    candidates = rank(metrics, wip_history)
    recs = recommend(candidates, metrics, wip_history)
    report = build_report(goal, snap, metrics, candidates, recs, notes)
    html_text = render_html(report, wip_history, throughput_series(snapshots))
    html_path = config.state_dir / "dashboard.html"
    md_path = config.state_dir / "report.md"
    html_path.write_text(html_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"ダッシュボード: {html_path}")
    print(f"Markdown: {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="toc",
        description="Goal-first な Theory of Constraints エンジン",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Goal を定義する（TOC の出発点）")
    p_init.add_argument("--config", default="config.local.toml")
    p_init.add_argument("--schema", action="store_true",
                        help="質問スキーマ JSON を表示（AI 対話用）")
    p_init.add_argument("--statement")
    p_init.add_argument("--throughput-unit", dest="throughput_unit")
    p_init.add_argument("--inventory")
    p_init.add_argument("--operating-expense", dest="operating_expense")
    p_init.add_argument("--target-per-week", dest="target_per_week", type=float)
    p_init.set_defaults(func=_cmd_init)

    p_snap = sub.add_parser("snapshot", help="全ソースを計測し制約候補を出す")
    p_snap.add_argument("--config", default="config.local.toml")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_note = sub.add_parser("note", help="意見・決定を記録する（定性データ）")
    p_note.add_argument("--config", default="config.local.toml")
    p_note.add_argument("text")
    p_note.set_defaults(func=_cmd_note)

    p_report = sub.add_parser("report", help="HTML ダッシュボードを生成する")
    p_report.add_argument("--config", default="config.local.toml")
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
