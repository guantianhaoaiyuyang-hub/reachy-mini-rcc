from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from robot.microphone import record_audio
from robot.tts_playback import (
    play_audio_realtime,
    prepare_audio,
    request_tts_wav,
)


TTS_BASE_URL = "http://127.0.0.1:8123"
TTS_TIMEOUT_SECONDS = 180.0
SPEECH_GAIN = 10.0
MAX_PEAK = 0.30
PLAYBACK_CHUNK_MS = 20


@dataclass(frozen=True)
class TurnOutcome:
    user_text: str
    assistant_text: str
    spoken: bool


class VoiceAssistant:
    """组织 Reachy 的一轮录音、理解、回答和播放。"""

    def __init__(
        self,
        *,
        media: Any,
        transcriber: Any,
        brain: Any,
        input_sample_rate: int,
        output_sample_rate: int,
        output_channels: int,
        tts_base_url: str = TTS_BASE_URL,
        record_seconds: float = 3.0,
        recorder: Callable[..., np.ndarray] = record_audio,
        tts_request: Callable[..., bytes] = request_tts_wav,
        audio_preparer: Callable[
            ...,
            tuple[np.ndarray, float],
        ] = prepare_audio,
        player: Callable[..., None] = play_audio_realtime,
        speech_motion_factory: Callable[[], Any] | None = None,
        status_fn: Callable[[str], None] = print,
    ) -> None:
        self.media = media
        self.transcriber = transcriber
        self.brain = brain
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.output_channels = output_channels
        self.tts_base_url = tts_base_url
        self.record_seconds = record_seconds
        self.recorder = recorder
        self.tts_request = tts_request
        self.audio_preparer = audio_preparer
        self.player = player
        self.speech_motion_factory = speech_motion_factory
        self.status_fn = status_fn

    def run_turn(self) -> TurnOutcome:
        self.status_fn(
            f"正在录音 {self.record_seconds:.0f} 秒，请开始说话……"
        )
        audio = self.recorder(
            self.media,
            self.record_seconds,
        )

        self.status_fn("正在识别语音……")
        user_text = self.transcriber.transcribe(
            audio,
            self.input_sample_rate,
        )
        if not user_text:
            return TurnOutcome("", "", False)

        self.status_fn(f"你说：{user_text}")
        self.status_fn("正在请求 DeepSeek……")
        answer = self.brain.chat(user_text)
        self.status_fn(f"Reachy：{answer}")

        self.status_fn("正在生成中文语音……")
        wav_bytes = self.tts_request(
            answer,
            self.tts_base_url,
            timeout=TTS_TIMEOUT_SECONDS,
        )
        prepared_audio, _ = self.audio_preparer(
            wav_bytes,
            target_sample_rate=self.output_sample_rate,
            target_channels=self.output_channels,
            max_peak=MAX_PEAK,
            gain=SPEECH_GAIN,
        )

        motion = (
            self.speech_motion_factory()
            if self.speech_motion_factory is not None
            else None
        )
        if motion is not None:
            motion.start()

        self.status_fn("正在播放……")
        try:
            self.player(
                self.media,
                prepared_audio,
                sample_rate=self.output_sample_rate,
                chunk_ms=PLAYBACK_CHUNK_MS,
            )
        finally:
            if motion is not None:
                motion.stop_and_return()

        return TurnOutcome(
            user_text=user_text,
            assistant_text=answer,
            spoken=True,
        )


def run_interactive_loop(
    assistant: Any,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    output_fn("按回车开始录音；输入 q 后回车退出。")

    while True:
        command = input_fn("\n等待命令：").strip().lower()
        if command == "q":
            output_fn("语音助手已退出。")
            return

        try:
            outcome = assistant.run_turn()
        except Exception as exc:
            output_fn(
                f"本轮失败：{type(exc).__name__}: {exc}"
            )
            continue

        if not outcome.user_text:
            output_fn("没有识别到有效语音，请重试。")
