from __future__ import annotations

import json

import pytest

from robot.realtime_protocol import (
    ProtocolError,
    append_audio_event,
    cancel_response_event,
    clear_audio_event,
    parse_server_event,
)


def test_append_audio_event_base64_encodes_bytes() -> None:
    raw = append_audio_event(b"\x00\x01\xff", "event-1")

    assert json.loads(raw) == {
        "type": "input_audio_buffer.append",
        "event_id": "event-1",
        "audio": "AAH/",
    }


def test_control_event_builders_use_compact_valid_json() -> None:
    assert json.loads(cancel_response_event("event-2")) == {
        "type": "response.cancel",
        "event_id": "event-2",
    }
    assert json.loads(clear_audio_event("event-3")) == {
        "type": "input_audio_buffer.clear",
        "event_id": "event-3",
    }


def test_parse_audio_delta_keeps_response_id_and_payload() -> None:
    event = parse_server_event(
        json.dumps(
            {
                "type": "response.audio.delta",
                "event_id": "event-4",
                "response_id": "resp-1",
                "delta": "AAE=",
            }
        )
    )

    assert event.type == "response.audio.delta"
    assert event.event_id == "event-4"
    assert event.response_id == "resp-1"
    assert event.payload["delta"] == "AAE="


@pytest.mark.parametrize(
    ("event_type", "response_id"),
    [
        ("session.created", None),
        ("session.updated", None),
        ("input_audio_buffer.speech_started", None),
        ("input_audio_buffer.speech_stopped", None),
        ("response.created", "resp-2"),
        ("response.audio_transcript.delta", "resp-2"),
        ("response.audio_transcript.done", "resp-2"),
        ("response.audio.done", "resp-2"),
        ("response.done", "resp-2"),
        ("future.server.event", None),
    ],
)
def test_parse_known_and_unknown_events_tolerantly(
    event_type: str,
    response_id: str | None,
) -> None:
    payload: dict[str, object] = {
        "type": event_type,
        "event_id": "event-x",
    }
    if event_type == "response.created":
        payload["response"] = {"id": response_id}
    elif event_type == "response.done":
        payload["response"] = {
            "id": response_id,
            "status": "completed",
        }
    elif response_id is not None:
        payload["response_id"] = response_id

    event = parse_server_event(json.dumps(payload))

    assert event.type == event_type
    assert event.response_id == response_id


def test_parse_server_error_retains_safe_details() -> None:
    event = parse_server_event(
        json.dumps(
            {
                "type": "error",
                "event_id": "event-error",
                "error": {
                    "code": "invalid_event",
                    "message": "bad request",
                },
            }
        )
    )

    assert event.payload["error"]["code"] == "invalid_event"


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        "{}",
        '{"type": 3}',
    ],
)
def test_parse_rejects_malformed_events(raw: str) -> None:
    with pytest.raises(ProtocolError):
        parse_server_event(raw)
