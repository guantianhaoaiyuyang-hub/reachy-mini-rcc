from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any


class ProtocolError(RuntimeError):
    """实时语音事件不是合法的协议消息。"""


@dataclass(frozen=True)
class ServerEvent:
    type: str
    event_id: str | None
    response_id: str | None
    payload: dict[str, Any]


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def append_audio_event(pcm_bytes: bytes, event_id: str) -> str:
    return _serialize(
        {
            "type": "input_audio_buffer.append",
            "event_id": event_id,
            "audio": base64.b64encode(pcm_bytes).decode("ascii"),
        }
    )


def cancel_response_event(event_id: str) -> str:
    return _serialize(
        {
            "type": "response.cancel",
            "event_id": event_id,
        }
    )


def clear_audio_event(event_id: str) -> str:
    return _serialize(
        {
            "type": "input_audio_buffer.clear",
            "event_id": event_id,
        }
    )


def parse_server_event(raw: str) -> ServerEvent:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("服务端返回的事件不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("服务端事件必须是 JSON 对象。")

    event_type = payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise ProtocolError("服务端事件缺少字符串类型的 type。")

    event_id = payload.get("event_id")
    if not isinstance(event_id, str):
        event_id = None

    response_id = payload.get("response_id")
    if not isinstance(response_id, str):
        response_id = None

    response = payload.get("response")
    if response_id is None and isinstance(response, dict):
        nested_id = response.get("id")
        if isinstance(nested_id, str):
            response_id = nested_id

    return ServerEvent(
        type=event_type,
        event_id=event_id,
        response_id=response_id,
        payload=payload,
    )
