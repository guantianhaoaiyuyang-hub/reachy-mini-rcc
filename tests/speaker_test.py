import time

import numpy as np
from reachy_mini import ReachyMini


def main() -> None:
    duration = 2.0
    frequency = 440.0

    print("正在连接 Reachy Mini……")

    with ReachyMini(connection_mode="network") as mini:
        print("连接成功！")

        sample_rate = mini.media.get_output_audio_samplerate()
        channels = mini.media.get_output_channels()

        print(f"输出采样率：{sample_rate}")
        print(f"输出声道数：{channels}")

        print("正在初始化扬声器……")
        mini.media.start_playing()

        # 给 WebRTC 音频管线一点初始化时间
        time.sleep(1.5)

        print("准备播放 2 秒测试音……")

        t = np.arange(
            int(sample_rate * duration),
            dtype=np.float32,
        ) / sample_rate

        tone = 0.2 * np.sin(2 * np.pi * frequency * t)

        # 按机器人实际声道数生成音频
        audio = np.repeat(
            tone[:, np.newaxis],
            channels,
            axis=1,
        ).astype(np.float32)

        mini.media.push_audio_sample(audio)

        # push_audio_sample() 是非阻塞调用
        time.sleep(duration + 1.0)

        mini.media.stop_playing()
        print("扬声器测试完成。")


if __name__ == "__main__":
    main()