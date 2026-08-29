from __future__ import annotations

import asyncio
import json

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name
from doubao.realtime_audio import RealtimeAudio


def extract_text(payload) -> str | None:
    if not isinstance(payload, dict):
        return None

    # 常见直接字段
    for key in ("text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # ChatResponse 常见 results 列表
    results = payload.get("results")
    if isinstance(results, list):
        texts: list[str] = []
        for item in results:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
        if texts:
            return "".join(texts)

    return None


async def send_microphone(
    client: DoubaoClient,
    audio: RealtimeAudio,
) -> None:
    while True:
        chunk = await audio.input_queue.get()
        await client.send_audio(chunk)


async def receive_and_play(
    client: DoubaoClient,
    audio: RealtimeAudio,
) -> None:
    while True:
        packet = await client.receive_packet()
        event = packet.event
        name = event_name(event)

        if event == Event.TTS_RESPONSE:
            audio.set_tts_playing(True)
            audio.feed_output(packet.payload)
            continue

        payload = packet.json_payload()

        if event in {
            Event.ASR_RESPONSE,
            Event.CHAT_RESPONSE,
            Event.TTS_SENTENCE_END,
        }:
            text = extract_text(payload)
            if text:
                print(f"{name}: {text}")
            elif payload is not None:
                print(
                    f"{name}:",
                    json.dumps(payload, ensure_ascii=False),
                )
            continue

        if event == Event.TTS_SENTENCE_START:
            audio.set_tts_playing(True)
            print("豆包开始说话")
            continue

        if event == Event.TTS_ENDED:
            # 给输出缓冲区一点播放完成时间，再恢复麦克风上传。
            await asyncio.sleep(0.25)
            audio.set_tts_playing(False)
            print("豆包说话结束，可以继续提问")
            continue

        if event in {
            Event.SESSION_FAILED,
            Event.CONNECTION_FAILED,
        }:
            raise RuntimeError(
                f"服务端失败：{name}，{payload}"
            )


async def main() -> None:
    client = DoubaoClient()
    loop = asyncio.get_running_loop()
    audio = RealtimeAudio(loop)

    print("建议先佩戴耳机，避免扬声器回声。")
    print("程序启动后直接说话；按 Ctrl+C 结束。")

    try:
        await client.connect()
        await client.start_session()
        audio.start()

        sender = asyncio.create_task(
            send_microphone(client, audio)
        )
        receiver = asyncio.create_task(
            receive_and_play(client, audio)
        )

        await asyncio.gather(sender, receiver)

    finally:
        audio.stop()
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户已结束实时对话")
