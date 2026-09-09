"""Narrow Streamlit runtime adapter for non-presentation layers.

Processing and service modules use these small hooks instead of importing the
UI framework directly. This keeps framework access explicit and provides one
seam for tests or a future non-Streamlit runtime.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

import streamlit as _st


def cache_data(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    return _st.cache_data(*args, **kwargs)


def get_session_state() -> Any:
    return _st.session_state


def get_secret(key: str, default: Any = None) -> Any:
    try:
        return _st.secrets.get(key, default)
    except Exception:
        return default


def show_error(message: str) -> None:
    _st.error(message)


@contextmanager
def spinner(message: str) -> Iterator[None]:
    with _st.spinner(message):
        yield


def attach_script_run_context(thread: Any, context: Any = None) -> None:
    """Attach Streamlit's runtime context when supported by this version."""
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx
    except ImportError:
        try:
            from streamlit.runtime.scriptrunner_utils import add_script_run_ctx
        except ImportError:
            return
    if context is None:
        add_script_run_ctx(thread)
    else:
        add_script_run_ctx(thread, context)


def get_script_run_context() -> Any:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except ImportError:
        return None
    return get_script_run_ctx()


class _RuntimeAPI:
    """Compatibility surface limited to the runtime features services require."""

    cache_data = staticmethod(cache_data)
    spinner = staticmethod(spinner)
    error = staticmethod(show_error)

    @property
    def session_state(self) -> Any:
        return get_session_state()

    @property
    def secrets(self) -> Any:
        return _st.secrets


runtime = _RuntimeAPI()
