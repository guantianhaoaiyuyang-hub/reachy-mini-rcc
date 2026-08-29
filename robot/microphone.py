from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

import numpy as np


class MicrophoneError(RuntimeError):
    """Reachy Mini 没有返回可用的麦克风数据。"""


class RecordingMedia(Protocol):
    def start_recording(self) -> None: ...

    def get_audio_sample(self) -> np.ndarray | None: ...

    def stop_recording(self) -> None: ...


def record_audio(
    media: RecordingMedia,
    duration_seconds: float,
    *,
    startup_delay: float = 1.0,
    poll_delay: float = 0.01,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> np.ndarray:
    chunks: list[np.ndarray] = []

    media.start_recording()
    try:
        sleep_fn(startup_delay)
        deadline = monotonic_fn() + duration_seconds

        while monotonic_fn() < deadline:
            chunk = media.get_audio_sample()
            if chunk is None:
                sleep_fn(poll_delay)
                continue

            prepared = np.asarray(chunk, dtype=np.float32)
            if prepared.size == 0:
                sleep_fn(poll_delay)
                continue
            if prepared.ndim == 1:
                prepared = prepared[:, np.newaxis]
            if prepared.ndim != 2:
                raise MicrophoneError(
                    "麦克风数据必须是二维数组 (samples, channels)。"
                )

            chunks.append(prepared)
    finally:
        media.stop_recording()

    if not chunks:
        raise MicrophoneError("录音失败：没有收到麦克风数据。")

    return np.concatenate(chunks, axis=0).astype(
        np.float32,
        copy=False,
    )
