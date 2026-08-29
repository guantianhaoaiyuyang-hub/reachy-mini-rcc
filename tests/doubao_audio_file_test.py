from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import numpy as np
import soundfile as sf

from doubao.client import DoubaoClient
from doubao.protocol import Event, event_name


INPUT_FILE = Path("recordings/test_record.wav")
OUTPUT_FILE = Path("recordings/doubao_reply.wav")

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
SAMPLES_PER_PACKET = 320  # 20ms at 16kHz


def load_input_pcm() -> bytes:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"找不到录音文件：{INPUT_FILE}")

    audio, sample_rate = sf.read(
        INPUT_FILE,
        dtype="int16",
        always_2d=True,
    )

    if sample_rate != INPUT_SAMPLE_RATE:
        raise ValueError(
            f"录音采样率应为16000Hz，实际为：{sample_rate}Hz"
        )
    if audio.shape[1] != 1:
        raise ValueError(
            f"录音应为单声道，实际声道数：{audio.shape[1]}"
        )

    mono = np.ascontiguousarray(audio[:, 0], dtype="<i2")
    return mono.tobytes()


def save_reply_pcm(pcm_data: bytes) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(OUTPUT_FILE), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(OUTPUT_SAMPLE_RATE)
        wav_file.writeframes(pcm_data)

    print("豆包回复语音已保存：", OUTPUT_FILE)
    print("回复音频字节数：", len(pcm_data))


async def receive_response(client: DoubaoClient) -> bytes:
    tts_audio = bytearray()

    while True:
        packet = await client.receive_packet(timeout=60)
        name = event_name(packet.event)

        if packet.event == Event.TTS_RESPONSE:
            tts_audio.extend(packet.payload)
            print(
                "收到TTS音频：",
                len(packet.payload),
                "字节；累计：",
                len(tts_audio),
                "字节",
            )
            continue

        payload = packet.json_payload()
        print("收到事件：", packet.event, name)

        if payload is not None:
            print(
                "事件内容：",
                json.dumps(payload, ensure_ascii=False),
            )

        if packet.event == Event.TTS_ENDED:
            print("本轮TTS生成结束")
            return bytes(tts_audio)

        if packet.event in {
            Event.SESSION_FAILED,
            Event.CONNECTION_FAILED,
        }:
            raise RuntimeError(
                f"服务端返回失败事件：{name}，{payload}"
            )


async def send_recording(
    client: DoubaoClient,
    pcm_data: bytes,
) -> None:
    bytes_per_packet = SAMPLES_PER_PACKET * 2
    total_packets = (
        len(pcm_data) + bytes_per_packet - 1
    ) // bytes_per_packet

    print("开始上传录音")
    print("录音字节数：", len(pcm_data))
    print("预计分包数：", total_packets)

    for index, start in enumerate(
        range(0, len(pcm_data), bytes_per_packet),
        start=1,
    ):
        chunk = pcm_data[start:start + bytes_per_packet]

        if len(chunk) < bytes_per_packet:
            chunk += b"\x00" * (bytes_per_packet - len(chunk))

        await client.send_audio(chunk)
        await asyncio.sleep(0.02)

        if index % 50 == 0:
            print(f"已发送 {index}/{total_packets} 包")

    print("录音上传完成，等待豆包回复……")


async def main() -> None:
    pcm_data = load_input_pcm()
    client = DoubaoClient()

    try:
        await client.connect()
        await client.start_session()

        receiver_task = asyncio.create_task(
            receive_response(client)
        )

        await send_recording(client, pcm_data)
        reply_pcm = await receiver_task

        if not reply_pcm:
            raise RuntimeError("没有收到豆包返回的TTS音频")

        save_reply_pcm(reply_pcm)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
