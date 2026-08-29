from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class MessageType(IntEnum):
    FULL_CLIENT_REQUEST = 0x1
    AUDIO_ONLY_REQUEST = 0x2
    FULL_SERVER_RESPONSE = 0x9
    AUDIO_ONLY_RESPONSE = 0xB
    ERROR = 0xF


class Event(IntEnum):
    # 客户端事件
    START_CONNECTION = 1
    FINISH_CONNECTION = 2
    START_SESSION = 100
    FINISH_SESSION = 102
    TASK_REQUEST = 200

    # 服务端连接事件
    CONNECTION_STARTED = 50
    CONNECTION_FAILED = 51
    CONNECTION_FINISHED = 52

    # 服务端会话事件
    SESSION_STARTED = 150
    SESSION_FINISHED = 152
    SESSION_FAILED = 153
    USAGE_RESPONSE = 154

    # TTS 事件
    TTS_SENTENCE_START = 350
    TTS_SENTENCE_END = 351
    TTS_RESPONSE = 352
    TTS_ENDED = 359

    # ASR 事件
    ASR_INFO = 450
    ASR_RESPONSE = 451
    ASR_ENDED = 459

    # 对话事件
    CHAT_RESPONSE = 550
    CHAT_ENDED = 559


@dataclass(frozen=True)
class ServerPacket:
    message_type: int
    flags: int
    serialization: int
    compression: int
    event: int | None
    connect_id: str | None
    session_id: str | None
    payload: bytes

    def json_payload(self) -> Any | None:
        if not self.payload:
            return None
        try:
            return json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None


def _header(
    message_type: MessageType,
    flags: int,
    serialization: int,
    compression: int = 0,
) -> bytes:
    return bytes([
        0x11,
        (int(message_type) << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])


def build_json_event(
    event: int,
    payload: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> bytes:
    payload_bytes = json.dumps(
        payload or {},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    packet = bytearray(
        _header(
            MessageType.FULL_CLIENT_REQUEST,
            flags=0x4,
            serialization=0x1,
        )
    )
    packet.extend(struct.pack(">I", int(event)))

    if session_id is not None:
        session_bytes = session_id.encode("utf-8")
        packet.extend(struct.pack(">I", len(session_bytes)))
        packet.extend(session_bytes)

    packet.extend(struct.pack(">I", len(payload_bytes)))
    packet.extend(payload_bytes)
    return bytes(packet)


def build_audio_event(
    event: int,
    audio: bytes,
    *,
    session_id: str,
) -> bytes:
    session_bytes = session_id.encode("utf-8")
    packet = bytearray(
        _header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0x4,
            serialization=0x0,
        )
    )
    packet.extend(struct.pack(">I", int(event)))
    packet.extend(struct.pack(">I", len(session_bytes)))
    packet.extend(session_bytes)
    packet.extend(struct.pack(">I", len(audio)))
    packet.extend(audio)
    return bytes(packet)


def parse_server_packet(data: bytes) -> ServerPacket:
    if len(data) < 8:
        raise ValueError(f"数据包过短：{len(data)} 字节")

    version = data[0] >> 4
    header_words = data[0] & 0x0F
    if version != 1:
        raise ValueError(f"不支持的协议版本：{version}")

    header_size = header_words * 4
    if header_size < 4 or len(data) < header_size:
        raise ValueError("无效的 Header 长度")

    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F

    offset = header_size
    event: int | None = None
    connect_id: str | None = None
    session_id: str | None = None

    if flags == 0x4:
        if len(data) < offset + 4:
            raise ValueError("数据包缺少事件 ID")
        event = struct.unpack_from(">I", data, offset)[0]
        offset += 4

        if event in {
            Event.CONNECTION_STARTED,
            Event.CONNECTION_FAILED,
            Event.CONNECTION_FINISHED,
        }:
            if len(data) < offset + 4:
                raise ValueError("数据包缺少 Connect ID 长度")
            connect_size = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            if len(data) < offset + connect_size:
                raise ValueError("Connect ID 不完整")
            connect_id = data[offset:offset + connect_size].decode("utf-8")
            offset += connect_size

        elif event >= 100:
            if len(data) < offset + 4:
                raise ValueError("数据包缺少 Session ID 长度")
            session_size = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            if len(data) < offset + session_size:
                raise ValueError("Session ID 不完整")
            session_id = data[offset:offset + session_size].decode("utf-8")
            offset += session_size

    error_code: int | None = None
    if message_type == MessageType.ERROR:
        if len(data) < offset + 4:
            raise ValueError("错误数据包缺少错误码")
        error_code = struct.unpack_from(">I", data, offset)[0]
        offset += 4

    if len(data) < offset + 4:
        raise ValueError("数据包缺少 Payload 长度")

    payload_size = struct.unpack_from(">I", data, offset)[0]
    offset += 4
    if len(data) < offset + payload_size:
        raise ValueError(
            f"Payload 不完整：声明 {payload_size} 字节，"
            f"实际剩余 {len(data) - offset} 字节"
        )

    payload = data[offset:offset + payload_size]

    if error_code is not None:
        error_data: dict[str, Any] = {"error_code": error_code}
        try:
            decoded = json.loads(payload.decode("utf-8"))
            if isinstance(decoded, dict):
                error_data.update(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            error_data["raw_payload"] = payload.hex()
        payload = json.dumps(error_data, ensure_ascii=False).encode("utf-8")

    return ServerPacket(
        message_type=message_type,
        flags=flags,
        serialization=serialization,
        compression=compression,
        event=event,
        connect_id=connect_id,
        session_id=session_id,
        payload=payload,
    )


def event_name(event: int | None) -> str:
    if event is None:
        return "NO_EVENT"
    try:
        return Event(event).name
    except ValueError:
        return f"UNKNOWN_EVENT_{event}"
