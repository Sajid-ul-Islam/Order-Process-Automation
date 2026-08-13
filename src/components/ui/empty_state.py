import streamlit as st


def render_empty_state(
    emoji: str = "📂",
    title: str = "No data available",
    description: str = "",
    action_label: str | None = None,
    action_key: str | None = None,
    on_action=None,
):
    """Visual empty state with optional CTA button."""
    with st.container(border=True):
        st.markdown(
            f"""<div style="display: flex; flex-direction: column; align-items: center; justify-content: center;
                padding: 40px 20px; text-align: center;">
                <div style="font-size: 3rem; margin-bottom: 12px; opacity: 0.6;">{
                emoji
            }</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-color, #0f172a); margin-bottom: 6px;">{
                title
            }</div>
                {
                f'<div style="font-size: 0.85rem; color: var(--text-muted, #475569); margin-bottom: 16px;">{description}</div>'
                if description
                else ""
            }
            </div>""",
            unsafe_allow_html=True,
        )
        if action_label and action_key:
            if st.button(action_label, key=action_key, use_container_width=True):
                if on_action:
                    on_action()
