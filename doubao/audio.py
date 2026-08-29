from __future__ import annotations

import numpy as np
import sounddevice as sd
import soundfile as sf


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


def record(seconds: float) -> np.ndarray:
    print(f"开始录音（{seconds} 秒）...")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()
    print("录音结束")
    return audio


def save_wav(audio: np.ndarray, filename: str) -> None:
    sf.write(filename, audio, SAMPLE_RATE)
    print("已保存：", filename)
