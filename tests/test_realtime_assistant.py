from __future__ import annotations

import asyncio
import base64
import json
import threading

from robot.conversation_state import (
    ConversationState,
    ConversationStatus,
)
from robot.interruption import InterruptionController
from robot.realtime_assistant import RealtimeAssistant
from robot.realtime_protocol import ServerEvent


class FakeSession:
    def __init__(self) -> None:
        self.controls: list[dict[str, object]] = []

    async def send_control(self, message: str) -> bool:
        self.controls.append(json.loads(message))
        return True


class FakePlayer:
    def __init__(self, interruption: InterruptionController) -> None:
        self.interruption = interruption
        self.enqueued: list[tuple[int, str, bytes]] = []
        self.interrupt_count = 0
        self.wait_count = 0

    def enqueue(
        self,
        generation: int,
        response_id: str,
        pcm_bytes: bytes,
    ) -> None:
        self.enqueued.append((generation, response_id, pcm_bytes))

    def interrupt(self) -> int:
        self.interrupt_count += 1
        self.interruption.invalidate_current()
        return 0

    async def wait_until_idle(self) -> None:
        self.wait_count += 1


def event(
    event_type: str,
    *,
    response_id: str | None = None,
    **payload: object,
) -> ServerEvent:
    return ServerEvent(
        type=event_type,
        event_id=None,
        response_id=response_id,
        payload={"type": event_type, **payload},
    )


def test_audio_response_transitions_and_plays_only_current_generation() -> None:
    async def scenario() -> None:
        state = ConversationState()
        interruption = InterruptionController()
        player = FakePlayer(interruption)
        assistant = RealtimeAssistant(
            state=state,
            interruption=interruption,
            player=player,
        )

        await assistant.handle_event(event("session.updated"))
        await assistant.handle_event(
            event("input_audio_buffer.speech_stopped"),
        )
        await assistant.handle_event(
            event("response.created", response_id="response-1"),
        )
        await assistant.handle_event(
            event(
                "response.audio.delta",
                response_id="response-1",
                delta=base64.b64encode(b"pcm").decode("ascii"),
            )
        )

        assert state.status is ConversationStatus.SPEAKING
        assert player.enqueued[0][1:] == ("response-1", b"pcm")

        await assistant.handle_event(
            event("response.done", response_id="response-1"),
        )
        assert player.wait_count == 1
        assert state.status is ConversationStatus.LISTENING

    asyncio.run(scenario())


def test_barge_in_cancels_response_and_drops_late_audio() -> None:
    async def scenario() -> None:
        state = ConversationState(ConversationStatus.LISTENING)
        interruption = InterruptionController()
        player = FakePlayer(interruption)
        session = FakeSession()
        assistant = RealtimeAssistant(
            state=state,
            interruption=interruption,
            player=player,
            session=session,
        )

        await assistant.handle_event(
            event("response.created", response_id="response-2"),
        )
        await assistant.handle_event(
            event(
                "response.audio.delta",
                response_id="response-2",
                delta=base64.b64encode(b"first").decode("ascii"),
            )
        )
        await assistant.handle_event(
            event("input_audio_buffer.speech_started"),
        )

        assert player.interrupt_count == 1
        assert session.controls[-1]["type"] == "response.cancel"
        assert state.status is ConversationStatus.LISTENING

        await assistant.handle_event(
            event(
                "response.audio.delta",
                response_id="response-2",
                delta=base64.b64encode(b"late").decode("ascii"),
            )
        )
        assert [item[2] for item in player.enqueued] == [b"first"]

    asyncio.run(scenario())


def test_run_and_stop_release_every_component_idempotently() -> None:
    class LifecycleSession(FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def run(self, stop_event: asyncio.Event) -> None:
            self.started.set()
            await stop_event.wait()

        async def send_audio(self, _data: bytes) -> bool:
            return True

    class LifecycleStreamer:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.stopped = threading.Event()

        def run(self, stop_event, _send_audio) -> None:
            self.started.set()
            stop_event.wait(timeout=2.0)
            self.stopped.set()

    class LifecycleComponent:
        def __init__(self) -> None:
            self.started = 0
            self.stopped = 0

        def start(self) -> None:
            self.started += 1

        def stop(self) -> None:
            self.stopped += 1

        def interrupt(self) -> int:
            return 0

    async def scenario() -> None:
        state = ConversationState()
        interruption = InterruptionController()
        session = LifecycleSession()
        streamer = LifecycleStreamer()
        player = LifecycleComponent()
        motion = LifecycleComponent()
        assistant = RealtimeAssistant(
            state=state,
            interruption=interruption,
            player=player,
            session=session,
            streamer=streamer,
            motion=motion,
        )

        task = asyncio.create_task(assistant.run())
        await asyncio.wait_for(session.started.wait(), timeout=1.0)
        assert await asyncio.to_thread(streamer.started.wait, 1.0)

        assistant.stop()
        assistant.stop()
        await asyncio.wait_for(task, timeout=2.0)

        assert streamer.stopped.is_set()
        assert player.started == 1
        assert player.stopped == 1
        assert motion.started == 1
        assert motion.stopped == 1
        assert state.status is ConversationStatus.STOPPED

    asyncio.run(scenario())
