from __future__ import annotations

from pathlib import Path

import pytest

from robot.realtime_config import ConfigError, RealtimeConfig


REQUIRED = {
    "VOLC_HARDWARE_INSTANCE_ID": "instance",
    "VOLC_HARDWARE_PRODUCT_KEY": "product",
    "VOLC_HARDWARE_PRODUCT_SECRET": "0123456789abcdef-secret",
    "VOLC_HARDWARE_BOT_ID": "bot",
    "VOLC_HARDWARE_DEVICE_ID": "reachy-mini-01",
}


def set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)


def test_realtime_config_loads_required_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required(monkeypatch)

    config = RealtimeConfig.from_env()

    assert config.instance_id == "instance"
    assert config.product_key == "product"
    assert config.product_secret == "0123456789abcdef-secret"
    assert config.bot_id == "bot"
    assert config.device_name == "reachy-mini-01"
    assert config.hardware_id == "reachy-mini-01"
    assert config.cache_path == Path("cache/volcengine_device.json")


def test_realtime_config_accepts_hardware_id_and_cache_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv("VOLC_HARDWARE_HARDWARE_ID", "reachy-serial-123")
    monkeypatch.setenv(
        "VOLC_HARDWARE_DEVICE_CACHE",
        "private/device.json",
    )

    config = RealtimeConfig.from_env()

    assert config.hardware_id == "reachy-serial-123"
    assert config.cache_path == Path("private/device.json")


def test_realtime_config_reports_all_missing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigError) as error:
        RealtimeConfig.from_env()

    message = str(error.value)
    for name in REQUIRED:
        assert name in message


def test_realtime_config_rejects_short_product_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv("VOLC_HARDWARE_PRODUCT_SECRET", "short")

    with pytest.raises(ConfigError, match="至少需要 16 字节"):
        RealtimeConfig.from_env()
