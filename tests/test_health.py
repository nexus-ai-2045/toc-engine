"""health.py のユニットテスト: throughput_health() のゾーン判定。"""
from toc_engine.health import Health, throughput_health

_TARGET_7DAYS = [
    ("2026-07-13T00:00:00+00:00", 0),
    ("2026-07-20T00:00:00+00:00", 3),
]


def test_no_target_is_unknown():
    result = throughput_health(_TARGET_7DAYS, None)
    assert result == Health("unknown", None, "目標未設定", target_set=False)
    assert result.target_set is False


def test_single_sample_is_unknown():
    result = throughput_health([("2026-07-20T00:00:00+00:00", 1)], 3.0)
    assert result == Health("unknown", None, "データ不足")


def test_short_span_is_unknown_with_label():
    short = [
        ("2026-07-20T10:00:00+00:00", 1),
        ("2026-07-20T10:05:00+00:00", 3),
    ]
    result = throughput_health(short, 3.0)
    assert result.zone == "unknown"
    assert result.rate_per_week is None
    assert result.label == "計測期間が短い"


def test_span_7days_increment_3_target_3_is_green():
    result = throughput_health(_TARGET_7DAYS, 3.0)
    assert result.zone == "green"
    assert result.label == "順調"
    assert result.rate_per_week == 3.0


def test_span_7days_increment_2point2_target_3_is_yellow():
    # 0.7 倍境界: rate = 2.2 >= target(3.0) * 0.7 = 2.1 → yellow
    throughput = [
        ("2026-07-13T00:00:00+00:00", 0),
        ("2026-07-20T00:00:00+00:00", 2.2),
    ]
    result = throughput_health(throughput, 3.0)
    assert result.zone == "yellow"
    assert result.label == "注意"


def test_span_7days_increment_1_target_3_is_red():
    throughput = [
        ("2026-07-13T00:00:00+00:00", 0),
        ("2026-07-20T00:00:00+00:00", 1),
    ]
    result = throughput_health(throughput, 3.0)
    assert result.zone == "red"
    assert result.label == "危険"


def test_invalid_datetime_is_unknown_without_raising():
    invalid = [
        ("not-a-date", 0),
        ("2026-07-20T00:00:00+00:00", 3),
    ]
    result = throughput_health(invalid, 3.0)
    assert result == Health("unknown", None, "日時を解析できません")


def test_unparsable_datetime_is_logged(caplog):
    """日時解析失敗を黙殺せず warning に残す (運用者が原因を追えるように)。"""
    import logging

    with caplog.at_level(logging.WARNING):
        result = throughput_health([("not-a-date", 1), ("also-bad", 5)], 3.0)
    assert result.zone == "unknown"
    assert "not-a-date" in caplog.text
