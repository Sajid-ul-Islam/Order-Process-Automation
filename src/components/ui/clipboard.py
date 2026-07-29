"""Copy-to-clipboard button powered by a small JS snippet."""

from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v1 as components


def render_copy_button(text: str, label: str = "Copy Data") -> None:
    """Render a JS-powered copy-to-clipboard button.

    The *text* is expected to be a tab-separated table string that can be
    pasted directly into Excel or Google Sheets.

    Args:
        text: The text content to copy (typically TSV-formatted table data).
        label: Button label displayed to the user.
    """
    escaped = html.escape(text).replace("\n", "\\n").replace("\t", "\\t")

    js_html = f"""
    <div style="text-align:right; margin:2px 0 6px 0;">
      <button onclick="copyData()" style="
          background:#475569; color:#fff; border:none; border-radius:6px;
          padding:5px 14px; font-size:12px; font-weight:500; cursor:pointer;">
          {html.escape(label)}
      </button>
      <span id="copy-status" style="font-size:11px; color:#10b981; margin-left:8px;"></span>
    </div>
    <script>
    function copyData() {{
      const text = "{escaped}";
      navigator.clipboard.writeText(text).then(function() {{
        document.getElementById('copy-status').innerText = 'Copied!';
        setTimeout(function() {{ document.getElementById('copy-status').innerText = ''; }}, 2000);
      }}).catch(function() {{
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        document.getElementById('copy-status').innerText = 'Copied!';
        setTimeout(function() {{ document.getElementById('copy-status').innerText = ''; }}, 2000);
      }});
    }}
    </script>
    """
    components.html(js_html, height=36)
