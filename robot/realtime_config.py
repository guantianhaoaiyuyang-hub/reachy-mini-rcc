from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """实时语音配置缺失或不合法。"""


@dataclass(frozen=True)
class RealtimeConfig:
    instance_id: str
    product_key: str
    product_secret: str
    bot_id: str
    device_name: str
    hardware_id: str
    cache_path: Path

    @classmethod
    def from_env(cls) -> "RealtimeConfig":
        names = {
            "instance_id": "VOLC_HARDWARE_INSTANCE_ID",
            "product_key": "VOLC_HARDWARE_PRODUCT_KEY",
            "product_secret": "VOLC_HARDWARE_PRODUCT_SECRET",
            "bot_id": "VOLC_HARDWARE_BOT_ID",
            "device_name": "VOLC_HARDWARE_DEVICE_ID",
        }
        values = {
            field: os.getenv(name, "").strip()
            for field, name in names.items()
        }
        missing = [
            names[field]
            for field, value in values.items()
            if not value
        ]
        if missing:
            raise ConfigError(
                "缺少实时语音配置：" + "、".join(missing)
            )

        product_secret = values["product_secret"]
        if len(product_secret.encode("utf-8")) < 16:
            raise ConfigError(
                "VOLC_HARDWARE_PRODUCT_SECRET 至少需要 16 字节。"
            )

        device_name = values["device_name"]
        hardware_id = os.getenv(
            "VOLC_HARDWARE_HARDWARE_ID",
            device_name,
        ).strip()
        cache_path = Path(
            os.getenv(
                "VOLC_HARDWARE_DEVICE_CACHE",
                "cache/volcengine_device.json",
            ).strip()
        )

        return cls(
            instance_id=values["instance_id"],
            product_key=values["product_key"],
            product_secret=product_secret,
            bot_id=values["bot_id"],
            device_name=device_name,
            hardware_id=hardware_id or device_name,
            cache_path=cache_path,
        )
