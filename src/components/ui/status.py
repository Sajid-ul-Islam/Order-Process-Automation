import streamlit as st


def render_status_toggle(label: str, status_type: str = "info", help_text: str = ""):
    """Renders a status indicator with a color-coded dot."""
    colors = {
        "success": "#15803d",
        "warning": "#b45309",
        "error": "#b91c1c",
        "info": "#1d4ed8",
    }
    color = colors.get(status_type, colors["info"])
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 8px; margin: 10px 0;">
            <div style="width: 10px; height: 10px; border-radius: 50%; background-color: {color};box-shadow: 0 0 6px {color}80;"></div>
            <div style="font-weight: 600; font-size: 0.9rem;">{label}</div>
            {f'<div style="font-size: 0.8rem; color: #64748b;">• {help_text}</div>' if help_text else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
