import time
from pathlib import Path

import numpy as np
import soundfile as sf
from reachy_mini import ReachyMini


RECORD_SECONDS = 5
OUTPUT_FILE = Path("microphone_test.wav")


def main() -> None:
    print("正在连接 Reachy Mini……")

    with ReachyMini(connection_mode="network") as mini:
        print("连接成功！")

        sample_rate = mini.media.get_input_audio_samplerate()
        channels = mini.media.get_input_channels()

        print(f"麦克风采样率：{sample_rate}")
        print(f"麦克风声道数：{channels}")
        print(f"即将录音 {RECORD_SECONDS} 秒，请对 Reachy Mini 说话……")

        mini.media.start_recording()
        time.sleep(1.0)

        chunks: list[np.ndarray] = []
        deadline = time.time() + RECORD_SECONDS

        try:
            while time.time() < deadline:
                chunk = mini.media.get_audio_sample()

                if chunk is not None and chunk.size > 0:
                    chunks.append(chunk)
                else:
                    time.sleep(0.01)
        finally:
            mini.media.stop_recording()

        if not chunks:
            print("录音失败：没有收到麦克风数据。")
            return

        audio = np.concatenate(chunks, axis=0).astype(np.float32)

        print(f"录音数据形状：{audio.shape}")
        print(f"录音时长约：{len(audio) / sample_rate:.2f} 秒")

        sf.write(
            OUTPUT_FILE,
            audio,
            sample_rate,
            subtype="PCM_16",
        )

        print(f"录音成功，文件已保存到：{OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()