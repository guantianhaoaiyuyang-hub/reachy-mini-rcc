from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress

from reachy_mini import ReachyMini
from config.robot_discovery import discover_robot

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name
from robot.motion_controller_v3 import (
    ReachyMotionControllerV3,
)
from robot.motion_manager_v3 import (
    MotionManagerV3,
)
from robot.motion_state import MotionState
from robot.reachy_audio_bridge import (
    ReachyAudioBridge,
)
from robot.vision_tracker import (
    ReachyVisionTracker,
)


DOUBAO_TTS_SAMPLE_RATE = 24000
PCM_BYTES_PER_SAMPLE = 2
PCM_CHANNELS = 1

PCM_BYTES_PER_SECOND = (
    DOUBAO_TTS_SAMPLE_RATE
    * PCM_BYTES_PER_SAMPLE
    * PCM_CHANNELS
)


def extract_text(
    payload,
) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("text", "content"):
        value = payload.get(key)

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    results = payload.get("results")

    if isinstance(results, list):
        texts = []

        for item in results:
            if not isinstance(item, dict):
                continue

            value = item.get("text")

            if (
                isinstance(value, str)
                and value.strip()
            ):
                texts.append(value.strip())

        if texts:
            return "".join(texts)

    return None


async def send_reachy_microphone(
    client,
    bridge,
) -> None:
    while True:
        if bridge.tts_playing.is_set():
            await asyncio.sleep(0.01)
            continue

        sample = await asyncio.to_thread(
            bridge.mini.media.get_audio_sample
        )

        pcm = (
            bridge
            .microphone_sample_to_pcm16(
                sample
            )
        )

        if pcm:
            await client.send_audio(pcm)
        else:
            await asyncio.sleep(0.005)


async def receive_play_and_move(
    client,
    bridge,
    motion,
) -> None:
    user_is_speaking = False
    answer_started = False

    answer_audio_bytes = 0
    first_audio_time: float | None = None

    while True:
        packet = await client.receive_packet()

        event = packet.event
        name = event_name(event)

        if event == Event.TTS_RESPONSE:
            bridge.tts_playing.set()

            if not answer_started:
                answer_started = True
                answer_audio_bytes = 0
                first_audio_time = (
                    time.monotonic()
                )

                await motion.change(
                    MotionState.SPEAKING
                )

            answer_audio_bytes += len(
                packet.payload
            )

            await asyncio.to_thread(
                bridge.play_doubao_pcm,
                packet.payload,
            )

            continue

        payload = packet.json_payload()

        if event == Event.ASR_INFO:
            if not user_is_speaking:
                user_is_speaking = True

                await motion.change(
                    MotionState.LISTENING
                )

            print(
                "检测到用户开始说话；"
                "视觉头部追踪暂时让位给倾听动作"
            )

            continue

        if event == Event.ASR_RESPONSE:
            text = extract_text(payload)

            if text:
                print(f"{name}: {text}")

            continue

        if event == Event.ASR_ENDED:
            user_is_speaking = False

            await motion.change(
                MotionState.THINKING
            )

            print(
                "用户说话结束；进入思考状态，"
                "视觉追踪恢复"
            )

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
                answer_audio_bytes = 0

                first_audio_time = (
                    time.monotonic()
                )

                await motion.change(
                    MotionState.SPEAKING
                )

            print(
                "豆包开始通过 Reachy 说话；"
                "视觉头部追踪暂时让位给"
                " Motion V3.5"
            )

            continue

        if event == Event.TTS_SENTENCE_END:
            text = extract_text(payload)

            if text:
                print(f"{name}: {text}")

            continue

        if event == Event.TTS_ENDED:
            audio_duration = (
                answer_audio_bytes
                / PCM_BYTES_PER_SECOND
            )

            elapsed = (
                time.monotonic()
                - first_audio_time
                if first_audio_time
                is not None
                else 0.0
            )

            remaining = max(
                0.20,
                audio_duration
                - elapsed
                + 0.35,
            )

            remaining = min(
                remaining,
                30.0,
            )

            print(
                "[V3.5 + Vision] "
                "服务端音频发送结束；"
                f"累计音频约 "
                f"{audio_duration:.2f} 秒，"
                f"继续动作约 "
                f"{remaining:.2f} 秒"
            )

            await asyncio.sleep(remaining)

            await motion.change(
                MotionState.ENDING
            )

            await motion.change(
                MotionState.IDLE
            )

            answer_started = False
            answer_audio_bytes = 0
            first_audio_time = None

            bridge.tts_playing.clear()

            print(
                "Reachy 回答结束；"
                "视觉追踪已经恢复"
            )

            continue

        if event in {
            Event.SESSION_FAILED,
            Event.CONNECTION_FAILED,
        }:
            raise RuntimeError(
                f"服务端失败："
                f"{name}，{payload}"
            )

        if payload is not None:
            print(
                f"{name}:",
                json.dumps(
                    payload,
                    ensure_ascii=False,
                ),
            )


async def run() -> None:
    client = DoubaoClient()

    print("=" * 68)
    print(
        "Reachy Mini Doubao Realtime Voice "
        "+ Motion V3.5 + Vision Tracking"
    )
    print("=" * 68)
    print(
        "Please keep at least 30 cm "
        "of free space around the robot."
    )
    print(
        "Press Ctrl+C in this terminal "
        "to stop the complete system."
    )
    print(
        "In the camera window: "
        "T toggles tracking, "
        "S saves a snapshot."
    )

    print()
    print("[RCC] Discovering Reachy Mini...")
    robot_host = discover_robot()
    print(f"[RCC] Reachy Mini found: {robot_host}")

    with ReachyMini(
        host=robot_host,
        connection_mode="network",
    ) as mini:
        bridge = ReachyAudioBridge(mini)

        controller = (
            ReachyMotionControllerV3(mini)
        )

        motion = (
            MotionManagerV3(controller)
        )

        vision = ReachyVisionTracker(
            mini=mini,
            motion=motion,
        )

        tasks: list[
            asyncio.Task
        ] = []

        try:
            mini.enable_motors()
            await asyncio.sleep(1)

            mini.wake_up()
            await asyncio.sleep(3)

            await client.connect()
            await client.start_session()

            bridge.start()

            await motion.change(
                MotionState.IDLE
            )

            tasks = [
                asyncio.create_task(
                    send_reachy_microphone(
                        client,
                        bridge,
                    ),
                    name="reachy-microphone",
                ),
                asyncio.create_task(
                    receive_play_and_move(
                        client,
                        bridge,
                        motion,
                    ),
                    name="doubao-events",
                ),
                asyncio.create_task(
                    vision.run(),
                    name="vision-tracker",
                ),
            ]

            done, pending = (
                await asyncio.wait(
                    tasks,
                    return_when=(
                        asyncio
                        .FIRST_EXCEPTION
                    ),
                )
            )

            for task in done:
                exception = task.exception()

                if exception is not None:
                    raise exception

            await asyncio.gather(*pending)

        finally:
            await vision.close()

            for task in tasks:
                if not task.done():
                    task.cancel()

            for task in tasks:
                with suppress(
                    asyncio.CancelledError
                ):
                    await task

            await motion.close()

            bridge.stop()

            await client.close()


def main() -> None:
    try:
        asyncio.run(run())

    except KeyboardInterrupt:
        print(
            "\nUser stopped Reachy Mini "
            "V3.5 + Vision."
        )


if __name__ == "__main__":
    main()