from __future__ import annotations

from pathlib import Path

from reachy_mini import ReachyMini

from robot.tts_playback import (
    check_tts_health,
    play_audio_realtime,
    prepare_audio,
    request_tts_wav,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTS_BASE_URL = "http://127.0.0.1:8123"
OUTPUT_WAV = PROJECT_ROOT / "cache" / "reachy_tts_test.wav"
TEST_TEXT = "你好，我是 Reachy Mini。现在本地语音系统已经连接成功。"
MAX_PEAK = 0.30
SPEECH_GAIN = 10.0


def main() -> None:
    print("1/5 正在检查本地 CosyVoice 服务……")
    health = check_tts_health(TTS_BASE_URL)
    print(
        f"TTS 服务已就绪：{health['model']}，"
        f"{health['sample_rate']} Hz"
    )

    print("2/5 正在生成测试语音，CPU 推理可能需要约一分钟……")
    wav_bytes = request_tts_wav(
        TEST_TEXT,
        TTS_BASE_URL,
        timeout=180.0,
    )
    OUTPUT_WAV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_WAV.write_bytes(wav_bytes)
    print(f"测试语音已保存：{OUTPUT_WAV}")

    print("3/5 正在连接 Reachy Mini……")
    with ReachyMini(connection_mode="network") as mini:
        print("机器人连接成功。")

        sample_rate = mini.media.get_output_audio_samplerate()
        channels = mini.media.get_output_channels()
        print(f"Reachy 输出格式：{sample_rate} Hz，{channels} 声道")

        audio, duration = prepare_audio(
            wav_bytes,
            target_sample_rate=sample_rate,
            target_channels=channels,
            max_peak=MAX_PEAK,
            gain=SPEECH_GAIN,
        )
        print(
            f"4/5 音频准备完成：{duration:.2f} 秒，"
            f"{SPEECH_GAIN:.0f} 倍增益，峰值上限 {MAX_PEAK:.0%}"
        )

        print("5/5 正在按 20 毫秒分块播放……")
        play_audio_realtime(
            mini.media,
            audio,
            sample_rate=sample_rate,
            chunk_ms=20,
        )

    print("播放流程结束，机器人媒体连接已释放。")


if __name__ == "__main__":
    main()
