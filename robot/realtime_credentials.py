from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from robot.realtime_config import RealtimeConfig


DYNAMIC_REGISTER_URL = (
    "https://iot-cn-shanghai.iot.volces.com/"
    "2021-12-14/DynamicRegister"
    "?Action=DynamicRegister&Version=2021-12-14"
)
WEBSOCKET_URL = "wss://ai-gateway.vei.volces.com/v1/realtime"


class DeviceRegistrationError(RuntimeError):
    """设备动态注册失败。"""


def _hmac_base64(content: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def registration_signature(
    *,
    auth_type: int,
    device_name: str,
    random_num: int,
    product_key: str,
    timestamp_ms: int,
    product_secret: str,
) -> str:
    content = (
        f"auth_type={auth_type}"
        f"&device_name={device_name}"
        f"&random_num={random_num}"
        f"&product_key={product_key}"
        f"&timestamp={timestamp_ms}"
    )
    return _hmac_base64(content, product_secret)


def decrypt_device_secret(
    payload: str,
    product_secret: str,
) -> str:
    key = product_secret.encode("utf-8")[:16]
    if len(key) != 16:
        raise DeviceRegistrationError(
            "产品密钥不足 16 字节，无法解密设备密钥。"
        )
    try:
        encrypted = base64.b64decode(payload, validate=True)
        cipher = AES.new(key, AES.MODE_CBC, iv=key)
        decrypted = unpad(
            cipher.decrypt(encrypted),
            AES.block_size,
        )
        value = decrypted.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise DeviceRegistrationError(
            "设备注册返回的密钥无法解密。"
        ) from exc
    if not value:
        raise DeviceRegistrationError("设备注册返回了空密钥。")
    return value


def websocket_headers(
    config: RealtimeConfig,
    device_secret: str,
    *,
    random_num: int,
    timestamp: int,
) -> dict[str, str]:
    content = (
        "auth_type=1"
        f"&device_name={config.device_name}"
        f"&random_num={random_num}"
        f"&product_key={config.product_key}"
        f"&timestamp={timestamp}"
        f"&instance_id={config.instance_id}"
    )
    signature = _hmac_base64(content, device_secret)
    return {
        "X-Auth-Type": "1",
        "X-Product-Key": config.product_key,
        "X-Device-Name": config.device_name,
        "X-Random-Num": str(random_num),
        "X-Timestamp": str(timestamp),
        "X-Instance-Id": config.instance_id,
        "X-Signature": signature,
        "X-Hardware-Id": config.hardware_id,
    }


class DeviceCredentials:
    def __init__(
        self,
        config: RealtimeConfig,
        *,
        open_fn: Callable[..., Any] = urlopen,
        random_fn: Callable[[], int] = lambda: secrets.randbelow(
            2_147_483_647
        ),
        time_ms_fn: Callable[[], int] = lambda: time.time_ns()
        // 1_000_000,
    ) -> None:
        self.config = config
        self.open_fn = open_fn
        self.random_fn = random_fn
        self.time_ms_fn = time_ms_fn

    def ensure_registered(self) -> str:
        cached = self._read_matching_cache()
        if cached is not None:
            return cached

        device_secret = self._register()
        self._write_cache(device_secret)
        return device_secret

    def _read_matching_cache(self) -> str | None:
        path = self.config.cache_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None

        expected = {
            "instance_id": self.config.instance_id,
            "product_key": self.config.product_key,
            "device_name": self.config.device_name,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            return None
        secret = payload.get("device_secret")
        return secret if isinstance(secret, str) and secret else None

    def _register(self) -> str:
        random_num = self.random_fn()
        timestamp_ms = self.time_ms_fn()
        signature = registration_signature(
            auth_type=1,
            device_name=self.config.device_name,
            random_num=random_num,
            product_key=self.config.product_key,
            timestamp_ms=timestamp_ms,
            product_secret=self.config.product_secret,
        )
        body = json.dumps(
            {
                "InstanceID": self.config.instance_id,
                "product_key": self.config.product_key,
                "device_name": self.config.device_name,
                "random_num": random_num,
                "timestamp": timestamp_ms,
                "auth_type": 1,
                "signature": signature,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            DYNAMIC_REGISTER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self.open_fn(request, timeout=15.0) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise DeviceRegistrationError(
                f"设备动态注册请求失败：{type(exc).__name__}"
            ) from exc

        error = (
            result.get("ResponseMetadata", {}).get("Error")
            if isinstance(result, dict)
            else None
        )
        if error:
            code = error.get("Code", "unknown")
            message = error.get("Message", "未知错误")
            raise DeviceRegistrationError(
                f"设备动态注册失败：{code} {message}"
            )

        try:
            encrypted = result["Result"]["payload"]
        except (KeyError, TypeError) as exc:
            raise DeviceRegistrationError(
                "设备动态注册响应缺少 Result.payload。"
            ) from exc
        if not isinstance(encrypted, str):
            raise DeviceRegistrationError(
                "设备动态注册响应的 payload 格式错误。"
            )
        return decrypt_device_secret(
            encrypted,
            self.config.product_secret,
        )

    def _write_cache(self, device_secret: str) -> None:
        path = self.config.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(f"{path}.tmp")
        payload = {
            "instance_id": self.config.instance_id,
            "product_key": self.config.product_key,
            "device_name": self.config.device_name,
            "device_secret": device_secret,
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)
