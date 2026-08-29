"""Conversation-state and audio-reactive Reachy Mini motion."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from config import (
    HOST_ANTENNA_RADIANS,
    HOST_HEAD_PITCH_DEGREES,
    HOST_HEAD_YAW_DEGREES,
)
from robot.conversation_state import (
    ConversationState,
    ConversationStatus,
)
from robot.speech_motion import make_head_pose
from robot.streaming_audio import AudioEnvelope


_NEUTRAL_STATES = {
    ConversationStatus.CONNECTING,
    ConversationStatus.INTERRUPTED,
    ConversationStatus.RECONNECTING,
    ConversationStatus.STOPPED,
}


class ReactiveMotion:
    """Own one motion worker for the full real-time conversation."""

    def __init__(
        self,
        robot: Any,
        *,
        state: ConversationState,
        step_seconds: float = 0.12,
        status_fn=print,
    ) -> None:
        if step_seconds <= 0:
            raise ValueError("动作步长必须大于零。")
        self._robot = robot
        self._state = state
        self._step_seconds = step_seconds
        self._status_fn = status_fn
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._envelope = AudioEnvelope(rms=0.0, peak=0.0)
        self._phase = 1.0
        self._neutral_sent = False
        state.subscribe(self._on_state_change)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._neutral_sent = False
            self._thread = threading.Thread(
                target=self._run,
                name="reachy-reactive-motion",
                daemon=True,
            )
            self._thread.start()

    def update_envelope(self, envelope: AudioEnvelope) -> None:
        with self._lock:
            self._envelope = envelope
        self._wake_event.set()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self._send_neutral(force=True)
        with self._lock:
            self._thread = None

    def _on_state_change(
        self,
        _old: ConversationStatus,
        new: ConversationStatus,
    ) -> None:
        if new in _NEUTRAL_STATES:
            self._send_neutral(force=False)
        else:
            with self._lock:
                self._neutral_sent = False
        self._wake_event.set()

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                status = self._state.status
                if status in _NEUTRAL_STATES:
                    self._send_neutral(force=False)
                elif status is ConversationStatus.LISTENING:
                    self._send_listening_target()
                elif status is ConversationStatus.THINKING:
                    self._send_thinking_target()
                elif status is ConversationStatus.SPEAKING:
                    self._send_speaking_target()
                self._phase *= -1.0
                self._wake_event.wait(self._step_seconds)
                self._wake_event.clear()
        except Exception as exc:
            self._status_fn(f"实时动作暂时不可用：{exc}")
        finally:
            self._send_neutral(force=True)

    def _send_listening_target(self) -> None:
        antenna = 0.12 * self._phase
        self._goto(
            pitch=0.0,
            yaw=2.0 * self._phase,
            antennas=[antenna, -antenna],
        )

    def _send_thinking_target(self) -> None:
        self._goto(
            pitch=-3.0,
            yaw=5.0 * self._phase,
            antennas=[0.18, -0.18],
        )

    def _send_speaking_target(self) -> None:
        with self._lock:
            envelope = self._envelope
        level = float(np.clip(envelope.rms / 0.18, 0.20, 1.0))
        self._goto(
            pitch=HOST_HEAD_PITCH_DEGREES * level * 0.55,
            yaw=HOST_HEAD_YAW_DEGREES * level * self._phase,
            antennas=[
                HOST_ANTENNA_RADIANS * level,
                -HOST_ANTENNA_RADIANS * level * self._phase,
            ],
        )

    def _goto(
        self,
        *,
        pitch: float,
        yaw: float,
        antennas: list[float],
    ) -> None:
        with self._lock:
            self._neutral_sent = False
        self._robot.goto_target(
            head=make_head_pose(pitch, yaw),
            antennas=antennas,
            duration=self._step_seconds,
            body_yaw=0.0,
        )

    def _send_neutral(self, *, force: bool) -> None:
        with self._lock:
            if self._neutral_sent and not force:
                return
            self._neutral_sent = True
        try:
            self._robot.goto_target(
                head=np.eye(4, dtype=np.float64),
                antennas=[0.0, 0.0],
                duration=self._step_seconds,
                body_yaw=0.0,
            )
        except Exception as exc:
            self._status_fn(f"实时动作回正失败：{exc}")
