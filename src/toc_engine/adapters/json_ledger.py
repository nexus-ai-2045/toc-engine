"""JSON 台帳をデータ源とするアダプタ。1 レコード = 完了済み成果物 1 件。

成果物の実体が外部 (公開 URL 等) にあり、ローカルには台帳しか無い場合に使う。
ディレクトリ型 (dir_pipeline) が「ファイルの場所 = 工程」を前提とするのに対し、
こちらは「台帳に載っている = 完了した」を前提とする。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from toc_engine.adapters.base import Adapter
from toc_engine.model import Stage, WorkItem

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400.0
_TITLE_MAX = 80


class JsonLedgerAdapter(Adapter):
    """完了済み成果物の台帳 (JSON) を 1 つの terminal 工程として読む。"""

    def __init__(
        self,
        name: str,
        path: str,
        stage: str = "done",
        records_key: str = "",
        id_field: str = "id",
        title_field: str = "title",
        timestamp_field: str = "published_at",
        filter_field: str = "",
        filter_value: str = "",
    ) -> None:
        self.name = name
        self._path = Path(path)
        self._stage = stage
        self._records_key = records_key
        self._id_field = id_field
        self._title_field = title_field
        self._timestamp_field = timestamp_field
        self._filter_field = filter_field
        self._filter_value = filter_value

    def stages(self) -> list[Stage]:
        return [Stage(self._stage, 0, terminal=True)]

    def _load_records(self) -> list[dict]:
        """台帳を読む。読めない場合は warn して空を返す (全体を落とさない)。"""
        if not self._path.is_file():
            logger.warning("台帳が見つからずスキップ: %s", self._path)
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("台帳を読めずスキップ: %s (%s)", self._path, e)
            return []
        if self._records_key:
            data = data.get(self._records_key, []) if isinstance(data, dict) else []
        if not isinstance(data, list):
            logger.warning("台帳のレコードが配列ではありません: %s", self._path)
            return []
        records = [r for r in data if isinstance(r, dict)]
        if self._filter_field:
            # 台帳の一部だけが完了扱いの場合に絞る (例: visibility=public の repo だけ)
            records = [
                r for r in records
                if str(r.get(self._filter_field, "")) == self._filter_value
            ]
        return records

    def _age_days(self, record: dict, now: datetime) -> float | None:
        """公開時刻からの経過日数。欠損・解析不能なら None (滞留不明として残す)。"""
        raw = record.get(self._timestamp_field)
        if not raw:
            return None
        try:
            published = datetime.fromisoformat(str(raw))
        except ValueError:
            logger.warning("日時を解析できません: %r (%s)", raw, self._path)
            return None
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return max(0.0, (now - published).total_seconds() / _SECONDS_PER_DAY)

    def scan(self) -> list[WorkItem]:
        now = datetime.now(timezone.utc)
        items: list[WorkItem] = []
        for index, record in enumerate(self._load_records()):
            identifier = str(record.get(self._id_field) or f"{self.name}:{index}")
            title = str(record.get(self._title_field) or identifier)
            items.append(
                WorkItem(
                    item_id=f"{self.name}:{identifier}",
                    title=title[:_TITLE_MAX],
                    stage=self._stage,
                    source=self.name,
                    age_days=self._age_days(record, now),
                )
            )
        return items
