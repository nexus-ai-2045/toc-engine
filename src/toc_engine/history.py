"""snapshot / note / cycle の JSONL 追記・読出。壊れた行は warn してスキップ。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from toc_engine.model import Note, Snapshot, Stage, WorkItem
from toc_engine.steps import CycleEntry, validate_step

logger = logging.getLogger(__name__)


def _snapshot_to_dict(snap: Snapshot) -> dict:
    return {
        "at": snap.taken_at.isoformat(),
        "stages": [
            {"name": s.name, "order": s.order, "terminal": s.terminal}
            for s in snap.stages
        ],
        "items": [
            {
                "id": i.item_id,
                "title": i.title,
                "stage": i.stage,
                "source": i.source,
                "age": i.age_days,
            }
            for i in snap.items
        ],
    }


def _snapshot_from_dict(d: dict) -> Snapshot:
    return Snapshot(
        taken_at=datetime.fromisoformat(d["at"]),
        stages=tuple(
            Stage(s["name"], s["order"], s["terminal"]) for s in d["stages"]
        ),
        items=tuple(
            WorkItem(i["id"], i["title"], i["stage"], i["source"], i.get("age"))
            for i in d["items"]
        ),
    )


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_snapshot(path: Path, snap: Snapshot) -> None:
    """snapshot を履歴に追記する。"""
    _append(path, {"type": "snapshot", **_snapshot_to_dict(snap)})


def append_note(path: Path, note: Note) -> None:
    """note を履歴に追記する。"""
    _append(
        path,
        {
            "type": "note",
            "at": note.at.isoformat(),
            "text": note.text,
            "constraint": note.constraint,
        },
    )


def append_cycle(path: Path, entry: CycleEntry) -> None:
    """Five Focusing Steps のサイクル記録を履歴に追記する。"""
    _append(
        path,
        {
            "type": "cycle",
            "at": entry.at.isoformat(),
            "step": entry.step,
            "constraint": entry.constraint,
            "action": entry.action,
        },
    )


def read_history(
    path: Path,
) -> tuple[list[Snapshot], list[Note], list[CycleEntry]]:
    """履歴を全読みする。壊れた行は warn してスキップ（読める行で継続）。"""
    snapshots: list[Snapshot] = []
    notes: list[Note] = []
    cycles: list[CycleEntry] = []
    if not path.exists():
        return snapshots, notes, cycles
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec["type"] == "snapshot":
                snapshots.append(_snapshot_from_dict(rec))
            elif rec["type"] == "note":
                notes.append(
                    Note(
                        at=datetime.fromisoformat(rec["at"]),
                        text=rec["text"],
                        constraint=rec.get("constraint"),
                    )
                )
            elif rec["type"] == "cycle":
                cycles.append(
                    CycleEntry(
                        at=datetime.fromisoformat(rec["at"]),
                        step=validate_step(rec["step"]),
                        constraint=rec.get("constraint", ""),
                        action=rec["action"],
                    )
                )
            else:
                logger.warning(
                    "history %d 行目: 未知の type %r をスキップ", lineno, rec["type"]
                )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning("history %d 行目を読めずスキップ: %s", lineno, e)
    return snapshots, notes, cycles
