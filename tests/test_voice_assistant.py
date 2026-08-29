from __future__ import annotations

import unittest
from typing import Any

import numpy as np

from robot.assistant import (
    TurnOutcome,
    VoiceAssistant,
    run_interactive_loop,
)


class VoiceAssistantTests(unittest.TestCase):
    def test_run_turn_executes_each_stage_in_order(self) -> None:
        events: list[tuple[Any, ...]] = []
        source_audio = np.ones((160, 2), dtype=np.float32)
        prepared_audio = np.ones((80, 2), dtype=np.float32)

        def recorder(media: object, duration: float) -> np.ndarray:
            events.append(("record", media, duration))
            return source_audio

        class Transcriber:
            def transcribe(
                self,
                audio: np.ndarray,
                sample_rate: int,
            ) -> str:
                events.append(("transcribe", audio, sample_rate))
                return "你好"

        class Brain:
            def chat(self, text: str) -> str:
                events.append(("chat", text))
                return "你好，很高兴见到你。"

        def tts_request(
            text: str,
            base_url: str,
            timeout: float,
        ) -> bytes:
            events.append(("tts", text, base_url, timeout))
            return b"wav"

        def preparer(
            wav_bytes: bytes,
            target_sample_rate: int,
            target_channels: int,
            max_peak: float,
            gain: float,
        ) -> tuple[np.ndarray, float]:
            events.append(
                (
                    "prepare",
                    wav_bytes,
                    target_sample_rate,
                    target_channels,
                    max_peak,
                    gain,
                )
            )
            return prepared_audio, 0.005

        def player(
            media: object,
            audio: np.ndarray,
            sample_rate: int,
            chunk_ms: int,
        ) -> None:
            events.append(
                ("play", media, audio, sample_rate, chunk_ms)
            )

        assistant = VoiceAssistant(
            media="media",
            transcriber=Transcriber(),
            brain=Brain(),
            input_sample_rate=16_000,
            output_sample_rate=16_000,
            output_channels=2,
            recorder=recorder,
            tts_request=tts_request,
            audio_preparer=preparer,
            player=player,
            status_fn=lambda _: None,
        )

        outcome = assistant.run_turn()

        self.assertEqual(
            outcome,
            TurnOutcome(
                user_text="你好",
                assistant_text="你好，很高兴见到你。",
                spoken=True,
            ),
        )
        self.assertEqual(
            [event[0] for event in events],
            ["record", "transcribe", "chat", "tts", "prepare", "play"],
        )
        self.assertEqual(events[0][2], 3.0)
        self.assertEqual(events[1][2], 16_000)
        self.assertEqual(events[2][1], "你好")
        self.assertEqual(
            events[3][1:],
            (
                "你好，很高兴见到你。",
                "http://127.0.0.1:8123",
                180.0,
            ),
        )
        self.assertEqual(events[4][-2:], (0.30, 10.0))
        self.assertEqual(events[5][-2:], (16_000, 20))

    def test_run_turn_skips_remaining_stages_for_empty_transcription(
        self,
    ) -> None:
        calls: list[str] = []

        class EmptyTranscriber:
            def transcribe(
                self,
                audio: np.ndarray,
                sample_rate: int,
            ) -> str:
                return ""

        class BrainThatMustNotRun:
            def chat(self, text: str) -> str:
                calls.append("brain")
                raise AssertionError("Brain must not run")

        assistant = VoiceAssistant(
            media="media",
            transcriber=EmptyTranscriber(),
            brain=BrainThatMustNotRun(),
            input_sample_rate=16_000,
            output_sample_rate=16_000,
            output_channels=2,
            recorder=lambda media, duration: np.zeros(
                (160, 1),
                dtype=np.float32,
            ),
            tts_request=lambda *args, **kwargs: calls.append("tts"),
            audio_preparer=lambda *args, **kwargs: calls.append(
                "prepare"
            ),
            player=lambda *args, **kwargs: calls.append("play"),
            status_fn=lambda _: None,
        )

        outcome = assistant.run_turn()

        self.assertEqual(outcome, TurnOutcome("", "", False))
        self.assertEqual(calls, [])


class InteractiveLoopTests(unittest.TestCase):
    def test_command_loop_runs_turns_until_q_and_reports_empty_audio(
        self,
    ) -> None:
        commands = iter(["", "", "q"])

        class Assistant:
            def __init__(self) -> None:
                self.calls = 0

            def run_turn(self) -> TurnOutcome:
                self.calls += 1
                if self.calls == 1:
                    return TurnOutcome("", "", False)
                return TurnOutcome("你好", "你好", True)

        assistant = Assistant()
        output: list[str] = []

        run_interactive_loop(
            assistant,
            input_fn=lambda prompt: next(commands),
            output_fn=output.append,
        )

        self.assertEqual(assistant.calls, 2)
        self.assertIn("没有识别到有效语音，请重试。", output)
        self.assertEqual(output[-1], "语音助手已退出。")

    def test_command_loop_reports_turn_error_and_remains_available(
        self,
    ) -> None:
        commands = iter(["", "q"])

        class FailingAssistant:
            def run_turn(self) -> TurnOutcome:
                raise RuntimeError("network failed")

        output: list[str] = []
        run_interactive_loop(
            FailingAssistant(),
            input_fn=lambda prompt: next(commands),
            output_fn=output.append,
        )

        self.assertTrue(
            any("network failed" in line for line in output)
        )
        self.assertEqual(output[-1], "语音助手已退出。")


if __name__ == "__main__":
    unittest.main()
