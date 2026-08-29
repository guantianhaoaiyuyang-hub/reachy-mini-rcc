from __future__ import annotations

import unittest
from collections.abc import Iterable

import numpy as np

from robot.microphone import MicrophoneError, record_audio


class RecordingMedia:
    def __init__(self, samples: Iterable[np.ndarray | None]) -> None:
        self.samples = list(samples)
        self.started = 0
        self.stopped = 0

    def start_recording(self) -> None:
        self.started += 1

    def get_audio_sample(self) -> np.ndarray | None:
        return self.samples.pop(0)

    def stop_recording(self) -> None:
        self.stopped += 1


class Clock:
    def __init__(self, values: Iterable[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class MicrophoneTests(unittest.TestCase):
    def test_record_audio_concatenates_chunks_and_ignores_empty_reads(
        self,
    ) -> None:
        media = RecordingMedia(
            [
                np.array([0.1, 0.2], dtype=np.float32),
                None,
                np.array([0.3], dtype=np.float32),
            ]
        )
        sleeps: list[float] = []

        audio = record_audio(
            media,
            1.0,
            startup_delay=0.0,
            monotonic_fn=Clock([0.0, 0.1, 0.2, 0.3, 1.0]),
            sleep_fn=sleeps.append,
        )

        np.testing.assert_allclose(audio[:, 0], [0.1, 0.2, 0.3])
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(audio.shape, (3, 1))
        self.assertEqual(media.started, 1)
        self.assertEqual(media.stopped, 1)
        self.assertEqual(sleeps, [0.0, 0.01])

    def test_record_audio_stops_media_when_read_raises(self) -> None:
        class FailingMedia(RecordingMedia):
            def get_audio_sample(self) -> np.ndarray | None:
                raise RuntimeError("read failed")

        media = FailingMedia([])

        with self.assertRaisesRegex(RuntimeError, "read failed"):
            record_audio(
                media,
                1.0,
                startup_delay=0.0,
                monotonic_fn=Clock([0.0, 0.1]),
                sleep_fn=lambda _: None,
            )

        self.assertEqual(media.started, 1)
        self.assertEqual(media.stopped, 1)

    def test_record_audio_rejects_a_recording_without_samples(self) -> None:
        media = RecordingMedia([None])

        with self.assertRaisesRegex(MicrophoneError, "没有收到"):
            record_audio(
                media,
                1.0,
                startup_delay=0.0,
                monotonic_fn=Clock([0.0, 0.1, 1.0]),
                sleep_fn=lambda _: None,
            )

        self.assertEqual(media.started, 1)
        self.assertEqual(media.stopped, 1)


if __name__ == "__main__":
    unittest.main()
