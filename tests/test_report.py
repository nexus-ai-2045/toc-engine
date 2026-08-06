"""report.py のテスト: Goal 起点のレポート構造。"""
import json
from datetime import datetime, timezone

from toc_engine.constraint import ConstraintCandidate
from toc_engine.metrics import stage_metrics, throughput_total
from toc_engine.model import Goal, Note, Snapshot, Stage, WorkItem
from toc_engine.recommend import Recommendation
from toc_engine.report import build_report, render_markdown


def _fixture():
    goal = Goal("記事を届ける", "公開された記事", target_per_week=2.0)
    snap = Snapshot(
        taken_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        stages=(Stage("a:inbox", 0, False), Stage("a:done", 1, True)),
        items=(
            WorkItem("i1", "draft-x", "a:inbox", "a", 5.0),
            WorkItem("i2", "pub-y", "a:done", "a", 1.0),
        ),
    )
    metrics = stage_metrics(snap)
    candidates = [ConstraintCandidate("a:inbox", 8.0, ("WIP 1 件",))]
    recs = [Recommendation("identify", "観察から始める", ())]
    notes = [Note(datetime(2026, 7, 19, tzinfo=timezone.utc), "辛い", "a:inbox")]
    return goal, snap, metrics, candidates, recs, notes


def test_build_report_is_goal_first_and_json_able():
    goal, snap, metrics, candidates, recs, notes = _fixture()
    report = build_report(goal, snap, metrics, candidates, recs, notes)
    # Goal が最上位に置かれる（Goal-first）
    assert report["goal"]["statement"] == "記事を届ける"
    assert report["throughput_total"] == throughput_total(snap)
    assert report["constraints"][0]["stage"] == "a:inbox"
    assert report["recommendations"][0]["step"] == "identify"
    # timeline は snapshot と note が時系列で混在
    kinds = [e["kind"] for e in report["timeline"]]
    assert "note" in kinds and "snapshot" in kinds
    json.dumps(report)  # JSON 化可能であること


def test_render_markdown_leads_with_goal():
    goal, snap, metrics, candidates, recs, notes = _fixture()
    md = render_markdown(build_report(goal, snap, metrics, candidates, recs, notes))
    lines = md.splitlines()
    assert "記事を届ける" in lines[0]  # 冒頭は Goal 文
    assert "a:inbox" in md            # 制約が載る
    assert "観察から始める" in md      # 推奨が載る


def test_build_report_includes_forecast_and_signals_when_provided():
    goal, snap, metrics, candidates, recs, notes = _fixture()
    forecast = {
        "available": True,
        "percentiles": {"50": 3.0, "70": 4.0, "85": 5.0},
        "trials": 1000,
        "samples_used": 6,
    }
    signals = [{"kind": "constraint_moved", "fired": True, "detail": "制約が a→b に変化"}]
    report = build_report(
        goal, snap, metrics, candidates, recs, notes,
        forecast=forecast, signals=signals,
    )
    assert report["forecast"] == forecast
    assert report["signals"] == signals
    json.dumps(report)  # JSON 化可能なまま


def test_build_report_omits_forecast_and_signals_when_not_provided():
    goal, snap, metrics, candidates, recs, notes = _fixture()
    report = build_report(goal, snap, metrics, candidates, recs, notes)
    assert "forecast" not in report
    assert "signals" not in report
