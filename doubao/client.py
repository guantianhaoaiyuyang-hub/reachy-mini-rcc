from __future__ import annotations

import asyncio
import uuid
from typing import Any

import websockets

from doubao.config import DoubaoConfig, load_config
from doubao.protocol import (
    Event,
    MessageType,
    ServerPacket,
    build_audio_event,
    build_json_event,
    event_name,
    parse_server_packet,
)


class DoubaoError(RuntimeError):
    """豆包实时语音客户端错误。"""


class DoubaoClient:
    def __init__(self, config: DoubaoConfig | None = None) -> None:
        self.config = config or load_config()
        self.websocket: Any | None = None
        self.connect_id: str | None = None
        self.session_id: str | None = None
        self.connection_started = False
        self.session_started = False

    def _headers(self) -> dict[str, str]:
        self.connect_id = str(uuid.uuid4())
        return {
            "X-Api-App-ID": self.config.app_id,
            "X-Api-Access-Key": self.config.access_token,
            "X-Api-Resource-Id": self.config.resource_id,
            "X-Api-App-Key": self.config.app_key,
            "X-Api-Connect-Id": self.connect_id,
        }

    async def connect(self) -> ServerPacket:
        if self.websocket is not None:
            raise DoubaoError("WebSocket 已经建立，请勿重复连接")

        print("正在连接豆包实时语音服务……")
        self.websocket = await websockets.connect(
            self.config.ws_url,
            additional_headers=self._headers(),
            open_timeout=15,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        )

        print("WebSocket 握手成功")
        print("Connect ID:", self.connect_id)

        await self.websocket.send(
            build_json_event(Event.START_CONNECTION, {})
        )
        print("StartConnection 已发送")

        response = await self.receive_packet(timeout=15)
        if response.event != Event.CONNECTION_STARTED:
            raise DoubaoError(
                "建立连接失败："
                f"{event_name(response.event)}，"
                f"payload={response.json_payload()}"
            )

        self.connection_started = True
        print("ConnectionStarted 已收到")
        print("服务端 Connect ID:", response.connect_id)
        return response

    def _start_session_payload(self) -> dict[str, Any]:
        return {
            "asr": {
                "audio_info": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "channel": 1,
                    "bits": 16,
                },
                "extra": {
                    "end_smooth_window_ms": 800,
                },
            },
            "tts": {
                "speaker": "zh_female_vv_jupiter_bigtts",
                "audio_config": {
                    "channel": 1,
                    "format": "pcm_s16le",
                    "sample_rate": 24000,
                },
                "extra": {},
            },
            "dialog": {
                "bot_name": "Reachy Mini",
                "system_role": (
                    "你是 Reachy Mini 机器人。"
                    "你友好、自然、反应迅速，使用简洁中文交流。"
                ),
                "speaking_style": (
                    "语气自然亲切，回答简短，适合现场人机互动。"
                ),
                "extra": {
                    "input_mod": "keep_alive",
                    "model": self.config.model,
                    "enable_loudness_norm": True,
                },
            },
        }

    async def start_session(self) -> ServerPacket:
        if self.websocket is None or not self.connection_started:
            raise DoubaoError("请先调用 connect()")
        if self.session_started:
            raise DoubaoError("当前会话已经启动")

        self.session_id = str(uuid.uuid4())
        await self.websocket.send(
            build_json_event(
                Event.START_SESSION,
                self._start_session_payload(),
                session_id=self.session_id,
            )
        )

        print("StartSession 已发送")
        print("本地 Session ID:", self.session_id)

        while True:
            response = await self.receive_packet(timeout=20)
            payload = response.json_payload()

            print("收到事件:", response.event, event_name(response.event))
            if payload is not None:
                print("事件内容:", payload)

            if response.event == Event.SESSION_STARTED:
                self.session_started = True
                if response.session_id:
                    self.session_id = response.session_id
                print("SessionStarted 已收到")
                print("服务端 Session ID:", self.session_id)
                return response

            if response.event in {
                Event.SESSION_FAILED,
                Event.CONNECTION_FAILED,
            }:
                raise DoubaoError(
                    "启动会话失败："
                    f"{event_name(response.event)}，payload={payload}"
                )

    async def send_audio(self, audio: bytes) -> None:
        if (
            self.websocket is None
            or not self.session_started
            or self.session_id is None
        ):
            raise DoubaoError("请先建立并启动会话")
        if not audio:
            return

        await self.websocket.send(
            build_audio_event(
                Event.TASK_REQUEST,
                audio,
                session_id=self.session_id,
            )
        )

    async def receive_packet(
        self,
        *,
        timeout: float | None = None,
    ) -> ServerPacket:
        if self.websocket is None:
            raise DoubaoError("WebSocket 尚未建立")

        call = self.websocket.recv()
        raw = (
            await call
            if timeout is None
            else await asyncio.wait_for(call, timeout=timeout)
        )

        if not isinstance(raw, bytes):
            raise DoubaoError(
                f"预期收到二进制数据，实际收到：{type(raw).__name__}"
            )

        packet = parse_server_packet(raw)
        if packet.message_type == MessageType.ERROR:
            raise DoubaoError(f"服务端错误：{packet.json_payload()}")
        return packet

    async def finish_session(self) -> None:
        if (
            self.websocket is None
            or not self.session_started
            or self.session_id is None
        ):
            return

        await self.websocket.send(
            build_json_event(
                Event.FINISH_SESSION,
                {},
                session_id=self.session_id,
            )
        )
        self.session_started = False
        print("FinishSession 已发送")

    async def finish_connection(self) -> None:
        if self.websocket is None:
            return

        try:
            if self.connection_started:
                await self.websocket.send(
                    build_json_event(Event.FINISH_CONNECTION, {})
                )
                print("FinishConnection 已发送")
        finally:
            await self.websocket.close()
            self.websocket = None
            self.connection_started = False
            self.session_started = False
            self.session_id = None
            print("WebSocket 已关闭")

    async def close(self) -> None:
        try:
            await self.finish_session()
        finally:
            await self.finish_connection()

    async def __aenter__(self) -> "DoubaoClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.close()
