"""Volcengine (Doubao) TTS 2.0 client for the Reachy Mini assistant.

The credentials are deliberately read from environment variables, never from
source code.  The client returns a WAV byte stream that can be passed directly
to :func:`robot.tts_playback.prepare_audio`.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TTS_ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
SUCCESS_CODES = {0, 20000000}


class VolcengineTTSError(RuntimeError):
    """Raised when Volcengine cannot produce usable speech audio."""


def load_env_file(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE entries without replacing existing variables."""

    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class VolcengineTTSConfig:
    """Configuration required by the Volcengine TTS 2.0 V3 API."""

    app_id: str
    access_token: str
    resource_id: str
    voice_type: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "VolcengineTTSConfig":
        fields = {
            "VOLCENGINE_TTS_APP_ID": "app_id",
            "VOLCENGINE_TTS_ACCESS_TOKEN": "access_token",
            "VOLCENGINE_TTS_RESOURCE_ID": "resource_id",
            "VOLCENGINE_TTS_VOICE_TYPE": "voice_type",
        }
        cleaned = {
            name: str(values.get(environment_name, "")).strip()
            for environment_name, name in fields.items()
        }
        missing = [environment_name for environment_name, name in fields.items() if not cleaned[name]]
        if missing:
            raise VolcengineTTSError(
                "缺少豆包语音配置：" + "、".join(missing)
            )
        return cls(**cleaned)

    @classmethod
    def from_env(cls) -> "VolcengineTTSConfig":
        return cls.from_mapping(os.environ)


class VolcengineTTSClient:
    """Small synchronous wrapper around Volcengine's unidirectional TTS API."""

    def __init__(
        self,
        config: VolcengineTTSConfig,
        *,
        endpoint: str = TTS_ENDPOINT,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._config = config
        self._endpoint = endpoint
        self._opener = opener

    def synthesize_wav(self, text: str, *, timeout: float = 30.0) -> bytes:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise VolcengineTTSError("要合成的文本不能为空。")

        payload = {
            "user": {"uid": "reachy-mini"},
            "req_params": {
                "text": cleaned_text,
                "speaker": self._config.voice_type,
                "audio_params": {"format": "wav", "sample_rate": 24000},
            },
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                # The legacy console labels this value APP ID; V3 deployments
                # have used both header spellings, so keep them consistent.
                "X-Api-App-Id": self._config.app_id,
                "X-Api-App-Key": self._config.app_id,
                "X-Api-Access-Key": self._config.access_token,
                "X-Api-Resource-Id": self._config.resource_id,
                "X-Api-Request-Id": str(uuid.uuid4()),
            },
            method="POST",
        )

        try:
            with self._opener(request, timeout=timeout) as response:
                body = response.read()
        except HTTPError as error:
            raise VolcengineTTSError(f"豆包语音请求失败：HTTP {error.code}") from error
        except URLError as error:
            raise VolcengineTTSError("无法连接豆包语音服务。") from error
        except OSError as error:
            raise VolcengineTTSError("豆包语音请求发生网络错误。") from error

        return self._extract_audio(body)

    @staticmethod
    def _extract_audio(body: bytes) -> bytes:
        if body.startswith(b"RIFF"):
            return body

        try:
            content = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise VolcengineTTSError("豆包语音返回了无法识别的音频数据。") from error

        decoder = json.JSONDecoder()
        position = 0
        audio_parts: list[bytes] = []

        while position < len(content):
            while position < len(content) and content[position].isspace():
                position += 1
            if content.startswith("data:", position):
                position += len("data:")
                while position < len(content) and content[position].isspace():
                    position += 1
            if position >= len(content):
                break

            try:
                message, position = decoder.raw_decode(content, position)
            except json.JSONDecodeError as error:
                raise VolcengineTTSError("无法解析豆包语音服务返回的数据。") from error

            if not isinstance(message, dict):
                raise VolcengineTTSError("豆包语音服务返回的数据格式不正确。")

            code = message.get("code")
            if code not in SUCCESS_CODES:
                detail = str(message.get("message") or "未知错误")
                raise VolcengineTTSError(f"豆包语音错误 {code}：{detail}")

            encoded_audio = message.get("data")
            if isinstance(encoded_audio, str) and encoded_audio:
                try:
                    audio_parts.append(base64.b64decode(encoded_audio, validate=True))
                except ValueError as error:
                    raise VolcengineTTSError("豆包语音返回的音频编码无效。") from error

        if not audio_parts:
            raise VolcengineTTSError("豆包语音未返回音频数据。")
        return b"".join(audio_parts)


def request_with_fallback(
    text: str,
    *,
    cloud_request: Callable[[str], bytes],
    local_request: Callable[[str], bytes],
    status: Callable[[str], None] = print,
) -> bytes:
    """Use cloud TTS first and retain local CosyVoice as a safe fallback."""

    try:
        return cloud_request(text)
    except VolcengineTTSError:
        status("豆包语音暂时不可用，正在改用本地 CosyVoice。")
        return local_request(text)
