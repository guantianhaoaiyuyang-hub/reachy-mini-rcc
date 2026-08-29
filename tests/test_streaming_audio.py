from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest

from robot.interruption import InterruptionController
from robot.streaming_audio import (
    AudioFormatError,
    MicrophoneStreamer,
    StreamingPlayer,
    float_audio_to_pcm16,
    pcm16_to_float_audio,
)


def test_float_audio_mixes_stereo_clips_and_encodes_little_endian() -> None:
    audio = np.array(
        [
            [1.5, 1.5],
            [1.0, -1.0],
            [-2.0, -2.0],
        ],
        dtype=np.float32,
    )

    encoded = float_audio_to_pcm16(
        audio,
        source_rate=16_000,
        target_rate=16_000,
    )

    samples = np.frombuffer(encoded, dtype="<i2")
    assert samples.tolist() == [32767, 0, -32767]


def test_float_audio_resampling_preserves_duration() -> None:
    audio = np.linspace(-0.5, 0.5, 4_800, dtype=np.float32)

    encoded = float_audio_to_pcm16(
        audio,
        source_rate=48_000,
        target_rate=16_000,
    )

    assert len(encoded) // 2 == 1_600


def test_pcm16_output_applies_gain_limiter_rate_and_channels() -> None:
    source = np.full(2_400, 10_000, dtype="<i2").tobytes()

    audio = pcm16_to_float_audio(
        source,
        source_rate=24_000,
        target_rate=48_000,
        channels=2,
        gain=10.0,
        max_peak=0.30,
    )

    assert audio.shape == (4_800, 2)
    assert audio.dtype == np.float32
    assert float(np.max(np.abs(audio))) <= 0.300001
    assert np.allclose(audio[:, 0], audio[:, 1])


@pytest.mark.parametrize(
    "audio",
    [
        np.array([], dtype=np.float32),
        np.zeros((2, 2, 2), dtype=np.float32),
    ],
)
def test_float_audio_rejects_empty_or_invalid_shape(
    audio: np.ndarray,
) -> None:
    with pytest.raises(AudioFormatError):
        float_audio_to_pcm16(
            audio,
            source_rate=48_000,
            target_rate=16_000,
        )


def test_pcm16_rejects_odd_byte_count() -> None:
    with pytest.raises(AudioFormatError):
        pcm16_to_float_audio(
            b"\x00",
            source_rate=24_000,
            target_rate=48_000,
            channels=2,
        )


class FakeRecordingMedia:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.audio = np.full((960, 2), 0.1, dtype=np.float32)

    def start_recording(self) -> None:
        self.started += 1

    def get_audio_sample(self) -> np.ndarray:
        return self.audio

    def stop_recording(self) -> None:
        self.stopped += 1


def test_microphone_streamer_starts_once_sends_pcm_and_stops() -> None:
    media = FakeRecordingMedia()
    stop_event = threading.Event()
    sent: list[bytes] = []

    def send_audio(data: bytes) -> None:
        sent.append(data)
        stop_event.set()

    streamer = MicrophoneStreamer(
        media,
        source_rate=48_000,
        target_rate=16_000,
        sleep_fn=lambda _duration: None,
    )
    streamer.run(stop_event, send_audio)

    assert media.started == 1
    assert media.stopped == 1
    assert len(sent) == 1
    assert len(sent[0]) == 640


class BlockingPlaybackMedia:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.pushes: list[np.ndarray] = []
        self.first_push = threading.Event()
        self.second_push = threading.Event()
        self.release_first = threading.Event()

    def start_playing(self) -> None:
        self.started += 1

    def push_audio_sample(self, chunk: np.ndarray) -> None:
        self.pushes.append(chunk.copy())
        if len(self.pushes) == 1:
            self.first_push.set()
            assert self.release_first.wait(timeout=2.0)
        elif len(self.pushes) == 2:
            self.second_push.set()

    def stop_playing(self) -> None:
        self.stopped += 1


def pcm(value: int, sample_count: int) -> bytes:
    return np.full(sample_count, value, dtype="<i2").tobytes()


def test_streaming_player_never_plays_old_frames_after_interrupt() -> None:
    media = BlockingPlaybackMedia()
    controller = InterruptionController()
    player = StreamingPlayer(
        media,
        interruption=controller,
        source_rate=24_000,
        target_rate=24_000,
        channels=1,
        gain=1.0,
        max_peak=1.0,
        chunk_ms=20,
        sleep_fn=lambda _duration: None,
    )
    old_generation = controller.begin_response("resp-old")
    player.start()
    player.enqueue(
        old_generation,
        "resp-old",
        pcm(1_000, 960),
    )
    assert media.first_push.wait(timeout=2.0)

    player.interrupt()
    new_generation = controller.begin_response("resp-new")
    player.enqueue(
        new_generation,
        "resp-new",
        pcm(20_000, 480),
    )
    media.release_first.set()
    assert media.second_push.wait(timeout=2.0)
    time.sleep(0.02)
    player.stop()

    assert media.started == 1
    assert media.stopped == 1
    assert len(media.pushes) == 2
    first_mean = float(np.mean(media.pushes[0]))
    second_mean = float(np.mean(media.pushes[1]))
    assert first_mean == pytest.approx(1_000 / 32767, abs=1e-4)
    assert second_mean == pytest.approx(20_000 / 32767, abs=1e-4)


def test_streaming_player_waits_until_queued_audio_is_finished() -> None:
    async def scenario() -> None:
        media = BlockingPlaybackMedia()
        controller = InterruptionController()
        player = StreamingPlayer(
            media,
            interruption=controller,
            source_rate=24_000,
            target_rate=24_000,
            channels=1,
            gain=1.0,
            max_peak=1.0,
            chunk_ms=20,
            sleep_fn=lambda _duration: None,
        )
        generation = controller.begin_response("resp")
        player.start()
        player.enqueue(generation, "resp", pcm(1_000, 480))
        assert await asyncio.to_thread(
            media.first_push.wait,
            2.0,
        )

        waiter = asyncio.create_task(player.wait_until_idle())
        await asyncio.sleep(0.01)
        assert not waiter.done()

        media.release_first.set()
        await asyncio.wait_for(waiter, timeout=2.0)
        player.stop()

    asyncio.run(scenario())
