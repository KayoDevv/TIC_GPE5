"""Tests for ml_layer.config."""

from __future__ import annotations

from ml_layer.config import Settings, get_config


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.kafka.topic_in == "file.requested"
    assert settings.kafka.topic_out == "ml_layer.result"
    assert settings.kafka.group_id == "ml-layer-worker"
    assert settings.kafka.bootstrap_servers == "localhost:9092"
    assert settings.model_path == "models/ml_model_pdf.onnx"


def test_get_config_is_cached() -> None:
    get_config.cache_clear()
    first = get_config()
    second = get_config()
    assert first is second
