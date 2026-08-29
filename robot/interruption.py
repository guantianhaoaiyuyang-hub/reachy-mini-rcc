from __future__ import annotations

from queue import Empty, Queue
from threading import RLock
from typing import Any


class InterruptionController:
    """以单调递增代际隔离被打断的旧回复。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._generation = 0
        self._response_id: str | None = None

    def begin_response(self, response_id: str) -> int:
        with self._lock:
            self._generation += 1
            self._response_id = response_id
            return self._generation

    def invalidate_current(self) -> int:
        with self._lock:
            self._generation += 1
            self._response_id = None
            return self._generation

    def is_current(
        self,
        generation: int,
        response_id: str,
    ) -> bool:
        with self._lock:
            return (
                generation == self._generation
                and response_id == self._response_id
            )

    def clear_queue(self, audio_queue: Queue[Any]) -> int:
        with self._lock:
            return self._clear_queue_unlocked(audio_queue)

    def interrupt(
        self,
        audio_queue: Queue[Any],
    ) -> tuple[int, int]:
        with self._lock:
            self._generation += 1
            self._response_id = None
            removed = self._clear_queue_unlocked(audio_queue)
            return self._generation, removed

    @staticmethod
    def _clear_queue_unlocked(audio_queue: Queue[Any]) -> int:
        removed = 0
        while True:
            try:
                audio_queue.get_nowait()
            except Empty:
                return removed
            else:
                removed += 1
