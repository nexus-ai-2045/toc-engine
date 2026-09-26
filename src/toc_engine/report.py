"""Goal 起点のレポート組み立て (JSON 化可能 dict) と Markdown 描画。"""
from __future__ import annotations

from toc_engine.constraint import ConstraintCandidate
from toc_engine.metrics import StageMetrics, throughput_total
from toc_engine.model import Goal, Note, Snapshot
from toc_engine.recommend import Recommendation
from toc_engine.steps import CycleEntry


def build_report(
    goal: Goal,
    snapshot: Snapshot,
    metrics: list[StageMetrics],
    candidates: list[ConstraintCandidate],
    recommendations: list[Recommendation],
    notes: list[Note],
    forecast: dict | None = None,
    signals: list[dict] | None = None,
    cycles: list[CycleEntry] | None = None,
) -> dict:
    """全計測結果を Goal 起点の 1 つの dict にまとめる。

    forecast / signals は呼び出し側 (cli) で組み立てた JSON 化可能な dict をそのまま
    受け取る。渡された場合のみキーを追加する（None のまま渡された既存呼び出しは
    forecast/signals キーなしの従来通りの dict になる）。
    cycles を渡すとタイムラインに介入記録も載る（before/after 検証用）。
    """
    timeline = [
        {
            "at": snapshot.taken_at.isoformat(),
            "kind": "snapshot",
            "text": f"計測: {len(snapshot.items)} 件 / 完了累計 {throughput_total(snapshot)}",
        }
    ] + [
        {"at": n.at.isoformat(), "kind": "note", "text": n.text, "constraint": n.constraint}
        for n in notes
    ] + [
        {
            "at": c.at.isoformat(),
            "kind": "cycle",
            "text": f"{c.step}: {c.action}",
            "constraint": c.constraint,
        }
        for c in (cycles or [])
    ]
    timeline.sort(key=lambda e: e["at"], reverse=True)
    report = {
        "goal": {
            "statement": goal.statement,
            "throughput_unit": goal.throughput_unit,
            "inventory": goal.inventory,
            "operating_expense": goal.operating_expense,
            "target_per_week": goal.target_per_week,
        },
        "taken_at": snapshot.taken_at.isoformat(),
        "throughput_total": throughput_total(snapshot),
        "stages": [
            {
                "name": m.stage.name,
                "terminal": m.stage.terminal,
                "wip": m.wip,
                "avg_age_days": m.avg_age_days,
                "max_age_days": m.max_age_days,
                "oldest": [
                    {"title": i.title, "age_days": i.age_days} for i in m.oldest
                ],
            }
            for m in metrics
        ],
        "constraints": [
            {"stage": c.stage_name, "score": c.score, "evidence": list(c.evidence)}
            for c in candidates
        ],
        "recommendations": [
            {"step": r.step, "text": r.text, "evidence": list(r.evidence)}
            for r in recommendations
        ],
        "timeline": timeline,
    }
    if forecast is not None:
        report["forecast"] = forecast
    if signals is not None:
        report["signals"] = signals
    return report


def render_markdown(report: dict) -> str:
    """レポート dict を Goal 起点の Markdown にする。"""
    g = report["goal"]
    lines = [
        f"# 🎯 {g['statement']}",
        "",
        f"- Throughput: **{report['throughput_total']} {g['throughput_unit']}**（累計）",
        f"- 計測時刻: {report['taken_at']}",
        "",
        "## ⛔ 制約候補",
        "",
    ]
    for i, c in enumerate(report["constraints"][:3], 1):
        lines.append(f"{i}. **{c['stage']}** (score {c['score']}) — {' / '.join(c['evidence'])}")
    lines += ["", "## 💡 推奨打ち手", ""]
    for r in report["recommendations"]:
        lines.append(f"- [{r['step']}] {r['text']}")
        for e in r["evidence"]:
            lines.append(f"  - 根拠: {e}")
    lines += ["", "## 工程別メトリクス", "", "| 工程 | WIP | 平均滞留(日) | 最大滞留(日) |", "|---|---|---|---|"]
    for s in report["stages"]:
        avg = f"{s['avg_age_days']:.1f}" if s["avg_age_days"] is not None else "-"
        mx = f"{s['max_age_days']:.1f}" if s["max_age_days"] is not None else "-"
        lines.append(f"| {s['name']}{' ✅' if s['terminal'] else ''} | {s['wip']} | {avg} | {mx} |")
    lines += ["", "## 📓 タイムライン", ""]
    for e in report["timeline"]:
        lines.append(f"- {e['at']} [{e['kind']}] {e['text']}")
    return "\n".join(lines) + "\n"
