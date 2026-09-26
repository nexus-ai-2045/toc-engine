"""自己完結 HTML ダッシュボード生成。外部依存なし（インライン SVG/CSS）。"""
from __future__ import annotations

import html as html_mod

from toc_engine.health import Health, throughput_health

_W, _H = 640, 240  # CFD 描画領域
_PALETTE = ["#4e79a7", "#f28e2b", "#76b7b2", "#e15759", "#59a14f",
            "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]

_CSS_BASE = """
body { font-family: sans-serif; margin: 1.5rem; background: #fafafa; color: #222; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; }
.card h2 { margin-top: 0; font-size: 1rem; }
.goal { background: #1a2b4a; color: #fff; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1rem; }
.goal h1 { margin: 0 0 .3rem; font-size: 1.3rem; }
.spotlight { border-left: 6px solid #e15759; }
.zone-green { background: #59a14f; } .zone-yellow { background: #edc948; color: #222; }
.zone-red { background: #e15759; }
.zone-unknown { background: #9aa0a6; }
.timeline { grid-column: 1 / -1; }
.timeline li { margin-bottom: .3rem; }
table { border-collapse: collapse; } td, th { padding: .2rem .6rem; border-bottom: 1px solid #eee; }
.muted { color: #888; font-size: .85rem; }
"""

_CSS_BADGE = ".health-badge { display: inline-block; padding: .2rem .8rem; border-radius: 1rem; color: #fff; font-weight: bold; }"


def _esc(value: object) -> str:
    return html_mod.escape(str(value))


def _goal_header(report: dict, throughput: list[tuple[str, int]], badge: str) -> str:
    """整形済みバッジ HTML を受け取る。出すか否かの判定はここでは行わない。"""
    g = report["goal"]
    spark = _sparkline(throughput)
    return (
        "<div class='goal'>"
        f"<h1>🎯 {_esc(g['statement'])}</h1>"
        f"<div>Throughput 累計: <b>{_esc(report['throughput_total'])}"
        f" {_esc(g['throughput_unit'])}</b> {spark} {badge}</div>"
        f"<div class='muted'>計測: {_esc(report['taken_at'])}</div>"
        "</div>"
    )


def _health_badge(health: Health, target_per_week: float | None) -> str:
    """バッジ HTML を返す。出さない場合は空文字。

    「バッジを出すか」の判定はこの関数だけが持つ。CSS 同梱の可否も
    戻り値が空かどうかで決めることで、条件が 2 箇所に分裂しないようにする。
    """
    if not health.target_set:
        return ""
    if health.rate_per_week is not None:
        detail = f": {health.rate_per_week:.1f}/週 (目標 {target_per_week:g})"
    else:
        detail = f" (目標 {target_per_week:g})"
    return f"<span class='health-badge zone-{health.zone}'>{health.label}{detail}</span>"


def _sparkline(throughput: list[tuple[str, int]]) -> str:
    if len(throughput) < 2:
        return ""
    values = [v for _, v in throughput]
    vmax = max(values) or 1
    w, h = 120, 24
    step = w / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{h - v / vmax * (h - 2):.1f}" for i, v in enumerate(values)
    )
    return (
        f"<svg width='{w}' height='{h}' style='vertical-align:middle'>"
        f"<polyline points='{points}' fill='none' stroke='#8ecae6' stroke-width='2'/></svg>"
    )


def _spotlight(report: dict) -> str:
    if not report["constraints"]:
        body = "<p>制約候補なし（データソース設定を確認）</p>"
    else:
        top = report["constraints"][0]
        evid = "".join(f"<li>{_esc(e)}</li>" for e in top["evidence"])
        recs = "".join(
            f"<li><b>[{_esc(r['step'])}]</b> {_esc(r['text'])}</li>"
            for r in report["recommendations"]
        )
        body = (
            f"<p>今の制約: <b>{_esc(top['stage'])}</b> (score {_esc(top['score'])})</p>"
            f"<ul>{evid}</ul><h3>推奨打ち手</h3><ul>{recs}</ul>"
        )
    return f"<div class='card spotlight'><h2>⛔ 制約スポットライト</h2>{body}</div>"


def _cfd_svg(cfd: dict[str, list[int]]) -> str:
    """累積フロー図。snapshot 2 点未満なら現在 WIP の棒グラフで代替。"""
    n_points = len(next(iter(cfd.values()))) if cfd else 0
    if n_points < 2:
        bars = "".join(
            f"<tr><td>{_esc(name)}</td><td>{'█' * series[-1] if series else ''}"
            f" {series[-1] if series else 0}</td></tr>"
            for name, series in cfd.items()
        )
        return (
            "<div class='card'><h2>CFD（累積フロー図）</h2>"
            "<p class='muted'>snapshot が 2 回以上貯まると面グラフになります</p>"
            f"<table>{bars}</table></div>"
        )
    names = list(cfd.keys())
    # 下から積み上げる: cumulative[i][t] = 下位 i 系列までの合計
    step = _W / (n_points - 1)
    cum = [0.0] * n_points
    total_max = max(
        sum(cfd[n][t] for n in names) for t in range(n_points)
    ) or 1
    polys = []
    for idx, name in enumerate(names):
        lower = list(cum)
        cum = [c + v for c, v in zip(cum, cfd[name])]
        top_pts = [
            f"{t * step:.1f},{_H - cum[t] / total_max * (_H - 10):.1f}"
            for t in range(n_points)
        ]
        bottom_pts = [
            f"{t * step:.1f},{_H - lower[t] / total_max * (_H - 10):.1f}"
            for t in reversed(range(n_points))
        ]
        color = _PALETTE[idx % len(_PALETTE)]
        polys.append(
            f"<polygon points='{' '.join(top_pts + bottom_pts)}'"
            f" fill='{color}' fill-opacity='0.75'><title>{_esc(name)}</title></polygon>"
        )
    legend = "".join(
        f"<span style='color:{_PALETTE[i % len(_PALETTE)]}'>■</span> {_esc(n)}&nbsp; "
        for i, n in enumerate(names)
    )
    return (
        "<div class='card'><h2>CFD（累積フロー図）</h2>"
        f"<svg width='{_W}' height='{_H}'>{''.join(polys)}</svg>"
        f"<div class='muted'>{legend}</div></div>"
    )


def _aging(report: dict) -> str:
    rows = []
    for s in report["stages"]:
        if s["terminal"]:
            continue
        for item in s["oldest"]:
            rows.append((item["age_days"] or 0.0, item["title"], s["name"]))
    rows.sort(reverse=True)
    body = "".join(
        f"<tr><td>{_esc(t)}</td><td>{_esc(st)}</td><td>{a:.1f} 日</td></tr>"
        for a, t, st in rows[:5]
    ) or "<tr><td colspan='3'>滞留アイテムなし</td></tr>"
    return (
        "<div class='card'><h2>Aging WIP（滞留 Top5）</h2>"
        f"<table><tr><th>アイテム</th><th>工程</th><th>滞留</th></tr>{body}</table></div>"
    )


def _forecast_card(report: dict) -> str:
    """予測カード。report に forecast キーが無ければ空文字（カード非表示）。"""
    payload = report.get("forecast")
    if payload is None:
        return ""
    if not payload.get("available"):
        body = f"<p>予測不能: {_esc(payload.get('reason', '理由不明'))}</p>"
    else:
        pct = payload["percentiles"]
        items = "".join(
            f"<li>{_esc(p)}%タイル: {_esc(pct[p])} 期間</li>" for p in sorted(pct, key=int)
        )
        body = (
            f"<ul>{items}</ul>"
            f"<p class='muted'>サンプル {_esc(payload['samples_used'])} 期間 /"
            f" 試行 {_esc(payload['trials'])} 回</p>"
        )
    return f"<div class='card'><h2>📈 完了予測</h2>{body}</div>"


def _signals_card(report: dict) -> str:
    """レビュー招集シグナルカード。report に signals キーが無ければ空文字（カード非表示）。"""
    signals = report.get("signals")
    if signals is None:
        return ""
    rows = "".join(
        f"<tr><td>{'🔔' if s['fired'] else ''}</td><td>{_esc(s['kind'])}</td>"
        f"<td>{_esc(s['detail'])}</td></tr>"
        for s in signals
    )
    return (
        "<div class='card'><h2>🔔 レビュー招集シグナル</h2>"
        f"<table><tr><th></th><th>種別</th><th>詳細</th></tr>{rows}</table></div>"
    )


def _timeline(report: dict) -> str:
    items = "".join(
        f"<li><span class='muted'>{_esc(e['at'])}</span>"
        f" <b>[{_esc(e['kind'])}]</b> {_esc(e['text'])}</li>"
        for e in report["timeline"][:30]
    )
    return (
        "<div class='card timeline'><h2>📓 タイムライン（実測 × 意見）</h2>"
        f"<ul>{items}</ul></div>"
    )


def render_html(
    report: dict, cfd: dict[str, list[int]], throughput: list[tuple[str, int]]
) -> str:
    """レポートを自己完結 HTML 1 ファイルにする。外部参照なし。"""
    # 健全性判定は health.py に一本化。バッジを出すかは _health_badge が唯一決め、
    # CSS 同梱はその結果から導出する (条件を 2 箇所に持たない)。
    health = throughput_health(throughput, report["goal"].get("target_per_week"))
    badge = _health_badge(health, report["goal"].get("target_per_week"))
    css = _CSS_BASE + (_CSS_BADGE if badge else "")

    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        "<title>toc-engine dashboard</title>"
        f"<style>{css}</style></head><body>"
        + _goal_header(report, throughput, badge)
        + "<div class='grid'>"
        + _spotlight(report)
        + _cfd_svg(cfd)
        + _forecast_card(report)
        + _signals_card(report)
        + _aging(report)
        + _timeline(report)
        + "</div></body></html>"
    )
