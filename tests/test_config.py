"""config.py のテスト。"""
import pytest

from toc_engine.adapters.dir_pipeline import DirPipelineAdapter
from toc_engine.adapters.md_tasks import MdTasksAdapter
from toc_engine.config import build_adapters, load_config

_SAMPLE = """
[core]
state_dir = ".toc"
max_interval_days = 2

[[source]]
type = "dir_pipeline"
name = "articles"
stages = [
  { name = "inbox", path = "content/inbox" },
  { name = "published", path = "published", terminal = true },
]

[[source]]
type = "md_tasks"
name = "todo"
path = "tasks/todo.md"
"""


def test_load_config(tmp_path):
    cfg_path = tmp_path / "config.local.toml"
    cfg_path.write_text(_SAMPLE, encoding="utf-8")
    config = load_config(cfg_path)
    assert config.state_dir == (tmp_path / ".toc").resolve()
    assert config.max_interval_days == 2.0
    assert len(config.sources) == 2


def test_build_adapters_resolves_relative_paths(tmp_path):
    cfg_path = tmp_path / "config.local.toml"
    cfg_path.write_text(_SAMPLE, encoding="utf-8")
    config = load_config(cfg_path)
    adapters = build_adapters(config, base=tmp_path)
    assert isinstance(adapters[0], DirPipelineAdapter)
    assert isinstance(adapters[1], MdTasksAdapter)
    # 相対パスが base 起点で解決されている
    assert str(tmp_path) in adapters[0]._specs[0]["path"]


def test_unknown_source_type_raises(tmp_path):
    cfg_path = tmp_path / "config.local.toml"
    cfg_path.write_text(
        '[[source]]\ntype = "mystery"\nname = "x"\n', encoding="utf-8"
    )
    config = load_config(cfg_path)
    with pytest.raises(ValueError, match="mystery"):
        build_adapters(config, base=tmp_path)


def test_example_config_is_loadable():
    # 公開用サンプルが常に読める状態を保証する
    from pathlib import Path

    example = Path(__file__).parent.parent / "config.example.toml"
    config = load_config(example)
    assert config.sources  # 少なくとも 1 ソース定義がある
