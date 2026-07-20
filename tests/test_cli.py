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
