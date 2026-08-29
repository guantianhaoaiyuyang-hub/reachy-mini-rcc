from __future__ import annotations

import threading
import unittest

from robot.speech_motion import HostSpeechMotion


class FakeRobot:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, float, float]] = []
        self.first_call = threading.Event()

    def goto_target(
        self,
        head: object = None,
        antennas: object = None,
        duration: float = 0.5,
        body_yaw: float = 0.0,
    ) -> None:
        self.calls.append((head, antennas, duration, body_yaw))
        self.first_call.set()


class HostSpeechMotionTests(unittest.TestCase):
    def test_motion_starts_with_safe_gesture_and_returns_neutral(self) -> None:
        robot = FakeRobot()
        motion = HostSpeechMotion(robot, step_seconds=0.01)

        motion.start()
        self.assertTrue(robot.first_call.wait(1.0))
        motion.stop_and_return()

        self.assertGreaterEqual(len(robot.calls), 2)
        gesture_head, gesture_antennas, gesture_duration, gesture_body_yaw = robot.calls[0]
        neutral_head, neutral_antennas, _, neutral_body_yaw = robot.calls[-1]
        self.assertIsNotNone(gesture_head)
        self.assertEqual(len(gesture_antennas), 2)
        self.assertEqual(gesture_duration, 0.01)
        self.assertEqual(gesture_body_yaw, 0.0)
        self.assertIsNotNone(neutral_head)
        self.assertEqual(neutral_antennas, [0.0, 0.0])
        self.assertEqual(neutral_body_yaw, 0.0)

    def test_motion_error_is_reported_and_does_not_escape(self) -> None:
        class BrokenRobot:
            def __init__(self) -> None:
                self.attempted = threading.Event()

            def goto_target(self, *args: object, **kwargs: object) -> None:
                self.attempted.set()
                raise RuntimeError("link lost")

        robot = BrokenRobot()
        messages: list[str] = []
        motion = HostSpeechMotion(
            robot,
            status_fn=messages.append,
            step_seconds=0.01,
        )

        motion.start()
        self.assertTrue(robot.attempted.wait(1.0))
        motion.stop_and_return()

        self.assertTrue(any("动作" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
