"""history.py のテスト: JSONL 追記・読出・壊れ行スキップ。"""
import logging
from datetime import datetime, timezone

from toc_engine.history import append_note, append_snapshot, read_history
from toc_engine.model import Note, Snapshot, Stage, WorkItem


def _snap():
    return Snapshot(
        taken_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        stages=(Stage("a:inbox", 0, False), Stage("a:done", 1, True)),
        items=(WorkItem("a:inbox:x.md", "x", "a:inbox", "a", 2.5),),
    )


def test_snapshot_roundtrip(tmp_path):
    path = tmp_path / "history.jsonl"
    snap = _snap()
    append_snapshot(path, snap)
    snapshots, notes = read_history(path)
    assert snapshots == [snap]
    assert notes == []


def test_note_roundtrip(tmp_path):
    path = tmp_path / "history.jsonl"
    note = Note(
        at=datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc),
        text="レビュー工程が辛い",
        constraint="a:inbox",
    )
    append_note(path, note)
    _, notes = read_history(path)
    assert notes == [note]


def test_broken_line_is_skipped_with_warning(tmp_path, caplog):
    path = tmp_path / "history.jsonl"
    append_snapshot(path, _snap())
    with path.open("a", encoding="utf-8") as f:
        f.write("{broken json\n")
    append_note(path, Note(datetime(2026, 7, 21, tzinfo=timezone.utc), "ok", None))
    with caplog.at_level(logging.WARNING):
        snapshots, notes = read_history(path)
    assert len(snapshots) == 1  # 壊れ行の前後は読める
    assert len(notes) == 1
    assert "スキップ" in caplog.text


def test_read_missing_file_returns_empty(tmp_path):
    assert read_history(tmp_path / "none.jsonl") == ([], [])
