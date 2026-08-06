"""toc コマンド: init / snapshot / note / report / cycle / review。"""
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
from toc_engine.forecast import MIN_SAMPLES, forecast_periods_to_clear, period_throughput
from toc_engine.history import append_cycle, append_note, append_snapshot, read_history
from toc_engine.metrics import cfd_series, stage_metrics, throughput_series
from toc_engine.model import Goal, GoalNotDefinedError, Note, Snapshot, load_goal, save_goal
from toc_engine.recommend import recommend
from toc_engine.report import build_report, render_markdown
from toc_engine.signals import Signal, evaluate as evaluate_signals
from toc_engine.steps import CycleEntry, validate_step

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


def _review_path(config: Config) -> Path:
    return config.state_dir / "review.json"


def _current_constraint(snapshots: list[Snapshot]) -> str | None:
    """最新 snapshot 時点の制約 1 位 stage 名を返す(_cmd_note と同じ求め方)。"""
    if not snapshots:
        return None
    candidates = rank(stage_metrics(snapshots[-1]), cfd_series(snapshots))
    return candidates[0].stage_name if candidates else None


def _last_review_at(config: Config) -> datetime | None:
    """前回 review 実行時刻を review.json の generated_at から読む。無ければ None。"""
    path = _review_path(config)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["generated_at"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _forecast_unavailable_reason(remaining: int, samples: list[int]) -> str:
    """forecast_periods_to_clear が None を返した理由を推定する。"""
    if remaining <= 0:
        return "残件数が 0 件です"
    if len(samples) < MIN_SAMPLES:
        return f"計測期間が不足しています（{len(samples)}期間、必要 {MIN_SAMPLES}期間以上）"
    if all(s <= 0 for s in samples):
        return "直近の期間で完了実績がありません"
    return "予測が安定しないため打ち切りました（ばらつきが大きい可能性）"


def _forecast_payload(snapshots: list[Snapshot], constraint: str | None) -> dict:
    """制約の残 WIP から期間予測ペイロードを作る。予測不能なら理由付きで返す。"""
    if constraint is None:
        return {"available": False, "reason": "制約候補が特定できません"}
    metrics = stage_metrics(snapshots[-1])
    remaining = next((m.wip for m in metrics if m.stage.name == constraint), 0)
    samples = period_throughput(snapshots)
    forecast = forecast_periods_to_clear(remaining, samples)
    if forecast is None:
        return {"available": False, "reason": _forecast_unavailable_reason(remaining, samples)}
    return {
        "available": True,
        "percentiles": {str(p): v for p, v in forecast.percentiles.items()},
        "trials": forecast.trials,
        "samples_used": forecast.samples_used,
    }


def _signals_payload(signals: list[Signal]) -> list[dict]:
    return [{"kind": s.kind, "fired": s.fired, "detail": s.detail} for s in signals]


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
    constraint = candidates[0].stage_name if candidates else None
    forecast_payload = _forecast_payload(snapshots, constraint)
    signals = evaluate_signals(
        snapshots, goal, config.max_interval_days, _last_review_at(config)
    )
    report = build_report(
        goal, snap, metrics, candidates, recs, notes,
        forecast=forecast_payload, signals=_signals_payload(signals),
    )
    html_text = render_html(report, wip_history, throughput_series(snapshots))
    html_path = config.state_dir / "dashboard.html"
    md_path = config.state_dir / "report.md"
    html_path.write_text(html_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"ダッシュボード: {html_path}")
    print(f"Markdown: {md_path}")
    return 0


def _cmd_cycle(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    try:
        step = validate_step(args.step)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    snapshots, _, _ = read_history(_history_path(config))
    constraint = _current_constraint(snapshots)
    entry = CycleEntry(
        at=datetime.now(timezone.utc), step=step, constraint=constraint or "", action=args.action
    )
    append_cycle(_history_path(config), entry)
    print(f"記録しました ({step} / 制約: {constraint or 'なし'}): {args.action}")
    return 0


def _forecast_markdown_line(payload: dict) -> str:
    """予測ペイロードを 1 行の Markdown にする。予測不能なら理由を出す。"""
    if not payload["available"]:
        return f"予測不能: {payload['reason']}"
    pct = payload["percentiles"]
    parts = " / ".join(f"{p}%タイル {pct[p]:g}期間" for p in sorted(pct, key=int))
    return f"完了までの期間数: {parts}（サンプル {payload['samples_used']} 期間）"


def _render_review_markdown(review: dict) -> str:
    """review dict を Markdown 化する(発火シグナル→予測→制約→推奨打ち手の順)。"""
    lines = ["# 📋 レビュー議題", "", f"Goal: {review['goal']}", "", "## 🔔 発火シグナル", ""]
    fired = [s for s in review["signals"] if s["fired"]]
    lines += [f"- **{s['kind']}**: {s['detail']}" for s in fired] if fired else ["- なし"]
    lines += ["", "## 📈 予測", "", _forecast_markdown_line(review["forecast"])]
    lines += ["", "## ⛔ 制約", "", review["constraint"] or "不明"]
    lines += ["", "## 💡 推奨打ち手", ""]
    lines += [f"- [{r['step']}] {r['text']}" for r in review["recommendations"]]
    return "\n".join(lines) + "\n"


def _cmd_review(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    goal = _load_goal_or_exit(config)
    if goal is None:
        return 1
    snapshots, _, _ = read_history(_history_path(config))
    if not snapshots:
        print("履歴がありません。先に `toc snapshot` を実行してください。", file=sys.stderr)
        return 1

    signals = evaluate_signals(
        snapshots, goal, config.max_interval_days, _last_review_at(config)
    )
    constraint = _current_constraint(snapshots)
    forecast_payload = _forecast_payload(snapshots, constraint)

    wip_history = cfd_series(snapshots)
    metrics = stage_metrics(snapshots[-1])
    candidates = rank(metrics, wip_history)
    recs = recommend(candidates, metrics, wip_history)

    review = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal.statement,
        "constraint": constraint,
        "signals": _signals_payload(signals),
        "forecast": forecast_payload,
        "recommendations": [
            {"step": r.step, "text": r.text, "evidence": list(r.evidence)} for r in recs
        ],
    }
    _review_path(config).write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(_render_review_markdown(review))
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

    p_cycle = sub.add_parser("cycle", help="Five Focusing Steps のサイクルを記録する")
    p_cycle.add_argument("--config", default="config.local.toml")
    p_cycle.add_argument("--step", required=True)
    p_cycle.add_argument("--action", required=True)
    p_cycle.set_defaults(func=_cmd_cycle)

    p_review = sub.add_parser("review", help="レビュー招集シグナルと予測から議題を生成する")
    p_review.add_argument("--config", default="config.local.toml")
    p_review.set_defaults(func=_cmd_review)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
