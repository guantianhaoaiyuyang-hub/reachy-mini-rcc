"""Safe, visible host-style movements while Reachy speaks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation

from config import (
    HOST_ANTENNA_RADIANS,
    HOST_HEAD_PITCH_DEGREES,
    HOST_HEAD_YAW_DEGREES,
    HOST_MOTION_STEP_SECONDS,
)


def make_head_pose(pitch_degrees: float, yaw_degrees: float) -> np.ndarray:
    """Create a task-space head pose with bounded pitch and yaw angles."""

    pose = np.eye(4, dtype=np.float64)
    pose[:3, :3] = Rotation.from_euler(
        "xyz",
        [pitch_degrees, 0.0, yaw_degrees],
        degrees=True,
    ).as_matrix()
    return pose


class HostSpeechMotion:
    """Runs a host-style head and antenna loop in a stoppable worker thread."""

    def __init__(
        self,
        robot: Any,
        *,
        status_fn: Callable[[str], None] = print,
        step_seconds: float = HOST_MOTION_STEP_SECONDS,
    ) -> None:
        if step_seconds <= 0.0:
            raise ValueError("讲话动作的节奏时长必须大于 0。")

        self._robot = robot
        self._status_fn = status_fn
        self._step_seconds = step_seconds
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._neutral_returned = False

    def start(self) -> None:
        """Start the motion loop once for the current spoken response."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._neutral_returned = False
            self._thread = threading.Thread(
                target=self._run,
                name="reachy-speech-motion",
                daemon=True,
            )
            self._thread.start()

    def stop_and_return(self, timeout: float = 2.0) -> None:
        """Stop gestures and make one best-effort return to neutral."""

        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self._return_to_neutral()

    def _run(self) -> None:
        antenna = HOST_ANTENNA_RADIANS
        sequence = (
            (make_head_pose(0.0, 0.0), [antenna, 0.15]),
            (
                make_head_pose(HOST_HEAD_PITCH_DEGREES, HOST_HEAD_YAW_DEGREES),
                [antenna, -0.15],
            ),
            (
                make_head_pose(-5.0, -HOST_HEAD_YAW_DEGREES),
                [-0.15, antenna],
            ),
            (make_head_pose(0.0, 0.0), [0.0, 0.0]),
        )

        try:
            while not self._stop_event.is_set():
                for head, antennas in sequence:
                    if self._stop_event.is_set():
                        return
                    self._robot.goto_target(
                        head=head,
                        antennas=antennas,
                        duration=self._step_seconds,
                        body_yaw=0.0,
                    )
                    if self._stop_event.wait(self._step_seconds):
                        return
        except Exception:
            self._status_fn("讲话动作暂时不可用，语音会继续播放。")
        finally:
            self._return_to_neutral()

    def _return_to_neutral(self) -> None:
        with self._lock:
            if self._neutral_returned:
                return
            self._neutral_returned = True

        try:
            self._robot.goto_target(
                head=np.eye(4, dtype=np.float64),
                antennas=[0.0, 0.0],
                duration=self._step_seconds,
                body_yaw=0.0,
            )
        except Exception:
            self._status_fn("讲话动作回正失败，下一轮会重新尝试。")
