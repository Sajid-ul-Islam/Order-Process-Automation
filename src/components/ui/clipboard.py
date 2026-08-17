"""Copy-to-clipboard button powered by a small JS snippet."""

from __future__ import annotations

import html
import json

import streamlit.components.v1 as components


def render_copy_button(text: str, label: str = "Copy Data") -> None:
    """Render a JS-powered copy-to-clipboard button.

    Args:
        text: The text content to copy.
        label: Button label displayed to the user.
    """
    safe_text = str(text or "")
    # Use json.dumps to safely convert string to a valid JavaScript literal,
    # preventing syntax errors from raw newlines, quotes, backslashes, or Windows \r\n.
    json_escaped_text = json.dumps(safe_text).replace("</", "<\\/")
    escaped_label = html.escape(label)

    js_html = f"""
    <div style="text-align:right; margin:2px 0 6px 0;">
      <button onclick="copyData()" style="
          background:#475569; color:#fff; border:none; border-radius:6px;
          padding:5px 14px; font-size:12px; font-weight:500; cursor:pointer;
          transition: background-color 0.2s ease;">
          {escaped_label}
      </button>
      <span id="copy-status" style="font-size:11px; margin-left:8px; font-weight:600;"></span>
    </div>
    <script>
    function copyData() {{
      const text = {json_escaped_text};

      function setStatus(msg, isErr) {{
        const statusEl = document.getElementById('copy-status');
        if (statusEl) {{
          statusEl.innerText = msg;
          statusEl.style.color = isErr ? '#ef4444' : '#10b981';
          setTimeout(function() {{ statusEl.innerText = ''; }}, 2500);
        }}
      }}

      // 1. Primary: navigator.clipboard API in current window
      if (navigator.clipboard && window.isSecureContext) {{
        navigator.clipboard.writeText(text).then(function() {{
          setStatus('Copied!', false);
        }}).catch(function() {{
          tryParentClipboard(text, setStatus);
        }});
      }} else {{
        tryParentClipboard(text, setStatus);
      }}
    }}

    function tryParentClipboard(text, setStatus) {{
      try {{
        if (window.parent && window.parent.navigator && window.parent.navigator.clipboard) {{
          window.parent.navigator.clipboard.writeText(text).then(function() {{
            setStatus('Copied!', false);
          }}).catch(function() {{
            execCopyFallback(text, setStatus);
          }});
          return;
        }}
      }} catch(e) {{}}
      execCopyFallback(text, setStatus);
    }}

    function execCopyFallback(text, setStatus) {{
      let ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.top = '0';
      ta.style.left = '0';
      ta.style.width = '2em';
      ta.style.height = '2em';
      ta.style.padding = '0';
      ta.style.border = 'none';
      ta.style.outline = 'none';
      ta.style.boxShadow = 'none';
      ta.style.background = 'transparent';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();

      let success = false;
      try {{
        success = document.execCommand('copy');
      }} catch (err) {{
        success = false;
      }}
      document.body.removeChild(ta);

      if (success) {{
        setStatus('Copied!', false);
      }} else {{
        try {{
          let pDoc = window.parent.document;
          let pTa = pDoc.createElement('textarea');
          pTa.value = text;
          pTa.style.position = 'fixed';
          pTa.style.opacity = '0';
          pDoc.body.appendChild(pTa);
          pTa.focus();
          pTa.select();
          let pSuccess = pDoc.execCommand('copy');
          pDoc.body.removeChild(pTa);
          if (pSuccess) {{
            setStatus('Copied!', false);
            return;
          }}
        }} catch(e) {{}}
        setStatus('Copy failed!', true);
      }}
    }}
    </script>
    """
    components.html(js_html, height=36)
