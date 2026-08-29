from __future__ import annotations

import unittest
from unittest.mock import patch

import main as app


class FakeMedia:
    def get_input_audio_samplerate(self) -> int:
        return 16_000

    def get_output_audio_samplerate(self) -> int:
        return 16_000

    def get_output_channels(self) -> int:
        return 2


class FakeReachy:
    def __init__(self) -> None:
        self.media = FakeMedia()
        self.motors_enabled = False

    def __enter__(self) -> "FakeReachy":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def enable_motors(self) -> None:
        self.motors_enabled = True


class MainStartupTests(unittest.TestCase):
    def test_connected_robot_motors_are_enabled_before_interaction(self) -> None:
        robot = FakeReachy()

        with (
            patch.object(app, "load_env_file"),
            patch.object(app, "make_tts_request", return_value=lambda *args, **kwargs: b""),
            patch.object(app, "DeepSeekBrain", return_value=object()),
            patch.object(app, "WhisperTranscriber", return_value=object()),
            patch.object(app, "ReachyMini", return_value=robot),
            patch.object(app, "VoiceAssistant", return_value=object()),
            patch.object(app, "run_interactive_loop"),
        ):
            app.main()

        self.assertTrue(robot.motors_enabled)


if __name__ == "__main__":
    unittest.main()
