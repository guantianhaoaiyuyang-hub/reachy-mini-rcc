from __future__ import annotations

import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

from robot.tts_playback import (
    TTSServiceError,
    check_tts_health,
    play_audio_realtime,
    prepare_audio,
    request_tts_wav,
)


def make_wav_bytes() -> bytes:
    samples = np.array([0.0, 0.25, -0.25, 0.0], dtype=np.float32)
    output = io.BytesIO()
    sf.write(output, samples, 24_000, format="WAV", subtype="FLOAT")
    return output.getvalue()


class StubTTSHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return

        body = json.dumps(self.server.health_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/tts":
            self.send_error(404)
            return

        content_length = int(self.headers["Content-Length"])
        request_body = self.rfile.read(content_length)
        self.server.received_payload = json.loads(request_body)

        body = self.server.wav_bytes
        self.send_response(200)
        self.send_header("Content-Type", self.server.tts_content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class TTSClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            StubTTSHandler,
        )
        cls.server.health_payload = {
            "status": "ready",
            "model": "test-model",
            "sample_rate": 24_000,
        }
        cls.server.wav_bytes = make_wav_bytes()
        cls.server.tts_content_type = "audio/wav"
        cls.server.received_payload = None
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def setUp(self) -> None:
        self.server.health_payload = {
            "status": "ready",
            "model": "test-model",
            "sample_rate": 24_000,
        }
        self.server.wav_bytes = make_wav_bytes()
        self.server.tts_content_type = "audio/wav"
        self.server.received_payload = None

    def test_health_returns_ready_service_metadata(self) -> None:
        health = check_tts_health(self.base_url)

        self.assertEqual(
            health,
            {
                "status": "ready",
                "model": "test-model",
                "sample_rate": 24_000,
            },
        )

    def test_request_sends_trimmed_text_and_returns_wav(self) -> None:
        wav_bytes = request_tts_wav(" 你好 ", self.base_url)

        self.assertEqual(self.server.received_payload, {"text": "你好"})
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])

    def test_unhealthy_service_is_rejected(self) -> None:
        self.server.health_payload = {
            "status": "loading",
            "model": "test-model",
            "sample_rate": 24_000,
        }

        with self.assertRaisesRegex(TTSServiceError, "尚未就绪"):
            check_tts_health(self.base_url)

    def test_empty_text_is_rejected_before_request(self) -> None:
        with self.assertRaisesRegex(TTSServiceError, "不能为空"):
            request_tts_wav("   ", self.base_url)

        self.assertIsNone(self.server.received_payload)

    def test_non_wav_response_is_rejected(self) -> None:
        self.server.tts_content_type = "application/json"

        with self.assertRaisesRegex(TTSServiceError, "不是 WAV"):
            request_tts_wav("你好", self.base_url)


class AudioPreparationTests(unittest.TestCase):
    @staticmethod
    def wav_bytes(
        samples: np.ndarray,
        sample_rate: int = 24_000,
    ) -> bytes:
        output = io.BytesIO()
        sf.write(
            output,
            samples.astype(np.float32),
            sample_rate,
            format="WAV",
            subtype="FLOAT",
        )
        return output.getvalue()

    def test_mono_input_is_repeated_to_stereo(self) -> None:
        source = np.array([0.0, 0.25, -0.25, 0.0], dtype=np.float32)

        audio, duration = prepare_audio(
            self.wav_bytes(source),
            target_sample_rate=24_000,
            target_channels=2,
        )

        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(audio.shape, (4, 2))
        np.testing.assert_allclose(audio[:, 0], source, atol=1e-6)
        np.testing.assert_allclose(audio[:, 1], source, atol=1e-6)
        self.assertAlmostEqual(duration, 4 / 24_000)

    def test_stereo_input_is_averaged_to_mono(self) -> None:
        source = np.array(
            [
                [0.2, 0.4],
                [-0.4, 0.2],
            ],
            dtype=np.float32,
        )

        audio, _ = prepare_audio(
            self.wav_bytes(source),
            target_sample_rate=24_000,
            target_channels=1,
        )

        expected = np.array([[0.3], [-0.1]], dtype=np.float32)
        np.testing.assert_allclose(audio, expected, atol=1e-6)

    def test_resampling_preserves_duration(self) -> None:
        source = np.array([0.0, 0.25, -0.25, 0.0], dtype=np.float32)

        audio, duration = prepare_audio(
            self.wav_bytes(source, sample_rate=24_000),
            target_sample_rate=48_000,
            target_channels=1,
        )

        self.assertEqual(audio.shape, (8, 1))
        self.assertAlmostEqual(duration, 4 / 24_000)

    def test_peak_is_scaled_down_to_safety_limit(self) -> None:
        source = np.array([0.0, 0.8, -0.4, 0.0], dtype=np.float32)

        audio, _ = prepare_audio(
            self.wav_bytes(source),
            target_sample_rate=24_000,
            target_channels=1,
            max_peak=0.30,
        )

        self.assertLessEqual(float(np.max(np.abs(audio))), 0.300001)
        self.assertAlmostEqual(float(audio[1, 0]), 0.30, places=5)

    def test_gain_boosts_quiet_speech_before_peak_limiting(self) -> None:
        source = np.array([0.0, 0.02, -0.02, 0.0], dtype=np.float32)

        audio, _ = prepare_audio(
            self.wav_bytes(source),
            target_sample_rate=24_000,
            target_channels=1,
            gain=10.0,
            max_peak=0.30,
        )

        expected = np.array([[0.0], [0.2], [-0.2], [0.0]], dtype=np.float32)
        np.testing.assert_allclose(audio, expected, atol=1e-6)

    def test_invalid_wav_is_rejected(self) -> None:
        with self.assertRaisesRegex(TTSServiceError, "无法解码"):
            prepare_audio(
                b"not a wav file",
                target_sample_rate=24_000,
                target_channels=1,
            )

    def test_invalid_target_channels_are_rejected(self) -> None:
        with self.assertRaisesRegex(TTSServiceError, "声道"):
            prepare_audio(
                self.wav_bytes(np.array([0.0], dtype=np.float32)),
                target_sample_rate=24_000,
                target_channels=0,
            )


class RecordingMedia:
    def __init__(self, fail_on_push: bool = False) -> None:
        self.fail_on_push = fail_on_push
        self.started = 0
        self.stopped = 0
        self.chunks: list[np.ndarray] = []

    def start_playing(self) -> None:
        self.started += 1

    def push_audio_sample(self, chunk: np.ndarray) -> None:
        if self.fail_on_push:
            raise RuntimeError("diagnostic push failure")
        self.chunks.append(chunk.copy())

    def stop_playing(self) -> None:
        self.stopped += 1


class PlaybackTests(unittest.TestCase):
    def test_audio_is_sent_in_twenty_millisecond_chunks(self) -> None:
        media = RecordingMedia()
        audio = np.arange(640 * 2, dtype=np.float32).reshape(640, 2)
        sleeps: list[float] = []

        play_audio_realtime(
            media,
            audio,
            sample_rate=16_000,
            chunk_ms=20,
            startup_delay=1.5,
            tail_delay=1.0,
            sleep_fn=sleeps.append,
        )

        self.assertEqual(media.started, 1)
        self.assertEqual(media.stopped, 1)
        self.assertEqual([chunk.shape for chunk in media.chunks], [(320, 2)] * 2)
        np.testing.assert_array_equal(
            np.concatenate(media.chunks, axis=0),
            audio,
        )
        self.assertEqual(sleeps, [1.5, 0.02, 0.02, 1.0])

    def test_playback_is_stopped_when_a_push_fails(self) -> None:
        media = RecordingMedia(fail_on_push=True)
        audio = np.zeros((320, 2), dtype=np.float32)

        with self.assertRaisesRegex(RuntimeError, "push failure"):
            play_audio_realtime(
                media,
                audio,
                sample_rate=16_000,
                sleep_fn=lambda _: None,
            )

        self.assertEqual(media.started, 1)
        self.assertEqual(media.stopped, 1)


if __name__ == "__main__":
    unittest.main()
