from __future__ import annotations

import io
import json
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf


class TTSServiceError(RuntimeError):
    """本地 TTS 服务不可用或返回了无效数据。"""


class PlaybackMedia(Protocol):
    def start_playing(self) -> None: ...

    def push_audio_sample(self, chunk: np.ndarray) -> None: ...

    def stop_playing(self) -> None: ...


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _open(request: Request, timeout: float):
    try:
        return urlopen(request, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise TTSServiceError(f"TTS 服务请求失败：{exc}") from exc


def check_tts_health(
    base_url: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    request = Request(
        _endpoint(base_url, "/health"),
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with _open(request, timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TTSServiceError("TTS 健康检查返回了无效 JSON。") from exc

    if not isinstance(payload, dict):
        raise TTSServiceError("TTS 健康检查返回格式错误。")
    if payload.get("status") != "ready":
        raise TTSServiceError(
            f"TTS 服务尚未就绪：{payload.get('status', 'unknown')}"
        )

    return payload


def request_tts_wav(
    text: str,
    base_url: str,
    timeout: float = 180.0,
) -> bytes:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise TTSServiceError("合成文本不能为空。")

    body = json.dumps(
        {"text": cleaned_text},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        _endpoint(base_url, "/tts"),
        data=body,
        headers={
            "Accept": "audio/wav",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    with _open(request, timeout) as response:
        content_type = response.headers.get_content_type()
        wav_bytes = response.read()

    if content_type != "audio/wav":
        raise TTSServiceError(
            f"TTS 服务返回的内容不是 WAV：{content_type}"
        )
    if not wav_bytes:
        raise TTSServiceError("TTS 服务返回了空音频。")

    return wav_bytes


def prepare_audio(
    wav_bytes: bytes,
    target_sample_rate: int,
    target_channels: int,
    max_peak: float = 0.30,
    gain: float = 1.0,
) -> tuple[np.ndarray, float]:
    if target_sample_rate <= 0:
        raise TTSServiceError("目标采样率必须大于零。")
    if target_channels <= 0:
        raise TTSServiceError("目标声道数必须大于零。")
    if not 0.0 < max_peak <= 1.0:
        raise TTSServiceError("音频峰值限制必须位于 0 到 1 之间。")
    if gain <= 0.0:
        raise TTSServiceError("音频增益必须大于零。")

    try:
        audio, source_sample_rate = sf.read(
            io.BytesIO(wav_bytes),
            dtype="float32",
            always_2d=True,
        )
    except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as exc:
        raise TTSServiceError(f"无法解码 TTS WAV 音频：{exc}") from exc

    if audio.size == 0 or audio.shape[0] == 0:
        raise TTSServiceError("TTS WAV 音频没有有效采样。")

    source_channels = audio.shape[1]
    if source_channels != target_channels:
        if source_channels == 1:
            audio = np.repeat(audio, target_channels, axis=1)
        elif target_channels == 1:
            audio = np.mean(audio, axis=1, keepdims=True)
        else:
            raise TTSServiceError(
                f"无法将 {source_channels} 声道转换为 "
                f"{target_channels} 声道。"
            )

    if source_sample_rate != target_sample_rate:
        source_length = audio.shape[0]
        target_length = max(
            1,
            round(source_length * target_sample_rate / source_sample_rate),
        )
        source_positions = np.arange(source_length, dtype=np.float64)
        target_positions = (
            np.arange(target_length, dtype=np.float64)
            * source_sample_rate
            / target_sample_rate
        )
        target_positions = np.clip(
            target_positions,
            0.0,
            source_length - 1,
        )
        audio = np.column_stack(
            [
                np.interp(
                    target_positions,
                    source_positions,
                    audio[:, channel],
                )
                for channel in range(audio.shape[1])
            ]
        )

    audio = np.asarray(audio, dtype=np.float32)
    if gain != 1.0:
        audio *= gain
    peak = float(np.max(np.abs(audio)))
    if peak > max_peak:
        audio = np.clip(audio, -max_peak, max_peak)

    duration = audio.shape[0] / target_sample_rate
    return audio, duration


def play_audio_realtime(
    media: PlaybackMedia,
    audio: np.ndarray,
    sample_rate: int,
    chunk_ms: int = 20,
    startup_delay: float = 1.5,
    tail_delay: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    if sample_rate <= 0:
        raise TTSServiceError("播放采样率必须大于零。")
    if chunk_ms <= 0:
        raise TTSServiceError("音频分块时长必须大于零。")
    if audio.ndim != 2 or audio.shape[0] == 0:
        raise TTSServiceError(
            "播放音频必须是非空的二维数组 (samples, channels)。"
        )

    prepared = np.ascontiguousarray(audio, dtype=np.float32)
    chunk_size = max(1, round(sample_rate * chunk_ms / 1000))

    media.start_playing()
    try:
        if startup_delay > 0:
            sleep_fn(startup_delay)

        for start in range(0, prepared.shape[0], chunk_size):
            chunk = prepared[start : start + chunk_size]
            media.push_audio_sample(chunk)
            sleep_fn(chunk.shape[0] / sample_rate)

        if tail_delay > 0:
            sleep_fn(tail_delay)
    finally:
        media.stop_playing()
