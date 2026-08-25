"""Chart.js-powered lightweight charts rendered via Streamlit HTML components.

Chart.js (~200KB, canvas-based) is used here for SMALL SUMMARY VISUALS —
donuts and horizontal bar strips — where loading a full Plotly figure is
disproportionately heavy. Interactive drilldown charts stay on Plotly,
which has native Streamlit selection support.

All functions accept plain Python lists/dicts and serialize them into the
generated HTML; no JS build step or npm dependency is required (Chart.js
loads from CDN).
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


def _to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def render_donut_chartjs(
    labels: list[str],
    values: list[float],
    colors: list[str],
    height: int = 260,
    center_text: str = "",
    key: str = "donut",
) -> None:
    """Render a compact donut chart with an optional centered total label.

    Appropriate for category-share summaries and status breakdowns where the
    viewer reads proportions at a glance rather than interacting.
    """
    if not labels or not values:
        st_empty = "<div style='color:#9ca3af;font-size:0.85rem;'>No data</div>"
        components.html(st_empty, height=40)
        return

    html = """
    <div style="position:relative;width:100%;height:{H}px;">
      <canvas id="cjs-{KEY}"></canvas>
      <div style="position:absolute;inset:0;display:flex;align-items:center;
                  justify-content:center;pointer-events:none;">
        <div style="text-align:center;font-weight:700;">{CENTER}</div>
      </div>
    </div>
    <script src="{CDN}"></script>
    <script>
    (function() {
      var ctx = document.getElementById('cjs-{KEY}');
      if (!ctx || !window.Chart) return;
      new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: {LABELS},
          datasets: [{
            data: {VALUES},
            backgroundColor: {COLORS},
            borderWidth: 2,
            borderColor: 'rgba(0,0,0,0.15)',
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '68%',
          plugins: {
            legend: { position: 'right', labels: { boxWidth: 10, font: { size: 11 } } },
            tooltip: { callbacks: {
              label: function(c) {
                var total = c.dataset.data.reduce(function(a,b){return a+b;},0);
                var pct = total ? Math.round(c.parsed/total*100) : 0;
                return c.label + ': ' + c.parsed.toLocaleString() + ' (' + pct + '%)';
              }
            }},
          }
        }
      });
    })();
    </script>
    """.replace(
        "{H}", str(height)
    )
    html = (
        html.replace("{KEY}", key)
        .replace("{CENTER}", center_text)
        .replace("{CDN}", _CHARTJS_CDN)
        .replace("{LABELS}", _to_json(labels))
        .replace("{VALUES}", _to_json(values))
        .replace("{COLORS}", _to_json(colors))
    )
    components.html(html, height=height + 10, scrolling=False)


def render_hbar_chartjs(
    labels: list[str],
    values: list[float],
    color: str = "#10b981",
    height: int = 300,
    prefix: str = "",
    key: str = "hbar",
) -> None:
    """Render a compact horizontal bar ranking (e.g. top products).

    Lighter than a Plotly figure for simple ranked lists; no interactivity
    beyond tooltips, which is all these views need.
    """
    if not labels or not values:
        components.html(
            "<div style='color:#9ca3af;font-size:0.85rem;'>No data</div>", height=40
        )
        return

    html = """
    <canvas id="cjs-{KEY}" style="width:100%;"></canvas>
    <script src="{CDN}"></script>
    <script>
    (function() {
      var ctx = document.getElementById('cjs-{KEY}');
      if (!ctx || !window.Chart) return;
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: {LABELS},
          datasets: [{
            data: {VALUES},
            backgroundColor: '{COLOR}',
            borderRadius: 4,
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              label: function(c) { return '{PREFIX}' + c.parsed.x.toLocaleString(); }
            }},
          },
          scales: { x: { grid: { color: 'rgba(128,128,128,0.12)' } },
                    y: { grid: { display: false } } }
        }
      });
    })();
    </script>
    """.replace(
        "{KEY}", key
    )
    html = (
        html.replace("{CDN}", _CHARTJS_CDN)
        .replace("{LABELS}", _to_json(labels))
        .replace("{VALUES}", _to_json(values))
        .replace("{COLOR}", color)
        .replace("{PREFIX}", prefix)
    )
    components.html(html, height=height, scrolling=False)
