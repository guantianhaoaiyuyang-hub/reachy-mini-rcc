from __future__ import annotations

import unittest

import config


class VoiceConfigurationTests(unittest.TestCase):
    def test_recording_window_is_three_seconds(self) -> None:
        self.assertEqual(config.RECORD_SECONDS, 3.0)

    def test_host_motion_limits_are_safe(self) -> None:
        self.assertLessEqual(abs(config.HOST_HEAD_YAW_DEGREES), 12.0)
        self.assertLessEqual(abs(config.HOST_HEAD_PITCH_DEGREES), 8.0)
        self.assertLessEqual(abs(config.HOST_ANTENNA_RADIANS), 0.65)
        self.assertGreater(config.HOST_MOTION_STEP_SECONDS, 0.0)


if __name__ == "__main__":
    unittest.main()
