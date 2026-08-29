from __future__ import annotations

import asyncio
import json

from reachy_mini import ReachyMini
from config.robot_discovery import discover_robot

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name
from robot.motion_controller import ReachyMotionController
from robot.motion_manager import MotionManager
from robot.motion_state import MotionState
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
        texts = []
        for item in results:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
        if texts:
            return "".join(texts)
    return None


async def send_reachy_microphone(client, bridge) -> None:
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


async def receive_play_and_move(client, bridge, motion) -> None:
    user_is_speaking = False
    answer_started = False

    while True:
        packet = await client.receive_packet()
        event = packet.event
        name = event_name(event)

        if event == Event.TTS_RESPONSE:
            bridge.tts_playing.set()
            bridge.play_doubao_pcm(packet.payload)
            continue

        payload = packet.json_payload()

        if event == Event.ASR_INFO:
            if not user_is_speaking:
                user_is_speaking = True
            print("检测到用户开始说话")
            continue

        if event == Event.ASR_RESPONSE:
            text = extract_text(payload)
            if text:
                print(f"{name}: {text}")
            continue

        if event == Event.ASR_ENDED:
            user_is_speaking = False
            print("用户说话结束，等待豆包回答")
            continue

        if event == Event.CHAT_RESPONSE:
            text = extract_text(payload)
            if text:
                print(f"{name}: {text}")
            continue

        if event == Event.TTS_SENTENCE_START:
            bridge.tts_playing.set()
            if not answer_started:
                answer_started = True
                await motion.change(MotionState.GREETING)
                await motion.change(MotionState.SPEAKING)
            print("豆包开始通过 Reachy 说话")
            continue

        if event == Event.TTS_SENTENCE_END:
            text = extract_text(payload)
            if text:
                print(f"{name}: {text}")
            continue

        if event == Event.TTS_ENDED:
            await asyncio.sleep(0.1)
            await motion.change(MotionState.ENDING)
            await motion.change(MotionState.IDLE)
            answer_started = False
            bridge.tts_playing.clear()
            print("Reachy 回答结束，可以继续提问")
            continue

        if event in {Event.SESSION_FAILED, Event.CONNECTION_FAILED}:
            raise RuntimeError(f"服务端失败：{name}，{payload}")

        if payload is not None:
            print(f"{name}:", json.dumps(payload, ensure_ascii=False))


async def run() -> None:
    client = DoubaoClient()

    print("=" * 64)
    print("Reachy Mini 豆包实时语音 + V2动作状态机")
    print("=" * 64)
    print("机器人周围至少留出30厘米空间。")
    print("按 Ctrl+C 结束。")

    print()
    print("[RCC] Discovering Reachy Mini...")
    robot_host = discover_robot()
    print(f"[RCC] Reachy Mini found: {robot_host}")

    with ReachyMini(
        host=robot_host,
        connection_mode="network",
    ) as mini:
        bridge = ReachyAudioBridge(mini)
        controller = ReachyMotionController(mini)
        motion = MotionManager(controller)

        try:
            await client.connect()
            await client.start_session()
            bridge.start()
            await motion.change(MotionState.IDLE)

            await asyncio.gather(
                send_reachy_microphone(client, bridge),
                receive_play_and_move(client, bridge, motion),
            )
        finally:
            await motion.close()
            bridge.stop()
            await client.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n用户已结束语音与动作状态机")


if __name__ == "__main__":
    main()
