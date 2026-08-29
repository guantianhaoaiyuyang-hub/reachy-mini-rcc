from __future__ import annotations

from reachy_mini import ReachyMini

from config import (
    REACHY_CONNECTION_MODE,
    RECORD_SECONDS,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)
from robot.assistant import VoiceAssistant, run_interactive_loop
from robot.brain import DeepSeekBrain
from robot.speech_motion import HostSpeechMotion
from robot.transcriber import WhisperTranscriber
from robot.tts_playback import check_tts_health, request_tts_wav
from robot.volcengine_tts import (
    VolcengineTTSClient,
    VolcengineTTSConfig,
    VolcengineTTSError,
    load_env_file,
    request_with_fallback,
)


LOCAL_TTS_BASE_URL = "http://127.0.0.1:8123"
CLOUD_TTS_TIMEOUT_SECONDS = 30.0


def make_tts_request():
    """Prefer fast Chinese cloud speech and retain local CosyVoice as backup."""

    try:
        cloud_client = VolcengineTTSClient(VolcengineTTSConfig.from_env())
    except VolcengineTTSError:
        cloud_client = None
        print("豆包中文语音尚未就绪，本次将使用本地 CosyVoice。")
        health = check_tts_health(LOCAL_TTS_BASE_URL)
        print(f"本地 CosyVoice 已就绪：{health['model']}，{health['sample_rate']} Hz")
    else:
        print("豆包中文语音已就绪，将优先使用云端快速合成。")

    def local_request(text: str) -> bytes:
        return request_tts_wav(text, LOCAL_TTS_BASE_URL, timeout=180.0)

    def request(text: str, _base_url: str, *, timeout: float) -> bytes:
        if cloud_client is None:
            return local_request(text)
        return request_with_fallback(
            text,
            cloud_request=lambda value: cloud_client.synthesize_wav(
                value,
                timeout=min(timeout, CLOUD_TTS_TIMEOUT_SECONDS),
            ),
            local_request=local_request,
        )

    return request


def main() -> None:
    load_env_file()
    tts_request = make_tts_request()
    brain = DeepSeekBrain()

    print("正在加载 Whisper 模型……")
    transcriber = WhisperTranscriber(
        model_name=WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )
    print("Whisper 已就绪。")

    print("正在连接 Reachy Mini……")
    with ReachyMini(connection_mode=REACHY_CONNECTION_MODE) as mini:
        mini.enable_motors()
        print("机器人电机已启用。")
        input_sample_rate = mini.media.get_input_audio_samplerate()
        output_sample_rate = mini.media.get_output_audio_samplerate()
        output_channels = mini.media.get_output_channels()
        print(
            "机器人连接成功："
            f"输入 {input_sample_rate} Hz；"
            f"输出 {output_sample_rate} Hz / {output_channels} 声道"
        )

        assistant = VoiceAssistant(
            media=mini.media,
            transcriber=transcriber,
            brain=brain,
            input_sample_rate=input_sample_rate,
            output_sample_rate=output_sample_rate,
            output_channels=output_channels,
            tts_base_url=LOCAL_TTS_BASE_URL,
            record_seconds=RECORD_SECONDS,
            tts_request=tts_request,
            speech_motion_factory=lambda: HostSpeechMotion(mini),
        )
        run_interactive_loop(assistant)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已收到中断，程序安全退出。")
