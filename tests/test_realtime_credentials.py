from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from urllib.request import Request

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from robot.realtime_config import RealtimeConfig
from robot.realtime_credentials import (
    DeviceCredentials,
    decrypt_device_secret,
    registration_signature,
    websocket_headers,
)


PRODUCT_SECRET = "0123456789abcdef-secret"


def make_config(tmp_path: Path) -> RealtimeConfig:
    return RealtimeConfig(
        instance_id="instance",
        product_key="product",
        product_secret=PRODUCT_SECRET,
        bot_id="bot",
        device_name="reachy-mini-01",
        hardware_id="reachy-hardware-01",
        cache_path=tmp_path / "device.json",
    )


def encrypt_device_secret(device_secret: str) -> str:
    key = PRODUCT_SECRET.encode("utf-8")[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv=key)
    encrypted = cipher.encrypt(
        pad(device_secret.encode("utf-8"), AES.block_size)
    )
    return base64.b64encode(encrypted).decode("ascii")


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_registration_signature_matches_official_field_order() -> None:
    value = registration_signature(
        auth_type=1,
        device_name="reachy-mini-01",
        random_num=42,
        product_key="product",
        timestamp_ms=1720000000123,
        product_secret=PRODUCT_SECRET,
    )
    content = (
        "auth_type=1&device_name=reachy-mini-01&random_num=42"
        "&product_key=product&timestamp=1720000000123"
    )
    expected = base64.b64encode(
        hmac.new(
            PRODUCT_SECRET.encode("utf-8"),
            content.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")

    assert value == expected


def test_decrypt_device_secret_reverses_official_aes_cbc_payload() -> None:
    encrypted = encrypt_device_secret("device-secret-value")

    assert (
        decrypt_device_secret(encrypted, PRODUCT_SECRET)
        == "device-secret-value"
    )


def test_websocket_headers_match_official_signature_order(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    headers = websocket_headers(
        config,
        "device-secret-value",
        random_num=73,
        timestamp=1720000000,
    )

    content = (
        "auth_type=1&device_name=reachy-mini-01&random_num=73"
        "&product_key=product&timestamp=1720000000"
        "&instance_id=instance"
    )
    expected = base64.b64encode(
        hmac.new(
            b"device-secret-value",
            content.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    assert headers == {
        "X-Auth-Type": "1",
        "X-Product-Key": "product",
        "X-Device-Name": "reachy-mini-01",
        "X-Random-Num": "73",
        "X-Timestamp": "1720000000",
        "X-Instance-Id": "instance",
        "X-Signature": expected,
        "X-Hardware-Id": "reachy-hardware-01",
    }


def test_matching_cache_avoids_registration(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    config.cache_path.write_text(
        json.dumps(
            {
                "instance_id": "instance",
                "product_key": "product",
                "device_name": "reachy-mini-01",
                "device_secret": "cached-secret",
            }
        ),
        encoding="utf-8",
    )

    def fail_open(_request: Request, timeout: float):
        raise AssertionError(f"不应注册设备：{timeout}")

    credentials = DeviceCredentials(config, open_fn=fail_open)

    assert credentials.ensure_registered() == "cached-secret"


def test_mismatched_cache_registers_and_replaces_cache(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    config.cache_path.write_text(
        json.dumps(
            {
                "instance_id": "other",
                "product_key": "product",
                "device_name": "reachy-mini-01",
                "device_secret": "wrong-secret",
            }
        ),
        encoding="utf-8",
    )
    requests: list[Request] = []

    def fake_open(request: Request, timeout: float) -> FakeResponse:
        requests.append(request)
        assert timeout == 15.0
        return FakeResponse(
            {
                "ResponseMetadata": {},
                "Result": {
                    "payload": encrypt_device_secret(
                        "new-device-secret"
                    )
                },
            }
        )

    credentials = DeviceCredentials(
        config,
        open_fn=fake_open,
        random_fn=lambda: 99,
        time_ms_fn=lambda: 1720000000123,
    )

    assert credentials.ensure_registered() == "new-device-secret"
    assert len(requests) == 1
    request_body = json.loads(requests[0].data.decode("utf-8"))
    assert request_body["InstanceID"] == "instance"
    assert request_body["device_name"] == "reachy-mini-01"
    assert request_body["random_num"] == 99
    assert request_body["timestamp"] == 1720000000123
    assert "0123456789abcdef-secret" not in requests[0].data.decode()

    cached = json.loads(config.cache_path.read_text(encoding="utf-8"))
    assert cached["device_secret"] == "new-device-secret"
    assert not (tmp_path / "device.json.tmp").exists()
