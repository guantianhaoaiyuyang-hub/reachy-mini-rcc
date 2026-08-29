from __future__ import annotations

import base64
import json
import unittest
from email.message import Message
from typing import Any

from robot.volcengine_tts import (
    VolcengineTTSClient,
    VolcengineTTSConfig,
    VolcengineTTSError,
)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class RecordingOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request = None
        self.timeout = None

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        return self.response


class VolcengineTTSConfigTests(unittest.TestCase):
    def test_config_reads_required_values_and_chinese_voice(self) -> None:
        config = VolcengineTTSConfig.from_mapping(
            {
                "VOLCENGINE_TTS_APP_ID": "app-id",
                "VOLCENGINE_TTS_ACCESS_TOKEN": "access-token",
                "VOLCENGINE_TTS_RESOURCE_ID": "seed-tts-2.0",
                "VOLCENGINE_TTS_VOICE_TYPE": "zh_male_m191_uranus_bigtts",
            }
        )

        self.assertEqual(config.app_id, "app-id")
        self.assertEqual(config.resource_id, "seed-tts-2.0")
        self.assertEqual(
            config.voice_type,
            "zh_male_m191_uranus_bigtts",
        )

    def test_missing_token_is_rejected_without_echoing_values(self) -> None:
        with self.assertRaisesRegex(VolcengineTTSError, "ACCESS_TOKEN"):
            VolcengineTTSConfig.from_mapping(
                {
                    "VOLCENGINE_TTS_APP_ID": "app-id",
                    "VOLCENGINE_TTS_RESOURCE_ID": "seed-tts-2.0",
                    "VOLCENGINE_TTS_VOICE_TYPE": "zh_male_m191_uranus_bigtts",
                }
            )


class VolcengineTTSClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = VolcengineTTSConfig(
            app_id="app-id",
            access_token="access-token",
            resource_id="seed-tts-2.0",
            voice_type="zh_male_m191_uranus_bigtts",
        )

    def test_client_posts_v3_request_and_decodes_all_audio_chunks(self) -> None:
        wav_prefix = b"RIFF" + b"first"
        wav_suffix = b"second"
        response_body = (
            json.dumps({"code": 0, "data": base64.b64encode(wav_prefix).decode()})
            + json.dumps({"code": 0, "data": base64.b64encode(wav_suffix).decode()})
            + json.dumps({"code": 20000000, "message": "ok"})
        ).encode("utf-8")
        opener = RecordingOpener(FakeResponse(response_body))
        client = VolcengineTTSClient(self.config, opener=opener)

        result = client.synthesize_wav("  你好，Reachy。  ", timeout=12.0)

        self.assertEqual(result, wav_prefix + wav_suffix)
        self.assertEqual(opener.timeout, 12.0)
        self.assertEqual(
            opener.request.full_url,
            "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        )
        self.assertEqual(opener.request.get_header("X-api-app-id"), "app-id")
        self.assertEqual(
            opener.request.get_header("X-api-access-key"),
            "access-token",
        )
        self.assertEqual(
            opener.request.get_header("X-api-resource-id"),
            "seed-tts-2.0",
        )

        payload = json.loads(opener.request.data.decode("utf-8"))
        self.assertEqual(payload["user"]["uid"], "reachy-mini")
        self.assertEqual(payload["req_params"]["text"], "你好，Reachy。")
        self.assertEqual(
            payload["req_params"]["speaker"],
            "zh_male_m191_uranus_bigtts",
        )
        self.assertEqual(payload["req_params"]["audio_params"]["format"], "wav")
        self.assertEqual(
            payload["req_params"]["audio_params"]["sample_rate"],
            24000,
        )

    def test_service_error_does_not_return_invalid_audio(self) -> None:
        response_body = json.dumps(
            {"code": 55000000, "message": "speaker permission denied"}
        ).encode("utf-8")
        client = VolcengineTTSClient(
            self.config,
            opener=RecordingOpener(FakeResponse(response_body)),
        )

        with self.assertRaisesRegex(VolcengineTTSError, "55000000"):
            client.synthesize_wav("你好")


if __name__ == "__main__":
    unittest.main()
