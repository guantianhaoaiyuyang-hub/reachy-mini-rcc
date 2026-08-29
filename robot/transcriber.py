from __future__ import annotations

from typing import Any

import numpy as np
from faster_whisper import WhisperModel


WHISPER_SAMPLE_RATE = 16_000


class WhisperTranscriber:
    """将 Reachy 音频转换为 Whisper 所需格式并转写中文。"""

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        model: Any | None = None,
    ) -> None:
        if model is None:
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
            )
        self.model = model

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> str:
        if sample_rate <= 0:
            raise ValueError("录音采样率必须大于零。")

        prepared = np.asarray(audio, dtype=np.float32)
        if prepared.ndim == 2:
            prepared = prepared.mean(axis=1, dtype=np.float32)
        elif prepared.ndim != 1:
            raise ValueError("录音必须是一维或二维数组。")

        if prepared.size == 0:
            return ""

        if sample_rate != WHISPER_SAMPLE_RATE:
            target_length = max(
                1,
                round(
                    prepared.size
                    * WHISPER_SAMPLE_RATE
                    / sample_rate
                ),
            )
            source_positions = np.arange(
                prepared.size,
                dtype=np.float64,
            )
            target_positions = (
                np.arange(target_length, dtype=np.float64)
                * sample_rate
                / WHISPER_SAMPLE_RATE
            )
            target_positions = np.clip(
                target_positions,
                0.0,
                prepared.size - 1,
            )
            prepared = np.interp(
                target_positions,
                source_positions,
                prepared,
            ).astype(np.float32)

        segments, _ = self.model.transcribe(
            prepared,
            language="zh",
            beam_size=5,
            vad_filter=True,
        )
        return "".join(
            text
            for segment in segments
            if (text := segment.text.strip())
        )
