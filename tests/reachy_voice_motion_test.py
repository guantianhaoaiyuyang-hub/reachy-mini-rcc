from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from reachy_mini import ReachyMini

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name
from robot.motion_controller import ReachyMotionController
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


class MotionRuntime:
    """
    把同步的 Reachy 动作安全地放入后台线程执行，
    避免阻塞豆包 WebSocket 音频接收。
    """

    def __init__(self, controller: ReachyMotionController) -> None:
        self.controller = controller
        self.lock = asyncio.Lock()
        self.speaking_task: asyncio.Task[None] | None = None
        self.running = True

    async def _run_locked(self, action, *args) -> None:
        async with self.lock:
            await asyncio.to_thread(action, *args)

    async def listening_pose(self) -> None:
        await self._run_locked(self.controller.curious)

    async def start_speaking(self) -> None:
        if self.speaking_task and not self.speaking_task.done():
            return

        await self._run_locked(self.controller.greet)

        self.speaking_task = asyncio.create_task(
            self._speaking_loop()
        )

    async def _speaking_loop(self) -> None:
        try:
            while self.running:
                await self._run_locked(
                    self.controller.speaking_pulse
                )
                await asyncio.sleep(0.18)
        except asyncio.CancelledError:
            raise

    async def stop_speaking(self) -> None:
        if self.speaking_task is not None:
            self.speaking_task.cancel()

            with suppress(asyncio.CancelledError):
                await self.speaking_task

            self.speaking_task = None

        await self._run_locked(self.controller.nod, 1)

    async def close(self) -> None:
        self.running = False

        if self.speaking_task is not None:
            self.speaking_task.cancel()

            with suppress(asyncio.CancelledError):
                await self.speaking_task

            self.speaking_task = None

        await self._run_locked(self.controller.neutral)


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


async def receive_play_and_move(
    client: DoubaoClient,
    bridge: ReachyAudioBridge,
    motion: MotionRuntime,
) -> None:
    listening_motion_started = False

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
            if not listening_motion_started:
                listening_motion_started = True
                asyncio.create_task(motion.listening_pose())

            print("检测到用户开始说话")
            continue

        if event == Event.ASR_ENDED:
            listening_motion_started = False
            print("用户说话结束，等待豆包回答")
            continue

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
            print("豆包开始通过 Reachy 说话并执行动作")
            await motion.start_speaking()
            continue

        if event == Event.TTS_ENDED:
            await asyncio.sleep(0.5)
            await motion.stop_speaking()
            bridge.tts_playing.clear()
            print("Reachy 回答结束，可以继续提问")
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

    print("=" * 60)
    print("Reachy Mini 豆包实时语音 + 动作联动")
    print("=" * 60)
    print()
    print("请确保 Reachy Mini Control 显示机器人在线。")
    print("机器人周围至少留出30厘米空间。")
    print("程序启动后直接对着机器人说话。")
    print("按 Ctrl+C 结束。")
    print()

    with ReachyMini() as mini:
        bridge = ReachyAudioBridge(mini)
        controller = ReachyMotionController(mini)
        motion = MotionRuntime(controller)

        try:
            await client.connect()
            await client.start_session()
            bridge.start()

            await asyncio.gather(
                send_reachy_microphone(client, bridge),
                receive_play_and_move(
                    client,
                    bridge,
                    motion,
                ),
            )

        finally:
            await motion.close()
            bridge.stop()
            await client.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n用户已结束语音与动作联动")


if __name__ == "__main__":
    main()
