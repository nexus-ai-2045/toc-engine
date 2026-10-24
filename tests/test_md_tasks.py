"""md_tasks アダプタのテスト。"""
import logging

from toc_engine.adapters.md_tasks import MdTasksAdapter


def test_scan_parses_checkboxes(tmp_path):
    md = tmp_path / "todo.md"
    md.write_text(
        "# TODO\n"
        "- [ ] 記事Aを書く\n"
        "- [x] 記事Bを公開する\n"
        "* [X] 大文字Xも完了扱い\n"
        "  - [ ] インデント付きタスク\n"
        "- ただの箇条書きは無視\n",
        encoding="utf-8",
    )
    adapter = MdTasksAdapter("todo", str(md))
    items = adapter.scan()
    assert len(items) == 4
    by_stage = {"open": 0, "done": 0}
    for i in items:
        by_stage[i.stage] += 1
        assert i.age_days is None  # md からは滞留時間不明
    assert by_stage == {"open": 2, "done": 2}
    assert any(i.title == "記事Aを書く" for i in items)


def test_stages_open_then_done():
    adapter = MdTasksAdapter("todo", "dummy.md")
    stages = adapter.stages()
    assert [(s.name, s.terminal) for s in stages] == [("open", False), ("done", True)]


def test_missing_file_warns_and_returns_empty(tmp_path, caplog):
    adapter = MdTasksAdapter("todo", str(tmp_path / "nope.md"))
    with caplog.at_level(logging.WARNING):
        assert adapter.scan() == []
    assert "nope.md" in caplog.text
