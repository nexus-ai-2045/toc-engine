"""dashboard.py のスモークテスト: 期待要素の存在と自己完結性。"""
from toc_engine.dashboard import render_html

_REPORT = {
    "goal": {
        "statement": "記事を届ける",
        "throughput_unit": "公開された記事",
        "inventory": "",
        "operating_expense": "",
        "target_per_week": 2.0,
    },
    "taken_at": "2026-07-20T00:00:00+00:00",
    "throughput_total": 3,
    "stages": [
        {"name": "a:inbox", "terminal": False, "wip": 4, "avg_age_days": 6.0,
         "max_age_days": 12.0, "oldest": [{"title": "draft-x", "age_days": 12.0}]},
        {"name": "a:done", "terminal": True, "wip": 3, "avg_age_days": 1.0,
         "max_age_days": 1.0, "oldest": []},
    ],
    "constraints": [{"stage": "a:inbox", "score": 8.0, "evidence": ["WIP 4 件"]}],
    "recommendations": [{"step": "exploit", "text": "最古のアイテムから流す", "evidence": []}],
    "timeline": [{"at": "2026-07-19T00:00:00+00:00", "kind": "note", "text": "辛い"}],
}
_CFD = {"a:inbox": [2, 4], "a:done": [1, 3]}
_THROUGHPUT = [("2026-07-18T00:00:00+00:00", 1), ("2026-07-20T00:00:00+00:00", 3)]


def test_html_contains_required_sections():
    html_text = render_html(_REPORT, _CFD, _THROUGHPUT)
    assert "記事を届ける" in html_text        # Goal 最上部
    assert "a:inbox" in html_text            # 制約スポットライト
    assert "最古のアイテムから流す" in html_text  # 推奨打ち手
    assert "<svg" in html_text               # CFD が SVG で描かれる
    assert "draft-x" in html_text            # Aging WIP
    assert "辛い" in html_text               # タイムライン


def test_html_is_self_contained():
    html_text = render_html(_REPORT, _CFD, _THROUGHPUT)
    assert "http://" not in html_text and "https://" not in html_text  # 外部参照なし


def test_html_escapes_user_text():
    report = dict(_REPORT)
    report["goal"] = dict(_REPORT["goal"], statement="<script>alert(1)</script>")
    html_text = render_html(report, _CFD, _THROUGHPUT)
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text


def test_health_badge_only_with_target():
    no_target = dict(_REPORT)
    no_target["goal"] = dict(_REPORT["goal"], target_per_week=None)
    assert "health-badge" in render_html(_REPORT, _CFD, _THROUGHPUT)
    assert "health-badge" not in render_html(no_target, _CFD, _THROUGHPUT)


def test_health_badge_short_window_shows_no_rate():
    # 数分間隔の snapshot ではレート外挿せず「計測期間が短い」を出す
    short = [("2026-07-20T10:00:00+00:00", 1), ("2026-07-20T10:05:00+00:00", 3)]
    html_text = render_html(_REPORT, _CFD, short)
    assert "計測期間が短い" in html_text
    assert "順調" not in html_text


def test_badge_and_css_stay_in_sync_when_zone_unknown():
    """target 設定済み × zone=unknown でも、バッジと CSS が両方出ること。

    バッジ描画条件と CSS 同梱条件が別々の変数を見ていると、
    スタイルの当たらない裸のバッジが出る (レビューで実機再現された不具合)。
    """
    short = [("2026-07-20T10:00:00+00:00", 1), ("2026-07-20T10:05:00+00:00", 3)]
    html_text = render_html(_REPORT, _CFD, short)
    assert "計測期間が短い" in html_text          # バッジ本体は出る
    assert ".health-badge {" in html_text          # その CSS も必ず同梱される
    assert ".zone-unknown" in html_text            # unknown の配色定義もある


def test_no_badge_means_no_badge_css():
    """target なしならバッジも CSS も出ない (逆方向の同期)。"""
    no_target = dict(_REPORT)
    no_target["goal"] = dict(_REPORT["goal"], target_per_week=None)
    html_text = render_html(no_target, _CFD, _THROUGHPUT)
    assert "health-badge" not in html_text


def test_forecast_card_hidden_when_absent():
    html_text = render_html(_REPORT, _CFD, _THROUGHPUT)
    assert "完了予測" not in html_text


def test_forecast_card_shows_percentiles_when_available():
    report = dict(
        _REPORT,
        forecast={
            "available": True,
            "percentiles": {"50": 2.0, "70": 3.0, "85": 4.0},
            "trials": 1000,
            "samples_used": 6,
        },
    )
    html_text = render_html(report, _CFD, _THROUGHPUT)
    assert "完了予測" in html_text
    assert "50" in html_text and "70" in html_text and "85" in html_text


def test_forecast_card_shows_reason_when_unavailable():
    report = dict(
        _REPORT,
        forecast={"available": False, "reason": "計測期間が不足しています"},
    )
    html_text = render_html(report, _CFD, _THROUGHPUT)
    assert "予測不能" in html_text
    assert "計測期間が不足しています" in html_text


def test_signals_card_hidden_when_absent():
    html_text = render_html(_REPORT, _CFD, _THROUGHPUT)
    assert "レビュー招集シグナル" not in html_text


def test_signals_card_shown_when_present():
    report = dict(
        _REPORT,
        signals=[{"kind": "constraint_moved", "fired": True, "detail": "制約が a→b に変化"}],
    )
    html_text = render_html(report, _CFD, _THROUGHPUT)
    assert "レビュー招集シグナル" in html_text
    assert "制約が a→b に変化" in html_text
