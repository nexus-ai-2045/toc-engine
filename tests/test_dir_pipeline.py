"""dir_pipeline アダプタと take_snapshot のテスト。"""
import logging

from toc_engine.adapters.base import take_snapshot
from toc_engine.adapters.dir_pipeline import DirPipelineAdapter


def _make_adapter(tmp_path, with_files=True):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "done").mkdir()
    if with_files:
        (tmp_path / "inbox" / "a.md").write_text("x", encoding="utf-8")
        (tmp_path / "inbox" / "b.md").write_text("y", encoding="utf-8")
        (tmp_path / "done" / "c.md").write_text("z", encoding="utf-8")
    return DirPipelineAdapter(
        "articles",
        [
            {"name": "inbox", "path": str(tmp_path / "inbox"), "terminal": False},
            {"name": "done", "path": str(tmp_path / "done"), "terminal": True},
        ],
    )


def test_scan_finds_files_with_age(tmp_path):
    adapter = _make_adapter(tmp_path)
    items = adapter.scan()
    assert len(items) == 3
    inbox_items = [i for i in items if i.stage == "inbox"]
    assert {i.title for i in inbox_items} == {"a", "b"}
    # mtime は今なので age はほぼ 0（1日未満）
    assert all(0.0 <= i.age_days < 1.0 for i in items)


def test_scan_missing_dir_warns_and_skips(tmp_path, caplog):
    adapter = DirPipelineAdapter(
        "x", [{"name": "ghost", "path": str(tmp_path / "nope"), "terminal": False}]
    )
    with caplog.at_level(logging.WARNING):
        items = adapter.scan()
    assert items == []
    assert "nope" in caplog.text  # 黙殺しない


def test_scan_ignores_hidden_and_dirs(tmp_path):
    adapter = _make_adapter(tmp_path, with_files=False)
    (tmp_path / "inbox" / ".hidden").write_text("h", encoding="utf-8")
    (tmp_path / "inbox" / "subdir").mkdir()
    assert adapter.scan() == []


def test_take_snapshot_qualifies_stage_names(tmp_path):
    adapter = _make_adapter(tmp_path)
    snap = take_snapshot([adapter])
    assert [s.name for s in snap.stages] == ["articles:inbox", "articles:done"]
    assert snap.stages[1].terminal is True
    assert all(i.stage in {"articles:inbox", "articles:done"} for i in snap.items)
    assert snap.taken_at.tzinfo is not None  # aware datetime
