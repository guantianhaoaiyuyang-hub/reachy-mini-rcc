from __future__ import annotations

import asyncio
import inspect
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from robot.realtime_config import RealtimeConfig
from robot.realtime_credentials import (
    DeviceCredentials,
    WEBSOCKET_URL,
    websocket_headers,
)
from robot.realtime_protocol import (
    ServerEvent,
    append_audio_event,
    parse_server_event,
)


def reconnect_delays() -> Iterator[int]:
    delay = 1
    while True:
        yield delay
        delay = min(delay * 2, 30)


class RealtimeSession:
    def __init__(
        self,
        config: RealtimeConfig,
        credentials: DeviceCredentials | Any,
        *,
        on_event: Callable[
            [ServerEvent],
            None | Awaitable[None],
        ]
        | None = None,
        on_status: Callable[[str], None] = print,
        on_disconnect: Callable[[], None] | None = None,
        connect_fn: Callable[..., Any] = connect,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_fn: Callable[[], int] = lambda: secrets.randbelow(
            2_147_483_647
        ),
        time_fn: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.on_event = on_event or (lambda _event: None)
        self.on_status = on_status
        self.on_disconnect = on_disconnect or (lambda: None)
        self.connect_fn = connect_fn
        self.sleep_fn = sleep_fn
        self.random_fn = random_fn
        self.time_fn = time_fn
        self._websocket: Any | None = None
        self._ready = asyncio.Event()
        self._send_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    async def run(self, stop_event: asyncio.Event) -> None:
        device_secret = await self._get_device_secret()
        delays = reconnect_delays()
        while not stop_event.is_set():
            try:
                await self._run_connection(
                    stop_event,
                    device_secret,
                )
                if not stop_event.is_set():
                    raise ConnectionError("实时语音连接意外结束。")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._ready.clear()
                self.on_disconnect()
                if stop_event.is_set():
                    break
                delay = next(delays)
                self.on_status(
                    f"实时语音连接中断：{type(exc).__name__}；"
                    f"{delay} 秒后重连。"
                )
                await self.sleep_fn(delay)

    async def send_audio(self, pcm_bytes: bytes) -> bool:
        websocket = self._websocket
        if (
            not pcm_bytes
            or not self._ready.is_set()
            or websocket is None
        ):
            return False
        message = append_audio_event(
            pcm_bytes,
            f"event-{uuid.uuid4().hex}",
        )
        async with self._send_lock:
            await websocket.send(message)
        return True

    async def send_control(self, message: str) -> bool:
        websocket = self._websocket
        if not self._ready.is_set() or websocket is None:
            return False
        async with self._send_lock:
            await websocket.send(message)
        return True

    async def _get_device_secret(self) -> str:
        async_getter = getattr(
            self.credentials,
            "get_device_secret",
            None,
        )
        if async_getter is not None:
            value = async_getter()
            if inspect.isawaitable(value):
                return await value
            return value
        return await asyncio.to_thread(
            self.credentials.ensure_registered
        )

    async def _run_connection(
        self,
        stop_event: asyncio.Event,
        device_secret: str,
    ) -> None:
        query = urlencode(
            {
                "bot": self.config.bot_id,
                "wait_for_session_update": "true",
            }
        )
        url = f"{WEBSOCKET_URL}?{query}"
        headers = websocket_headers(
            self.config,
            device_secret,
            random_num=self.random_fn(),
            timestamp=self.time_fn(),
        )

        async with self.connect_fn(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
            close_timeout=5,
        ) as websocket:
            self._websocket = websocket
            try:
                while not stop_event.is_set():
                    raw = await websocket.recv()
                    if not isinstance(raw, str):
                        continue
                    event = parse_server_event(raw)
                    if event.type == "session.updated":
                        self._ready.set()
                    result = self.on_event(event)
                    if inspect.isawaitable(result):
                        await result
            finally:
                self._ready.clear()
                self._websocket = None
