from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from robot.realtime_config import RealtimeConfig
from robot.realtime_protocol import ServerEvent
from robot.realtime_session import (
    RealtimeSession,
    reconnect_delays,
)


def make_config(tmp_path: Path) -> RealtimeConfig:
    return RealtimeConfig(
        instance_id="instance",
        product_key="product",
        product_secret="0123456789abcdef-secret",
        bot_id="bot id",
        device_name="reachy-mini-01",
        hardware_id="reachy-hardware-01",
        cache_path=tmp_path / "device.json",
    )


class FakeCredentials:
    async def get_device_secret(self) -> str:
        return "device-secret-value"


class FakeWebSocket:
    def __init__(
        self,
        incoming: list[str],
        stop_event: asyncio.Event,
    ) -> None:
        self.incoming = incoming
        self.stop_event = stop_event
        self.sent: list[str] = []

    async def recv(self) -> str:
        value = self.incoming.pop(0)
        if not self.incoming:
            self.stop_event.set()
        return value

    async def send(self, value: str) -> None:
        self.sent.append(value)


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeConnector:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeConnection:
        self.calls.append((url, kwargs))
        return FakeConnection(self.websocket)


def test_reconnect_delays_are_bounded_exponential() -> None:
    delays = reconnect_delays()

    assert [next(delays) for _ in range(8)] == [
        1,
        2,
        4,
        8,
        16,
        30,
        30,
        30,
    ]


def test_audio_is_dropped_before_session_is_ready(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = RealtimeSession(
            make_config(tmp_path),
            FakeCredentials(),
        )

        assert not await session.send_audio(b"\x00\x01")

    asyncio.run(scenario())


def test_signed_connection_receives_events_and_sends_audio(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        stop_event = asyncio.Event()
        websocket = FakeWebSocket(
            [
                json.dumps(
                    {
                        "type": "session.created",
                        "event_id": "created",
                        "session": {"input_audio_format": "pcm16"},
                    }
                ),
                json.dumps(
                    {
                        "type": "session.updated",
                        "event_id": "updated",
                        "session": {"input_audio_format": "pcm16"},
                    }
                ),
            ],
            stop_event,
        )
        connector = FakeConnector(websocket)
        events: list[ServerEvent] = []
        session: RealtimeSession

        async def on_event(event: ServerEvent) -> None:
            events.append(event)
            if event.type == "session.updated":
                assert await session.send_audio(b"\x00\x01")

        session = RealtimeSession(
            make_config(tmp_path),
            FakeCredentials(),
            on_event=on_event,
            connect_fn=connector,
            random_fn=lambda: 73,
            time_fn=lambda: 1_720_000_000,
        )

        await session.run(stop_event)

        assert [event.type for event in events] == [
            "session.created",
            "session.updated",
        ]
        assert len(connector.calls) == 1
        url, options = connector.calls[0]
        assert (
            url
            == "wss://ai-gateway.vei.volces.com/v1/realtime"
            "?bot=bot+id&wait_for_session_update=true"
        )
        assert options["additional_headers"]["X-Device-Name"] == (
            "reachy-mini-01"
        )
        assert options["additional_headers"]["X-Timestamp"] == (
            "1720000000"
        )
        sent = json.loads(websocket.sent[0])
        assert sent["type"] == "input_audio_buffer.append"
        assert sent["audio"] == "AAE="

    asyncio.run(scenario())


def test_disconnect_callback_runs_before_retry_sleep(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        stop_event = asyncio.Event()
        order: list[str] = []
        attempts = 0

        class BrokenConnection:
            async def __aenter__(self):
                raise OSError("network down")

            async def __aexit__(self, *_args: object) -> None:
                return None

        class Connector:
            def __call__(self, _url: str, **_kwargs: Any):
                nonlocal attempts
                attempts += 1
                return BrokenConnection()

        async def fake_sleep(delay: float) -> None:
            order.append(f"sleep:{delay}")
            stop_event.set()

        def on_disconnect() -> None:
            order.append("disconnect")

        session = RealtimeSession(
            make_config(tmp_path),
            FakeCredentials(),
            connect_fn=Connector(),
            sleep_fn=fake_sleep,
            on_disconnect=on_disconnect,
        )

        await session.run(stop_event)

        assert attempts == 1
        assert order == ["disconnect", "sleep:1"]

    asyncio.run(scenario())
