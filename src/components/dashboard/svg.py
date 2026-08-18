"""Pure SVG chart primitives (sparklines, dual trends, mini bar charts).

Extracted from dashboard_metrics.py so the metric renderers focus on layout
and data while chart generation stays reusable and unit-testable.
"""

from __future__ import annotations


def _generate_sparkline_svg(
    values: list[float],
    color: str = "#3b82f6",
    prefix: str = "",
    suffix: str = "",
    labels: list[str] | None = None,
) -> tuple[str, str]:
    """Generates an informative normalized SVG sparkline.

    Enhancements over a bare line:
      - 7-day area + smoothed line with peak and latest markers
      - dashed 7-day average baseline for at-a-glance context
      - day-of-week axis labels beneath the plot (pass `labels`)
      - current value labelled at the endpoint
      - badge showing 7D peak / avg AND today vs previous-day delta (▲/▼ %)

    Returns (svg_html_snippet, micro_badge_html_snippet).
    """
    if not values or len(values) < 2:  # A line needs at least 2 points to show a trend.
        return "", ""

    # Normalize values to fit the SVG coordinate system (top 24px reserved for plot,
    # bottom 10px for day labels).
    min_v, max_v = min(values), max(values)
    avg_v = sum(values) / len(values)
    latest_v = values[-1]
    prev_v = values[-2]
    rng = max_v - min_v if max_v != min_v else 1

    width = 100
    plot_h = 24
    label_h = 10
    height = plot_h + label_h
    step = width / (len(values) - 1)

    coords = []
    max_idx = 0
    for i, v in enumerate(values):
        x = i * step
        y = plot_h - ((v - min_v) / rng * (plot_h - 6)) - 3
        coords.append((x, y))
        if v == max_v:
            max_idx = i

    if len(coords) == 2:
        path_data = f"M {coords[0][0]:.1f},{coords[0][1]:.1f} L {coords[1][0]:.1f},{coords[1][1]:.1f}"
    else:
        path_data = f"M {coords[0][0]:.1f},{coords[0][1]:.1f}"
        for i in range(len(coords) - 1):
            p0 = coords[i]
            p1 = coords[i + 1]
            cx = (p0[0] + p1[0]) / 2
            path_data += (
                f" C {cx:.1f},{p0[1]:.1f} {cx:.1f},{p1[1]:.1f} {p1[0]:.1f},{p1[1]:.1f}"
            )

    area_data = path_data + f" L {width:.1f},{plot_h:.1f} L 0.0,{plot_h:.1f} Z"

    # 7-day average baseline (dashed) for context.
    avg_y = plot_h - ((avg_v - min_v) / rng * (plot_h - 6)) - 3
    avg_line = (
        f'<line x1="0" y1="{avg_y:.1f}" x2="{width:.1f}" y2="{avg_y:.1f}" '
        f'stroke="{color}" stroke-width="0.6" stroke-dasharray="2 2" opacity="0.45" />'
    )

    px, py = coords[max_idx]
    ex, ey = coords[-1]

    # Day labels beneath the plot.
    label_svg = ""
    if labels:
        n = len(labels)
        for i, lab in enumerate(labels):
            lx = (i * (width / (n - 1))) if n > 1 else width / 2
            label_svg += (
                f'<text x="{lx:.1f}" y="{height - 1:.1f}" font-size="4.2" '
                f'text-anchor="middle" fill="#9ca3af" font-family="monospace">{lab}</text>'
            )

    # Current value label near the endpoint.
    val_label = f"{prefix}{latest_v:,.0f}{suffix}"
    val_text_x = max(2.0, min(ex - 1, width - 2))
    val_text = (
        f'<text x="{val_text_x:.1f}" y="{max(4.0, ey - 2):.1f}" font-size="4.6" '
        f'text-anchor="end" fill="{color}" font-weight="700" '
        f'font-family="monospace">{val_label}</text>'
    )

    # Today vs previous-day delta.
    if prev_v and prev_v != 0:
        delta_pct = (latest_v - prev_v) / abs(prev_v) * 100.0
    else:
        delta_pct = 0.0
    arrow = "▲" if delta_pct >= 0 else "▼"
    delta_color = "#10b981" if delta_pct >= 0 else "#ef4444"

    tooltip_txt = (
        f"7-Day Trend: Peak {prefix}{max_v:,.0f}{suffix} | Avg {prefix}{avg_v:,.0f}{suffix} | "
        f"Today {prefix}{latest_v:,.0f}{suffix} ({arrow}{abs(delta_pct):.0f}% vs prev day)"
    )

    svg_raw = f"""<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none">
        <title>{tooltip_txt}</title>
        <path d="{area_data}" fill="{color}" fill-opacity="0.15" />
        <path d="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        {avg_line}
        <circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}" stroke="#ffffff" stroke-width="1.2" />
        <circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.5" fill="#ffffff" stroke="{color}" stroke-width="1.5" />
        {val_text}
        {label_svg}
    </svg>"""

    import base64

    b64_svg = base64.b64encode(svg_raw.encode("utf-8")).decode("utf-8")

    svg_html = f"""
    <div class="metric-sparkline" title="{tooltip_txt}" style="height:34px;">
        <img src="data:image/svg+xml;base64,{b64_svg}" style="width: 100%; height: 34px; display: block;" />
    </div>
    """

    badge_html = f"""<div class="metric-detail-row" style="color:var(--text-color, #000000); font-weight:700; opacity:1;">
        <span>🔥 7D Peak: <b>{prefix}{max_v:,.0f}{suffix}</b></span>
        <span>📊 7D Avg: <b>{prefix}{avg_v:,.0f}{suffix}</b></span>
        <span style="color:{delta_color};">Today {arrow}{abs(delta_pct):.0f}% vs prev</span>
    </div>"""

    return svg_html, badge_html


def _generate_mini_bar_chart_svg(
    new_values: list[float],
    ret_values: list[float],
    color1: str = "#a855f7",
    color2: str = "#f59e0b",
    suffix: str = "%",
) -> tuple[str, str]:
    """Generates a 7-day side-by-side dual mini bar SVG chart displaying New vs. Returning customer ratios."""
    if not new_values or len(new_values) < 2:
        return "", ""

    n = len(new_values)
    svg_width = 100.0
    svg_height = 30.0
    single_bar_w = 4.8
    pair_inner_gap = 1.0
    day_gap = 3.5

    pair_w = 2 * single_bar_w + pair_inner_gap
    total_w = n * pair_w + (n - 1) * day_gap
    start_x = (svg_width - total_w) / 2.0
    max_h = 24.0

    bars_svg = []
    for i in range(n):
        x_pair = start_x + i * (pair_w + day_gap)
        x_new = x_pair
        x_ret = x_pair + single_bar_w + pair_inner_gap

        val_new = new_values[i]
        val_ret = ret_values[i]
        tot = val_new + val_ret

        pct_new = (
            (val_new / tot * 100.0) if tot > 0 else (val_new if suffix == "%" else 0.0)
        )
        pct_ret = (
            (val_ret / tot * 100.0) if tot > 0 else (val_ret if suffix == "%" else 0.0)
        )

        h_new = (pct_new / 100.0) * max_h if (pct_new > 0 or tot > 0) else 2.0
        h_ret = (pct_ret / 100.0) * max_h if (pct_ret > 0 or tot > 0) else 2.0

        y_bottom = svg_height - 2.0
        y_new = y_bottom - h_new
        y_ret = y_bottom - h_ret

        day_label = f"Day {i + 1}" if i < n - 1 else "Today"
        bar_tooltip = (
            f"{day_label}: 🆕 {pct_new:.0f}% New | 🔄 {pct_ret:.0f}% Returning"
        )

        bar_item = f"""<g title="{bar_tooltip}">
            <rect x="{x_new:.1f}" y="{y_new:.1f}" width="{single_bar_w:.1f}" height="{h_new:.1f}" fill="{color1}" rx="1" opacity="0.95"><title>{bar_tooltip}</title></rect>
            <rect x="{x_ret:.1f}" y="{y_ret:.1f}" width="{single_bar_w:.1f}" height="{h_ret:.1f}" fill="{color2}" rx="1" opacity="0.90"><title>{bar_tooltip}</title></rect>
        </g>"""
        bars_svg.append(bar_item)

    latest_new = new_values[-1]
    latest_ret = ret_values[-1]
    tot_l = latest_new + latest_ret
    p_new_l = (
        (latest_new / tot_l * 100.0)
        if tot_l > 0
        else (latest_new if suffix == "%" else 0.0)
    )
    p_ret_l = (
        (latest_ret / tot_l * 100.0)
        if tot_l > 0
        else (latest_ret if suffix == "%" else 0.0)
    )

    avg_new = sum(new_values) / n
    avg_ret = sum(ret_values) / n

    tooltip_txt = f"7-Day Customer Mix: Today {p_new_l:.0f}% New vs {p_ret_l:.0f}% Ret | 7D Avg: {avg_new:.0f}% New / {avg_ret:.0f}% Ret"
    bars_str = "\n".join(bars_svg)

    svg_raw = f"""<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 100 30" preserveAspectRatio="none">
        <title>{tooltip_txt}</title>
        {bars_str}
    </svg>"""

    import base64

    b64_svg = base64.b64encode(svg_raw.encode("utf-8")).decode("utf-8")

    svg_html = f"""
    <div class="metric-sparkline" title="{tooltip_txt}">
        <img src="data:image/svg+xml;base64,{b64_svg}" style="width: 100%; height: 30px; display: block;" />
    </div>
    """

    badge_html = f"""<div class="metric-detail-row" style="color:var(--text-color, #000000); font-weight:700; opacity:1;">
        <span style="color:{color1};">🆕 7D New: <b>{avg_new:.0f}% avg</b></span>
        <span style="color:{color2};">🔄 7D Ret: <b>{avg_ret:.0f}% avg</b></span>
    </div>"""

    return svg_html, badge_html
