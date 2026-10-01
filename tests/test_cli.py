"""cli.py の統合テスト。"""
import json

import pytest

from toc_engine.cli import main


@pytest.fixture
def workspace(tmp_path):
    """設定 + データソース + goal 一式を tmp に作る。"""
    (tmp_path / "inbox").mkdir()
    (tmp_path / "done").mkdir()
    (tmp_path / "inbox" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "done" / "b.md").write_text("y", encoding="utf-8")
    cfg = tmp_path / "config.local.toml"
    cfg.write_text(
        """
[core]
state_dir = ".toc"

[[source]]
type = "dir_pipeline"
name = "articles"
stages = [
  { name = "inbox", path = "inbox" },
  { name = "done", path = "done", terminal = true },
]
""",
        encoding="utf-8",
    )
    return tmp_path, cfg


def _init_goal(cfg):
    return main(
        [
            "init", "--config", str(cfg),
            "--statement", "記事を届ける",
            "--throughput-unit", "公開された記事",
            "--target-per-week", "2",
        ]
    )


def test_init_schema_prints_questions(capsys):
    assert main(["init", "--schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    keys = [q["key"] for q in schema["questions"]]
    assert keys == [
        "statement", "throughput_unit", "inventory",
        "operating_expense", "target_per_week",
    ]


def test_snapshot_refuses_without_goal(workspace, capsys):
    tmp_path, cfg = workspace
    assert main(["snapshot", "--config", str(cfg)]) == 1
    assert "toc init" in capsys.readouterr().err  # Goal-first の強制


def test_init_then_snapshot_then_report(workspace, capsys):
    tmp_path, cfg = workspace
    assert _init_goal(cfg) == 0
    assert (tmp_path / ".toc" / "goal.toml").exists()

    assert main(["snapshot", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "記事を届ける" in out          # サマリは Goal 起点
    assert "articles:inbox" in out        # 制約候補が出る
    assert (tmp_path / ".toc" / "history.jsonl").exists()
    report = json.loads((tmp_path / ".toc" / "report.json").read_text(encoding="utf-8"))
    assert report["goal"]["statement"] == "記事を届ける"

    assert main(["report", "--config", str(cfg)]) == 0
    html_text = (tmp_path / ".toc" / "dashboard.html").read_text(encoding="utf-8")
    assert "記事を届ける" in html_text
    assert (tmp_path / ".toc" / "report.md").exists()


def test_note_links_to_current_constraint(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    capsys.readouterr()
    assert main(["note", "--config", str(cfg), "inbox が詰まってる"]) == 0
    history = (tmp_path / ".toc" / "history.jsonl").read_text(encoding="utf-8")
    last = json.loads(history.strip().splitlines()[-1])
    assert last["type"] == "note"
    assert last["text"] == "inbox が詰まってる"
    assert last["constraint"] == "articles:inbox"


def test_report_without_snapshot_errors(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    assert main(["report", "--config", str(cfg)]) == 1
    assert "snapshot" in capsys.readouterr().err


def test_cycle_records_entry_linked_to_constraint(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    capsys.readouterr()
    rc = main([
        "cycle", "--config", str(cfg),
        "--step", "exploit", "--action", "最古のアイテムから流す",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "exploit" in out
    history = (tmp_path / ".toc" / "history.jsonl").read_text(encoding="utf-8")
    last = json.loads(history.strip().splitlines()[-1])
    assert last["type"] == "cycle"
    assert last["step"] == "exploit"
    assert last["action"] == "最古のアイテムから流す"
    assert last["constraint"] == "articles:inbox"


def test_cycle_unknown_step_errors_without_traceback(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    rc = main([
        "cycle", "--config", str(cfg),
        "--step", "not-a-step", "--action", "x",
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not-a-step" in err
    assert "Traceback" not in err


def test_review_requires_goal(workspace, capsys):
    tmp_path, cfg = workspace
    assert main(["review", "--config", str(cfg)]) == 1
    assert "toc init" in capsys.readouterr().err


def test_review_requires_history(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    assert main(["review", "--config", str(cfg)]) == 1
    assert "snapshot" in capsys.readouterr().err


def test_review_generates_review_json_with_four_signals(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    capsys.readouterr()
    rc = main(["review", "--config", str(cfg)])
    assert rc == 0
    review_path = tmp_path / ".toc" / "review.json"
    assert review_path.exists()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["goal"] == "記事を届ける"
    assert len(review["signals"]) == 4
    assert {s["kind"] for s in review["signals"]} == {
        "constraint_moved", "health_worsened", "throughput_stalled", "interval_exceeded",
    }
    assert "generated_at" in review
    out = capsys.readouterr().out
    assert "レビュー議題" in out


def test_cli_does_not_call_rank_directly():
    """制約の順位付けは constraint の入口関数だけを通す (設計 10.2)。

    cli が rank(stage_metrics(...), cfd_series(...)) を直書きすると、引数の渡し方の
    違いで「レポートの制約」と「シグナル・cycle 記録の制約」がズレる。
    """
    import ast
    import inspect

    import toc_engine.cli as cli

    tree = ast.parse(inspect.getsource(cli))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {
        alias.asname or alias.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }
    assert "rank" not in names
    assert "rank" not in imported


@pytest.mark.parametrize(
    "bad_content",
    [
        '{"generated_at": null}',
        '{"generated_at": 12345}',
        '{"generated_at": "not-a-date"}',
        '["not", "a", "dict"]',
        "{broken json",
        "{}",
    ],
)
@pytest.mark.parametrize("command", ["review", "report"])
def test_invalid_review_json_is_warned_and_ignored(
    workspace, capsys, caplog, bad_content, command
):
    """review.json の generated_at が null や数値でも落ちず、警告して未レビュー扱いにする。

    回帰: 旧実装は datetime.fromisoformat(None / 数値) の TypeError を捕まえず、
    toc review / toc report がクラッシュしていた。
    """
    import logging

    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    (tmp_path / ".toc" / "review.json").write_text(bad_content, encoding="utf-8")
    capsys.readouterr()
    with caplog.at_level(logging.WARNING, logger="toc_engine.cli"):
        assert main([command, "--config", str(cfg)]) == 0
    assert "review.json" in caplog.text


def test_missing_review_json_is_silent(workspace, capsys, caplog):
    """review.json が無いのは「まだレビューしていない」正常状態なので警告しない。"""
    import logging

    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    with caplog.at_level(logging.WARNING, logger="toc_engine.cli"):
        assert main(["report", "--config", str(cfg)]) == 0
    assert "review.json" not in caplog.text


def test_report_dashboard_shows_forecast_reason_from_forecast(workspace, capsys):
    """予測を出さない時、ダッシュボードには forecast.py が返した理由がそのまま載る。"""
    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])  # snapshot 1 件 = 期間 0 → サンプル不足
    assert main(["report", "--config", str(cfg)]) == 0
    html_text = (tmp_path / ".toc" / "dashboard.html").read_text(encoding="utf-8")
    assert "予測不能: 計測期間が不足しています" in html_text
    assert "理由不明" not in html_text


def test_report_dashboard_shows_reason_when_no_constraint(workspace, capsys):
    """制約候補が無く予測を試みなかった時も、cli 側の具体的な理由が載る。"""
    tmp_path, cfg = workspace
    (tmp_path / "inbox" / "a.md").unlink()  # 未完了が 0 件 → 制約候補なし
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])
    assert main(["report", "--config", str(cfg)]) == 0
    html_text = (tmp_path / ".toc" / "dashboard.html").read_text(encoding="utf-8")
    assert "予測不能: 制約候補が特定できません" in html_text
    assert "理由不明" not in html_text


def test_forecast_payload_rejects_unavailable_without_reason(monkeypatch):
    """予測関数が理由なしで None を返したら、空の理由で黙って進めず例外にする。"""
    from datetime import datetime, timezone

    import toc_engine.cli as cli
    from toc_engine.model import Snapshot, Stage, WorkItem

    snap = Snapshot(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        (Stage("s:inbox", 0), Stage("s:done", 1, terminal=True)),
        (WorkItem("i1", "i1", "s:inbox", "s"),),
    )
    monkeypatch.setattr(cli, "forecast_periods_to_clear", lambda *a, **k: (None, None))
    with pytest.raises(ValueError):
        cli._forecast_payload([snap], "s:inbox")


def test_review_reports_forecast_unavailable_with_reason(workspace, capsys):
    tmp_path, cfg = workspace
    _init_goal(cfg)
    main(["snapshot", "--config", str(cfg)])  # snapshot 1 件だけでは予測不能
    capsys.readouterr()
    rc = main(["review", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "予測不能" in out
    review = json.loads((tmp_path / ".toc" / "review.json").read_text(encoding="utf-8"))
    assert review["forecast"]["available"] is False
    assert review["forecast"]["reason"]
