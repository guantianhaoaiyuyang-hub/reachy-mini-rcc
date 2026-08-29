from __future__ import annotations

import asyncio
import json
import time

from reachy_mini import ReachyMini
from config.robot_discovery import discover_robot

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name
from robot.reachy_audio_bridge import ReachyAudioBridge


def extract_text(payload) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    results = payload.get("results")
    if isinstance(results, list):
        texts: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            value = item.get("text")
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        if texts:
            return "".join(texts)

    return None


async def send_reachy_microphone(
    client: DoubaoClient,
    bridge: ReachyAudioBridge,
) -> None:
    while True:
        if bridge.tts_playing.is_set():
            await asyncio.sleep(0.01)
            continue

        sample = await asyncio.to_thread(
            bridge.mini.media.get_audio_sample
        )

        pcm = bridge.microphone_sample_to_pcm16(sample)
        if pcm:
            await client.send_audio(pcm)
        else:
            await asyncio.sleep(0.005)


async def receive_and_play_on_reachy(
    client: DoubaoClient,
    bridge: ReachyAudioBridge,
) -> None:
    while True:
        packet = await client.receive_packet()
        event = packet.event
        name = event_name(event)

        if event == Event.TTS_RESPONSE:
            bridge.tts_playing.set()
            bridge.play_doubao_pcm(packet.payload)
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
            bridge.tts_playing.set()
            print("豆包开始通过Reachy说话")
            continue

        if event == Event.TTS_ENDED:
            # push_audio_sample是非阻塞的，保留少量时间让缓冲区播完。
            await asyncio.sleep(0.5)
            bridge.tts_playing.clear()
            print("Reachy说话结束，可以继续提问")
            continue

        if event in {
            Event.SESSION_FAILED,
            Event.CONNECTION_FAILED,
        }:
            raise RuntimeError(
                f"服务端失败：{name}，{payload}"
            )


async def run() -> None:
    client = DoubaoClient()

    print("请确保Reachy Mini Control显示机器人在线。")
    print("程序启动后直接对着机器人说话。")
    print("按Ctrl+C结束。")

    print()
    print("[RCC] Discovering Reachy Mini...")
    robot_host = discover_robot()
    print(f"[RCC] Reachy Mini found: {robot_host}")

    with ReachyMini(
        host=robot_host,
        connection_mode="network",
    ) as mini:
        bridge = ReachyAudioBridge(mini)

        try:
            await client.connect()
            await client.start_session()
            bridge.start()

            sender = asyncio.create_task(
                send_reachy_microphone(client, bridge)
            )
            receiver = asyncio.create_task(
                receive_and_play_on_reachy(client, bridge)
            )

            await asyncio.gather(sender, receiver)

        finally:
            bridge.stop()
            await client.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n用户已结束Reachy实时对话")


if __name__ == "__main__":
    main()
