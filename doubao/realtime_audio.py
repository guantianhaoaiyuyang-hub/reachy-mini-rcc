from __future__ import annotations

import asyncio
import threading
from collections import deque

import sounddevice as sd


INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"

INPUT_BLOCK_FRAMES = 320   # 20ms @ 16kHz
OUTPUT_BLOCK_FRAMES = 480  # 20ms @ 24kHz


class RealtimeAudio:
    """
    电脑端实时音频桥：
    - 麦克风每20ms产生一包PCM16
    - 输出端持续播放豆包返回的24kHz PCM16
    - 播放TTS时默认暂停上传麦克风，避免扬声器回声再次被识别
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)

        self._output_chunks: deque[bytes] = deque()
        self._output_buffer = bytearray()
        self._output_lock = threading.Lock()

        self._tts_playing = threading.Event()
        self._closed = False

        self.input_stream: sd.RawInputStream | None = None
        self.output_stream: sd.RawOutputStream | None = None

    @property
    def tts_playing(self) -> bool:
        return self._tts_playing.is_set()

    def set_tts_playing(self, playing: bool) -> None:
        if playing:
            self._tts_playing.set()
        else:
            self._tts_playing.clear()

    def _enqueue_input(self, data: bytes) -> None:
        if self._closed or self._tts_playing.is_set():
            return

        try:
            self.input_queue.put_nowait(data)
        except asyncio.QueueFull:
            # 实时音频宁可丢旧包，也不允许积压导致明显延迟。
            try:
                self.input_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.input_queue.put_nowait(data)
            except asyncio.QueueFull:
                pass

    def _input_callback(self, indata, frames, time_info, status) -> None:
        if status:
            print("麦克风状态：", status)

        data = bytes(indata)
        self.loop.call_soon_threadsafe(self._enqueue_input, data)

    def _output_callback(self, outdata, frames, time_info, status) -> None:
        if status:
            print("扬声器状态：", status)

        required = frames * 2  # mono int16

        with self._output_lock:
            while len(self._output_buffer) < required and self._output_chunks:
                self._output_buffer.extend(self._output_chunks.popleft())

            available = min(required, len(self._output_buffer))
            chunk = bytes(self._output_buffer[:available])
            del self._output_buffer[:available]

        if available < required:
            chunk += b"\x00" * (required - available)

        outdata[:] = chunk

    def feed_output(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self._output_lock:
            self._output_chunks.append(bytes(pcm))

    def clear_output(self) -> None:
        with self._output_lock:
            self._output_chunks.clear()
            self._output_buffer.clear()

    def start(self) -> None:
        if self.input_stream is not None or self.output_stream is not None:
            return

        self._closed = False

        self.input_stream = sd.RawInputStream(
            samplerate=INPUT_SAMPLE_RATE,
            blocksize=INPUT_BLOCK_FRAMES,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._input_callback,
        )

        self.output_stream = sd.RawOutputStream(
            samplerate=OUTPUT_SAMPLE_RATE,
            blocksize=OUTPUT_BLOCK_FRAMES,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._output_callback,
        )

        self.input_stream.start()
        self.output_stream.start()
        print("实时麦克风与扬声器已启动")

    def stop(self) -> None:
        self._closed = True

        if self.input_stream is not None:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None

        if self.output_stream is not None:
            self.output_stream.stop()
            self.output_stream.close()
            self.output_stream = None

        self.clear_output()
        print("实时音频设备已关闭")
