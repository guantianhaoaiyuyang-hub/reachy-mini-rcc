"""Event orchestration for the always-listening real-time assistant."""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Any

from robot.conversation_state import (
    ConversationState,
    ConversationStatus,
)
from robot.interruption import InterruptionController
from robot.realtime_protocol import (
    ServerEvent,
    cancel_response_event,
)


class RealtimeAssistant:
    def __init__(
        self,
        *,
        state: ConversationState,
        interruption: InterruptionController,
        player: Any,
        session: Any | None = None,
        status_fn=print,
    ) -> None:
        self.state = state
        self.interruption = interruption
        self.player = player
        self.session = session
        self.status_fn = status_fn
        self._active_response_id: str | None = None
        self._active_generation: int | None = None

    def attach_session(self, session: Any) -> None:
        self.session = session

    async def handle_event(self, event: ServerEvent) -> None:
        event_type = event.type

        if event_type == "session.updated":
            if self.state.status in {
                ConversationStatus.CONNECTING,
                ConversationStatus.RECONNECTING,
            }:
                self.state.transition(ConversationStatus.LISTENING)
            self.status_fn("实时语音已连接，可以随时说话。")
            return

        if event_type == "input_audio_buffer.speech_started":
            await self._handle_speech_started()
            return

        if event_type == "input_audio_buffer.speech_stopped":
            if self.state.status is ConversationStatus.LISTENING:
                self.state.transition(ConversationStatus.THINKING)
            return

        if event_type == "response.created":
            response_id = self._response_id(event)
            if response_id:
                self._active_response_id = response_id
                self._active_generation = (
                    self.interruption.begin_response(response_id)
                )
            return

        if event_type == "response.audio.delta":
            self._handle_audio_delta(event)
            return

        if event_type in {
            "response.done",
            "response.audio.done",
        }:
            await self._handle_response_done(event)
            return

        if event_type.endswith("transcription.completed"):
            transcript = event.payload.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                self.status_fn(f"你说：{transcript.strip()}")
            return

        if event_type.endswith("audio_transcript.done"):
            transcript = event.payload.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                self.status_fn(f"Reachy：{transcript.strip()}")
            return

        if event_type == "error":
            self.status_fn(f"实时语音服务返回错误：{event.payload}")

    def handle_disconnect(self) -> None:
        self.player.interrupt()
        self._active_response_id = None
        self._active_generation = None
        if self.state.status is not ConversationStatus.STOPPED:
            self.state.transition(ConversationStatus.RECONNECTING)

    async def _handle_speech_started(self) -> None:
        if self.state.status not in {
            ConversationStatus.SPEAKING,
            ConversationStatus.THINKING,
        }:
            return

        response_was_active = self._active_response_id is not None
        self.player.interrupt()
        self._active_response_id = None
        self._active_generation = None
        self.state.transition(ConversationStatus.INTERRUPTED)

        if response_was_active and self.session is not None:
            await self.session.send_control(
                cancel_response_event(
                    f"event-{uuid.uuid4().hex}",
                )
            )

        self.state.transition(ConversationStatus.LISTENING)

    def _handle_audio_delta(self, event: ServerEvent) -> None:
        response_id = self._response_id(event)
        if (
            response_id is None
            or response_id != self._active_response_id
            or self._active_generation is None
            or not self.interruption.is_current(
                self._active_generation,
                response_id,
            )
        ):
            return

        delta = event.payload.get("delta")
        if not isinstance(delta, str) or not delta:
            return
        try:
            pcm_bytes = base64.b64decode(delta, validate=True)
        except (binascii.Error, ValueError):
            self.status_fn("忽略了一段格式无效的实时音频。")
            return

        if self.state.status in {
            ConversationStatus.LISTENING,
            ConversationStatus.THINKING,
        }:
            self.state.transition(ConversationStatus.SPEAKING)
        self.player.enqueue(
            self._active_generation,
            response_id,
            pcm_bytes,
        )

    async def _handle_response_done(
        self,
        event: ServerEvent,
    ) -> None:
        response_id = self._response_id(event)
        if (
            response_id is None
            or response_id != self._active_response_id
            or self._active_generation is None
        ):
            return
        generation = self._active_generation
        await self.player.wait_until_idle()
        if not self.interruption.is_current(generation, response_id):
            return

        self.interruption.invalidate_current()
        self._active_response_id = None
        self._active_generation = None
        if self.state.status in {
            ConversationStatus.SPEAKING,
            ConversationStatus.THINKING,
        }:
            self.state.transition(ConversationStatus.LISTENING)

    def _response_id(self, event: ServerEvent) -> str | None:
        return event.response_id or self._active_response_id
