from __future__ import annotations

import time

import numpy as np

from robot.conversation_state import (
    ConversationState,
    ConversationStatus,
)
from robot.reactive_motion import ReactiveMotion
from robot.streaming_audio import AudioEnvelope


class FakeRobot:
    def __init__(self) -> None:
        self.targets: list[dict[str, object]] = []

    def goto_target(self, **target: object) -> None:
        self.targets.append(target)


def wait_for(predicate, timeout: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached")


def is_neutral(target: dict[str, object]) -> bool:
    return bool(
        np.allclose(target["head"], np.eye(4))
        and target["antennas"] == [0.0, 0.0]
    )


def test_speaking_motion_follows_audio_and_interrupt_returns_neutral() -> None:
    robot = FakeRobot()
    state = ConversationState(ConversationStatus.LISTENING)
    motion = ReactiveMotion(robot, state=state, step_seconds=0.01)
    motion.start()

    state.transition(ConversationStatus.SPEAKING)
    motion.update_envelope(AudioEnvelope(rms=0.18, peak=0.25))

    wait_for(
        lambda: any(not is_neutral(target) for target in robot.targets),
    )
    state.transition(ConversationStatus.INTERRUPTED)
    wait_for(lambda: is_neutral(robot.targets[-1]))

    motion.stop()
    assert is_neutral(robot.targets[-1])


def test_listening_motion_is_subtle_and_stop_is_idempotent() -> None:
    robot = FakeRobot()
    state = ConversationState(ConversationStatus.LISTENING)
    motion = ReactiveMotion(robot, state=state, step_seconds=0.01)

    motion.start()
    wait_for(lambda: len(robot.targets) >= 2)
    motion.stop()
    motion.stop()

    non_neutral = [
        target for target in robot.targets if not is_neutral(target)
    ]
    assert non_neutral
    assert all(
        max(abs(float(value)) for value in target["antennas"])
        <= 0.15
        for target in non_neutral
    )
    assert is_neutral(robot.targets[-1])
