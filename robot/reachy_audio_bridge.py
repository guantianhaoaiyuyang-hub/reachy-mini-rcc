from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
from scipy.signal import resample_poly


DOUBAO_INPUT_RATE = 16000
DOUBAO_OUTPUT_RATE = 24000


class ReachyAudioBridge:
    """
    Reachy Mini 与豆包之间的实时音频转换桥。

    Reachy 输入：
    - 16000Hz
    - float32
    - 双声道，典型形状 (320, 2)

    豆包输入：
    - 16000Hz
    - PCM16 小端序
    - 单声道

    豆包输出：
    - 24000Hz
    - PCM16 小端序
    - 单声道

    Reachy 输出：
    - 16000Hz
    - float32
    - 单声道或双声道
    """

    def __init__(self, mini: Any) -> None:
        self.mini = mini
        self.input_rate = int(
            mini.media.get_input_audio_samplerate()
        )
        self.output_rate = int(
            mini.media.get_output_audio_samplerate()
        )

        self.tts_playing = asyncio.Event()
        self.closed = False

    def start(self) -> None:
        if self.input_rate != DOUBAO_INPUT_RATE:
            raise RuntimeError(
                f"Reachy输入采样率应为16000Hz，实际为{self.input_rate}Hz"
            )

        self.mini.media.start_recording()
        self.mini.media.start_playing()

        try:
            self.mini.media.set_max_output_buffers(100)
        except Exception:
            pass

        print("Reachy麦克风和扬声器已启动")
        print("Reachy输入采样率：", self.input_rate)
        print("Reachy输出采样率：", self.output_rate)

    def stop(self) -> None:
        self.closed = True

        try:
            self.mini.media.stop_recording()
        except Exception as exc:
            print("停止Reachy麦克风时提示：", exc)

        try:
            self.mini.media.stop_playing()
        except Exception as exc:
            print("停止Reachy扬声器时提示：", exc)

        print("Reachy音频设备已停止")

    def microphone_sample_to_pcm16(
        self,
        sample: Any,
    ) -> bytes | None:
        if sample is None:
            return None

        data = np.asarray(sample, dtype=np.float32)
        if data.size == 0:
            return None

        if data.ndim == 2:
            data = np.mean(data, axis=1)
        elif data.ndim != 1:
            data = data.reshape(-1)

        data = np.nan_to_num(
            data,
            nan=0.0,
            posinf=1.0,
            neginf=-1.0,
        )
        data = np.clip(data, -1.0, 1.0)

        pcm16 = np.asarray(
            np.round(data * 32767.0),
            dtype="<i2",
        )
        return pcm16.tobytes()

    def doubao_pcm16_to_reachy(
        self,
        pcm: bytes,
    ) -> np.ndarray:
        if not pcm:
            return np.empty((0,), dtype=np.float32)

        int16_audio = np.frombuffer(
            pcm,
            dtype="<i2",
        )

        audio = (
            int16_audio.astype(np.float32)
            / 32768.0
        )

        if DOUBAO_OUTPUT_RATE != self.output_rate:
            audio = resample_poly(
                audio,
                self.output_rate,
                DOUBAO_OUTPUT_RATE,
            ).astype(np.float32, copy=False)

        return np.ascontiguousarray(audio, dtype=np.float32)

    def play_doubao_pcm(self, pcm: bytes) -> None:
        audio = self.doubao_pcm16_to_reachy(pcm)
        if audio.size == 0:
            return

        self.mini.media.push_audio_sample(audio)
