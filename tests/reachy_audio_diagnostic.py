from __future__ import annotations

import time

import numpy as np
from reachy_mini import ReachyMini


def main() -> None:
    with ReachyMini() as mini:
        print("已连接 Reachy Mini")

        input_rate = mini.media.get_input_audio_samplerate()
        output_rate = mini.media.get_output_audio_samplerate()

        print("输入采样率：", input_rate)
        print("输出采样率：", output_rate)

        mini.media.start_recording()
        print("已开始机器人麦克风采集，请对着机器人说话……")

        time.sleep(2)

        sample = mini.media.get_audio_sample()

        print("返回类型：", type(sample))
        print("形状：", getattr(sample, "shape", None))
        print("数据类型：", getattr(sample, "dtype", None))

        if sample is None:
            print("本次没有收到音频样本")
        else:
            array = np.asarray(sample)

            print("样本数量：", array.size)

            if array.size:
                print("最小值：", array.min())
                print("最大值：", array.max())

                rms = np.sqrt(
                    np.mean(array.astype(np.float64) ** 2)
                )
                print("RMS：", float(rms))

        mini.media.stop_recording()
        print("机器人麦克风采集已停止")


if __name__ == "__main__":
    main()