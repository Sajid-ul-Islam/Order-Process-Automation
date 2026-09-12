"""Unit tests for Streamlit custom bi-directional components."""

import os
from src.components.custom.chip_filter import _chip_filter_component


def test_custom_component_declared():
    assert _chip_filter_component is not None
    frontend_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "components",
        "custom",
        "chip_filter",
        "frontend",
    )
    assert os.path.isdir(frontend_dir)
    assert os.path.isfile(os.path.join(frontend_dir, "index.html"))


def test_chip_filter_frontend_contains_streamlit_protocol():
    frontend_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "components",
        "custom",
        "chip_filter",
        "frontend",
        "index.html",
    )
    with open(frontend_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert "streamlit:componentReady" in html_content
    assert "streamlit:setComponentValue" in html_content
    assert "streamlit:setFrameHeight" in html_content
    assert "streamlit:render" in html_content


def test_spark_metric_declared():
    from src.components.custom.spark_metric import _spark_metric_component

    assert _spark_metric_component is not None
    frontend_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "components",
        "custom",
        "spark_metric",
        "frontend",
    )
    assert os.path.isdir(frontend_dir)
    assert os.path.isfile(os.path.join(frontend_dir, "index.html"))


def test_spark_metric_frontend_contains_streamlit_protocol():
    frontend_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "components",
        "custom",
        "spark_metric",
        "frontend",
        "index.html",
    )
    with open(frontend_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert "streamlit:componentReady" in html_content
    assert "streamlit:setFrameHeight" in html_content
    assert "streamlit:render" in html_content
