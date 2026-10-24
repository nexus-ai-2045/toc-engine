"""json_ledger アダプタのテスト。"""
import json
import logging

from toc_engine.adapters.json_ledger import JsonLedgerAdapter

_RECORDS = [
    {"id": "n1", "title": "最初の記事", "published_at": "2026-06-05T18:00:00+09:00"},
    {"id": "n2", "title": "次の記事", "published_at": "2026-08-03T10:00:00+09:00"},
]


def _write(tmp_path, payload):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_scan_reads_flat_list(tmp_path):
    path = _write(tmp_path, _RECORDS)
    adapter = JsonLedgerAdapter(
        "notes", str(path), stage="published",
        id_field="id", title_field="title", timestamp_field="published_at",
    )
    items = adapter.scan()
    assert [i.title for i in items] == ["最初の記事", "次の記事"]
    assert all(i.stage == "published" for i in items)
    assert all(i.source == "notes" for i in items)
    # published_at からの経過日数が入る（古い記事ほど大きい）
    assert items[0].age_days > items[1].age_days


def test_stage_is_terminal():
    # 台帳のレコードは「完了済み」= スループットとして数える
    adapter = JsonLedgerAdapter("notes", "dummy.json", stage="published")
    stages = adapter.stages()
    assert [(s.name, s.terminal) for s in stages] == [("published", True)]


def test_scan_reads_nested_list_via_records_key(tmp_path):
    path = _write(tmp_path, {"schema": "v1", "notes": _RECORDS})
    adapter = JsonLedgerAdapter(
        "notes", str(path), stage="published", records_key="notes",
        id_field="id", title_field="title", timestamp_field="published_at",
    )
    assert len(adapter.scan()) == 2


def test_missing_file_warns_and_returns_empty(tmp_path, caplog):
    adapter = JsonLedgerAdapter("notes", str(tmp_path / "nope.json"), stage="published")
    with caplog.at_level(logging.WARNING):
        assert adapter.scan() == []
    assert "nope.json" in caplog.text


def test_broken_json_warns_and_returns_empty(tmp_path, caplog):
    path = tmp_path / "ledger.json"
    path.write_text("{broken", encoding="utf-8")
    adapter = JsonLedgerAdapter("notes", str(path), stage="published")
    with caplog.at_level(logging.WARNING):
        assert adapter.scan() == []
    assert "ledger.json" in caplog.text


def test_filter_keeps_only_matching_records(tmp_path):
    # 台帳の一部だけが「完了」の場合 (例: visibility=public の repo だけ)
    path = _write(tmp_path, [
        {"id": "r1", "title": "公開済み", "visibility": "public"},
        {"id": "r2", "title": "非公開", "visibility": "private"},
        {"id": "r3", "title": "ローカルのみ", "visibility": "local_only"},
    ])
    adapter = JsonLedgerAdapter(
        "repos", str(path), stage="published",
        id_field="id", title_field="title",
        filter_field="visibility", filter_value="public",
    )
    items = adapter.scan()
    assert [i.title for i in items] == ["公開済み"]


def test_no_filter_keeps_all_records(tmp_path):
    # filter 未指定なら全件 (既存挙動を壊さない)
    path = _write(tmp_path, [{"id": "a"}, {"id": "b"}])
    adapter = JsonLedgerAdapter("x", str(path), stage="done", id_field="id")
    assert len(adapter.scan()) == 2


def test_record_missing_timestamp_keeps_item_with_unknown_age(tmp_path):
    # 日時欠損は「滞留不明」として残す（黙って捨てない）
    path = _write(tmp_path, [{"id": "n1", "title": "日付なし"}])
    adapter = JsonLedgerAdapter(
        "notes", str(path), stage="published",
        id_field="id", title_field="title", timestamp_field="published_at",
    )
    items = adapter.scan()
    assert len(items) == 1
    assert items[0].age_days is None
