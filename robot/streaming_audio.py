from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Protocol

import numpy as np

from robot.interruption import InterruptionController


class AudioFormatError(RuntimeError):
    """实时音频格式无效。"""


class RecordingMedia(Protocol):
    def start_recording(self) -> None: ...

    def get_audio_sample(self) -> np.ndarray | None: ...

    def stop_recording(self) -> None: ...


class PlaybackMedia(Protocol):
    def start_playing(self) -> None: ...

    def push_audio_sample(self, chunk: np.ndarray) -> None: ...

    def stop_playing(self) -> None: ...


@dataclass(frozen=True)
class AudioEnvelope:
    rms: float
    peak: float


def _validate_rates(source_rate: int, target_rate: int) -> None:
    if source_rate <= 0 or target_rate <= 0:
        raise AudioFormatError("音频采样率必须大于零。")


def _resample(
    audio: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    _validate_rates(source_rate, target_rate)
    if source_rate == target_rate:
        return np.asarray(audio, dtype=np.float32)

    source_length = audio.shape[0]
    target_length = max(
        1,
        round(source_length * target_rate / source_rate),
    )
    source_positions = np.arange(source_length, dtype=np.float64)
    target_positions = (
        np.arange(target_length, dtype=np.float64)
        * source_rate
        / target_rate
    )
    target_positions = np.clip(
        target_positions,
        0.0,
        source_length - 1,
    )
    if audio.ndim == 1:
        result = np.interp(
            target_positions,
            source_positions,
            audio,
        )
    else:
        result = np.column_stack(
            [
                np.interp(
                    target_positions,
                    source_positions,
                    audio[:, channel],
                )
                for channel in range(audio.shape[1])
            ]
        )
    return np.asarray(result, dtype=np.float32)


def float_audio_to_pcm16(
    audio: np.ndarray,
    *,
    source_rate: int,
    target_rate: int,
) -> bytes:
    prepared = np.asarray(audio, dtype=np.float32)
    if prepared.size == 0:
        raise AudioFormatError("麦克风音频不能为空。")
    if prepared.ndim == 2:
        prepared = np.mean(prepared, axis=1)
    elif prepared.ndim != 1:
        raise AudioFormatError(
            "麦克风音频必须是一维或二维数组。"
        )

    prepared = _resample(
        prepared,
        source_rate,
        target_rate,
    )
    prepared = np.clip(prepared, -1.0, 1.0)
    pcm = np.rint(prepared * 32767.0).astype("<i2")
    return pcm.tobytes()


def pcm16_to_float_audio(
    data: bytes,
    *,
    source_rate: int,
    target_rate: int,
    channels: int,
    gain: float = 1.0,
    max_peak: float = 0.30,
) -> np.ndarray:
    _validate_rates(source_rate, target_rate)
    if len(data) == 0 or len(data) % 2:
        raise AudioFormatError(
            "PCM16 音频必须包含偶数个非空字节。"
        )
    if channels <= 0:
        raise AudioFormatError("目标声道数必须大于零。")
    if gain <= 0:
        raise AudioFormatError("音频增益必须大于零。")
    if not 0 < max_peak <= 1:
        raise AudioFormatError("音频峰值限制必须位于 0 到 1。")

    mono = np.frombuffer(data, dtype="<i2").astype(np.float32)
    mono /= 32767.0
    mono = np.clip(mono, -1.0, 1.0)
    mono = _resample(mono, source_rate, target_rate)
    mono *= gain
    mono = np.clip(mono, -max_peak, max_peak)
    audio = np.repeat(mono[:, np.newaxis], channels, axis=1)
    return np.ascontiguousarray(audio, dtype=np.float32)


class MicrophoneStreamer:
    def __init__(
        self,
        media: RecordingMedia,
        *,
        source_rate: int,
        target_rate: int,
        poll_delay: float = 0.005,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        _validate_rates(source_rate, target_rate)
        self.media = media
        self.source_rate = source_rate
        self.target_rate = target_rate
        self.poll_delay = poll_delay
        self.sleep_fn = sleep_fn

    def run(
        self,
        stop_event: Event,
        send_audio: Callable[[bytes], None],
    ) -> None:
        self.media.start_recording()
        try:
            while not stop_event.is_set():
                audio = self.media.get_audio_sample()
                if audio is None or np.asarray(audio).size == 0:
                    self.sleep_fn(self.poll_delay)
                    continue
                pcm = float_audio_to_pcm16(
                    audio,
                    source_rate=self.source_rate,
                    target_rate=self.target_rate,
                )
                send_audio(pcm)
        finally:
            self.media.stop_recording()


_STOP = object()


class StreamingPlayer:
    def __init__(
        self,
        media: PlaybackMedia,
        *,
        interruption: InterruptionController,
        source_rate: int,
        target_rate: int,
        channels: int,
        gain: float = 10.0,
        max_peak: float = 0.30,
        chunk_ms: int = 20,
        envelope_fn: Callable[[AudioEnvelope], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        _validate_rates(source_rate, target_rate)
        if chunk_ms <= 0:
            raise AudioFormatError("音频分帧时长必须大于零。")
        self.media = media
        self.interruption = interruption
        self.source_rate = source_rate
        self.target_rate = target_rate
        self.channels = channels
        self.gain = gain
        self.max_peak = max_peak
        self.chunk_ms = chunk_ms
        self.envelope_fn = envelope_fn or (lambda _value: None)
        self.sleep_fn = sleep_fn
        self.queue: Queue[
            tuple[int, str, bytes] | object
        ] = Queue(maxsize=200)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lifecycle_lock = Lock()
        self._pending_lock = Lock()
        self._pending = 0
        self._idle_event = Event()
        self._idle_event.set()
        self._error: BaseException | None = None

    @property
    def error(self) -> BaseException | None:
        return self._error

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._error = None
            self.media.start_playing()
            self._thread = Thread(
                target=self._run,
                name="reachy-realtime-playback",
                daemon=True,
            )
            self._thread.start()

    def enqueue(
        self,
        generation: int,
        response_id: str,
        pcm_bytes: bytes,
    ) -> None:
        if pcm_bytes:
            with self._pending_lock:
                self._pending += 1
                self._idle_event.clear()
            try:
                self.queue.put((generation, response_id, pcm_bytes))
            except BaseException:
                self._finish_items(1)
                raise

    def interrupt(self) -> int:
        _generation, removed = self.interruption.interrupt(self.queue)
        self._finish_items(removed)
        return removed

    async def wait_until_idle(self) -> None:
        await asyncio.to_thread(self._idle_event.wait)

    def stop(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
            removed = self.interruption.clear_queue(self.queue)
            self._finish_items(removed)
            self.queue.put(_STOP)
        thread.join(timeout=3.0)
        with self._lifecycle_lock:
            self.media.stop_playing()
            self._thread = None

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                item = self.queue.get()
                if item is _STOP:
                    return
                generation, response_id, pcm_bytes = item
                try:
                    if not self.interruption.is_current(
                        generation,
                        response_id,
                    ):
                        continue
                    audio = pcm16_to_float_audio(
                        pcm_bytes,
                        source_rate=self.source_rate,
                        target_rate=self.target_rate,
                        channels=self.channels,
                        gain=self.gain,
                        max_peak=self.max_peak,
                    )
                    chunk_size = max(
                        1,
                        round(
                            self.target_rate
                            * self.chunk_ms
                            / 1_000
                        )
                    )
                    for start in range(
                        0,
                        audio.shape[0],
                        chunk_size,
                    ):
                        if self._stop_event.is_set():
                            return
                        if not self.interruption.is_current(
                            generation,
                            response_id,
                        ):
                            break
                        chunk = audio[start : start + chunk_size]
                        self.envelope_fn(
                            AudioEnvelope(
                                rms=float(
                                    np.sqrt(
                                        np.mean(np.square(chunk))
                                    )
                                ),
                                peak=float(np.max(np.abs(chunk))),
                            )
                        )
                        self.media.push_audio_sample(chunk)
                        self.sleep_fn(
                            chunk.shape[0] / self.target_rate
                        )
                finally:
                    self._finish_items(1)
        except BaseException as exc:
            self._error = exc
            self._stop_event.set()
            with self._pending_lock:
                self._pending = 0
                self._idle_event.set()

    def _finish_items(self, count: int) -> None:
        if count <= 0:
            return
        with self._pending_lock:
            self._pending = max(0, self._pending - count)
            if self._pending == 0:
                self._idle_event.set()
