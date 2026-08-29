from __future__ import annotations

import unittest

import numpy as np

from robot.assistant import VoiceAssistant


class VoiceAssistantMotionIntegrationTests(unittest.TestCase):
    def make_assistant(
        self,
        events: list[str],
        *,
        player: object,
    ) -> VoiceAssistant:
        class Motion:
            def start(self) -> None:
                events.append("motion_start")

            def stop_and_return(self) -> None:
                events.append("motion_stop")

        class Transcriber:
            def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
                events.append("transcribe")
                return "hello"

        class Brain:
            def chat(self, text: str) -> str:
                events.append("chat")
                return "answer"

        def recorder(media: object, duration: float) -> np.ndarray:
            events.append("record")
            return np.ones((20, 1), dtype=np.float32)

        def tts_request(*args: object, **kwargs: object) -> bytes:
            events.append("tts")
            return b"wav"

        def preparer(*args: object, **kwargs: object) -> tuple[np.ndarray, float]:
            events.append("prepare")
            return np.ones((20, 1), dtype=np.float32), 0.01

        return VoiceAssistant(
            media="media",
            transcriber=Transcriber(),
            brain=Brain(),
            input_sample_rate=16_000,
            output_sample_rate=16_000,
            output_channels=1,
            recorder=recorder,
            tts_request=tts_request,
            audio_preparer=preparer,
            player=player,
            speech_motion_factory=Motion,
            status_fn=lambda _: None,
        )

    def test_motion_wraps_successful_playback(self) -> None:
        events: list[str] = []

        def player(*args: object, **kwargs: object) -> None:
            events.append("play")

        self.make_assistant(events, player=player).run_turn()

        self.assertEqual(
            events,
            [
                "record",
                "transcribe",
                "chat",
                "tts",
                "prepare",
                "motion_start",
                "play",
                "motion_stop",
            ],
        )

    def test_motion_returns_neutral_when_playback_fails(self) -> None:
        events: list[str] = []

        def broken_player(*args: object, **kwargs: object) -> None:
            events.append("play")
            raise RuntimeError("speaker unavailable")

        with self.assertRaisesRegex(RuntimeError, "speaker unavailable"):
            self.make_assistant(events, player=broken_player).run_turn()

        self.assertEqual(events[-2:], ["play", "motion_stop"])


if __name__ == "__main__":
    unittest.main()
