"""steps.py のテスト: validate_step / CycleEntry の history 経由ラウンドトリップ。"""
import logging
from datetime import datetime, timezone

import pytest

from toc_engine.history import append_cycle, append_note, append_snapshot, read_history
from toc_engine.model import Note, Snapshot, Stage, WorkItem
from toc_engine.steps import STEPS, CycleEntry, validate_step


def _snap():
    return Snapshot(
        taken_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        stages=(Stage("a:inbox", 0, False), Stage("a:done", 1, True)),
        items=(WorkItem("a:inbox:x.md", "x", "a:inbox", "a", 2.5),),
    )


def _cycle():
    return CycleEntry(
        at=datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc),
        step="exploit",
        constraint="a:inbox",
        action="レビュー担当を1人専任にした",
    )


class TestValidateStep:
    @pytest.mark.parametrize("step", STEPS)
    def test_valid_step_passes_through(self, step):
        assert validate_step(step) == step

    def test_uppercase_mixed_is_normalized(self):
        assert validate_step("Exploit") == "exploit"

    def test_unknown_step_raises_with_valid_list_in_message(self):
        with pytest.raises(ValueError) as exc_info:
            validate_step("mystery")
        message = str(exc_info.value)
        for step in STEPS:
            assert step in message


class TestAppendCycleRoundtrip:
    def test_cycle_roundtrip_preserves_aware_datetime(self, tmp_path):
        path = tmp_path / "history.jsonl"
        entry = _cycle()
        append_cycle(path, entry)
        _, _, cycles = read_history(path)
        assert cycles == [entry]
        assert cycles[0].at.tzinfo is not None

    def test_mixed_types_are_sorted_into_respective_lists(self, tmp_path, caplog):
        path = tmp_path / "history.jsonl"
        snap = _snap()
        note = Note(
            at=datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc),
            text="レビュー工程が辛い",
            constraint="a:inbox",
        )
        cycle = _cycle()
        append_snapshot(path, snap)
        append_note(path, note)
        append_cycle(path, cycle)
        with caplog.at_level(logging.WARNING):
            snapshots, notes, cycles = read_history(path)
        assert snapshots == [snap]
        assert notes == [note]
        assert cycles == [cycle]
