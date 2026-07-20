"""model.py のテスト: Goal 保存読込と guard。"""
import pytest

from toc_engine.model import Goal, GoalNotDefinedError, load_goal, save_goal


def test_goal_roundtrip(tmp_path):
    # 保存 → 読込で全フィールドが往復する
    goal = Goal(
        statement="読者に役立つ記事を継続的に届ける",
        throughput_unit="公開された記事",
        inventory="下書き・未処理タスク",
        operating_expense="作業時間",
        target_per_week=2.0,
    )
    path = tmp_path / "goal.toml"
    save_goal(goal, path)
    assert load_goal(path) == goal


def test_goal_roundtrip_without_target(tmp_path):
    # 目標値なしでも往復できる
    goal = Goal(statement="test", throughput_unit="件")
    path = tmp_path / "goal.toml"
    save_goal(goal, path)
    loaded = load_goal(path)
    assert loaded.target_per_week is None
    assert loaded.inventory == ""


def test_goal_statement_with_quotes(tmp_path):
    # 引用符を含む Goal 文もエスケープされて往復する
    goal = Goal(statement='"最高"の成果を出す', throughput_unit="件")
    path = tmp_path / "goal.toml"
    save_goal(goal, path)
    assert load_goal(path).statement == '"最高"の成果を出す'


def test_load_goal_missing_raises(tmp_path):
    # Goal 未定義なら GoalNotDefinedError（toc init へ誘導するメッセージ付き）
    with pytest.raises(GoalNotDefinedError, match="toc init"):
        load_goal(tmp_path / "goal.toml")
