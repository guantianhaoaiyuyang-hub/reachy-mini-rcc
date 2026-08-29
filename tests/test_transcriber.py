from __future__ import annotations

import unittest

import numpy as np

from robot.transcriber import WhisperTranscriber


class Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisper:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.audio: np.ndarray | None = None
        self.kwargs: dict[str, object] | None = None

    def transcribe(
        self,
        audio: np.ndarray,
        **kwargs: object,
    ) -> tuple[list[Segment], object]:
        self.audio = audio
        self.kwargs = kwargs
        return [Segment(text) for text in self.texts], object()


class TranscriberTests(unittest.TestCase):
    def test_transcribe_converts_stereo_to_mono_16khz_and_joins_text(
        self,
    ) -> None:
        model = FakeWhisper([" 你好 ", " Reachy "])
        transcriber = WhisperTranscriber(model=model)
        stereo_32khz = np.array(
            [
                [0.0, 0.2],
                [0.2, 0.4],
                [0.4, 0.6],
                [0.6, 0.8],
            ],
            dtype=np.float32,
        )

        result = transcriber.transcribe(stereo_32khz, 32_000)

        self.assertEqual(result, "你好Reachy")
        self.assertIsNotNone(model.audio)
        np.testing.assert_allclose(
            model.audio,
            np.array([0.1, 0.5], dtype=np.float32),
            atol=1e-6,
        )
        self.assertEqual(model.audio.dtype, np.float32)
        self.assertEqual(model.audio.shape, (2,))
        self.assertEqual(
            model.kwargs,
            {
                "language": "zh",
                "beam_size": 5,
                "vad_filter": True,
            },
        )

    def test_transcribe_returns_empty_string_when_no_segment_has_text(
        self,
    ) -> None:
        transcriber = WhisperTranscriber(
            model=FakeWhisper([" ", ""]),
        )

        result = transcriber.transcribe(
            np.zeros((160, 1), dtype=np.float32),
            16_000,
        )

        self.assertEqual(result, "")

    def test_transcribe_rejects_invalid_sample_rate(self) -> None:
        transcriber = WhisperTranscriber(model=FakeWhisper(["你好"]))

        with self.assertRaisesRegex(ValueError, "采样率"):
            transcriber.transcribe(
                np.zeros((160, 1), dtype=np.float32),
                0,
            )


if __name__ == "__main__":
    unittest.main()
