from datetime import datetime

import streamlit as st

from src.config.constants import bd_now


def _get_sync_badge_html(sync_time: datetime | None) -> str:
    """Return an HTML/CSS/JS sync status badge that updates in real-time.

    Shows a colored dot + 'Last sync: Xs ago' that refreshes every second.
    Green  = synced within last 60s
    Yellow = synced within last 5 min
    Red    = synced more than 5 min ago (or never)
    """
    if sync_time is None:
        return (
            '<div style="display:inline-flex;align-items:center;gap:6px;'
            'font-size:0.75rem;color:rgba(255,255,255,0.6);font-weight:500;">'
            '<span style="width:8px;height:8px;border-radius:50%;background:#ef4444;'
            'box-shadow:0 0 6px rgba(239,68,68,0.6);"></span>'
            '<span id="sync-badge-text">Not synced</span></div>'
        )

    # Pass the sync timestamp as a data attribute for JS to read
    ts_ms = int(sync_time.timestamp() * 1000) if hasattr(sync_time, "timestamp") else 0
    return f"""<div style="display:inline-flex;align-items:center;gap:6px;"
          data-sync-ts="{ts_ms}" id="sync-badge-container">
  <span id="sync-badge-dot" style="width:8px;height:8px;border-radius:50%;
        background:#10b981;box-shadow:0 0 6px rgba(16,185,129,0.6);
        transition:background 0.4s ease,box-shadow 0.4s ease;"></span>
  <span id="sync-badge-text" style="font-size:0.75rem;color:rgba(255,255,255,0.6);
        font-weight:500;">Synced</span>
</div>
<script>
(function() {{
var container = document.getElementById('sync-badge-container');
if (!container) return;
if (window.__syncInterval) clearInterval(window.__syncInterval);
var ts = parseInt(container.getAttribute('data-sync-ts'), 10);
if (!ts) return;
function updateSync() {{
  var dot = document.getElementById('sync-badge-dot');
  var txt = document.getElementById('sync-badge-text');
  if (!dot || !txt) return;
  var elapsed = (Date.now() - ts) / 1000;
  var label, color, shadow;
  if (elapsed < 60) {{
    label = Math.round(elapsed) + 's ago';
    color = '#10b981'; shadow = 'rgba(16,185,129,0.6)';
  }} else if (elapsed < 300) {{
    label = Math.round(elapsed / 60) + 'm ago';
    color = '#f59e0b'; shadow = 'rgba(245,158,11,0.6)';
  }} else {{
    label = Math.round(elapsed / 60) + 'm ago';
    color = '#ef4444'; shadow = 'rgba(239,68,68,0.6)';
  }}
  dot.style.background = color;
  dot.style.boxShadow = '0 0 6px ' + shadow;
  txt.textContent = label;
}}
updateSync();
window.__syncInterval = setInterval(updateSync, 1000);
}})();
</script>"""


def get_clock_html():
    """Returns the compact, single-line JavaScript clock HTML string."""
    now_bd = bd_now()
    return f"""<div style="text-align: right; line-height: 1.5; color: white; font-family: sans-serif;">
<span id="header-clock-time" style="font-size: 1.05rem; font-weight: 700; letter-spacing: -0.3px;">{now_bd.strftime("%I:%M:%S %p")}</span>
<span style="color: rgba(255,255,255,0.4); margin: 0 10px; font-weight: 300;">|</span>
<span id="header-clock-date" style="font-size: 0.9rem; color: rgba(255,255,255,0.8); font-weight: 500;">{now_bd.strftime("%A, %B %d")}</span>
</div>
<script>
(function() {{
if (window.headerClockInterval) clearInterval(window.headerClockInterval);
function updateClock() {{
const timeEl = document.getElementById('header-clock-time');
const dateEl = document.getElementById('header-clock-date');
if (!timeEl) return;
const now = new Date();
const bdTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (6 * 3600000));
timeEl.innerHTML = bdTime.toLocaleTimeString('en-US', {{
hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
}});
if (dateEl) {{
dateEl.innerHTML = bdTime.toLocaleDateString('en-US', {{
weekday: 'long', month: 'long', day: '2-digit'
}});
}}
}}
updateClock();
window.headerClockInterval = setInterval(updateClock, 1000);
}})();
</script>"""


def render_dynamic_clock(sync_time=None):
    """Renders a compact JavaScript clock + live sync-status badge for the header."""
    col1, col2 = st.columns([1, 1])
    with col1:
        sync_badge = _get_sync_badge_html(sync_time)
        st.markdown(sync_badge, unsafe_allow_html=True)
    with col2:
        st.markdown(get_clock_html(), unsafe_allow_html=True)
