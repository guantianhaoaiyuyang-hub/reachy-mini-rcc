from pathlib import Path

from faster_whisper import WhisperModel


AUDIO_FILE = Path("microphone_test.wav")


def main() -> None:
    if not AUDIO_FILE.exists():
        print(f"找不到录音文件：{AUDIO_FILE.resolve()}")
        return

    print("正在加载语音识别模型……")
    print("第一次运行需要下载模型，请耐心等待。")

    model = WhisperModel(
        "small",
        device="cpu",
        compute_type="int8",
    )

    print("模型加载完成，正在识别……")

    segments, info = model.transcribe(
        str(AUDIO_FILE),
        language="zh",
        beam_size=5,
        vad_filter=True,
    )

    texts: list[str] = []

    for segment in segments:
        text = segment.text.strip()

        if text:
            texts.append(text)
            print(
                f"[{segment.start:.2f}s → {segment.end:.2f}s] "
                f"{text}"
            )

    result = "".join(texts).strip()

    print("\n识别结果：")
    print(result if result else "没有识别到有效语音。")
    print(f"\n检测语言：{info.language}")
    print(f"语言置信度：{info.language_probability:.2%}")


if __name__ == "__main__":
    main()