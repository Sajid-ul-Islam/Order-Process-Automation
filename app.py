import streamlit as st

st.set_page_config(
    page_title="DEEN OPS Terminal",
    page_icon="AH",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.app_bootstrap import run_app  # noqa: E402

try:
    run_app()
except Exception as exc:
    from src.utils.logging import log_error

    log_error(exc, context="App Bootstrap")
    st.error(
        "Application failed to render. Check 'More Tools -> System Logs' for details."
    )
    st.code(str(exc))
