from __future__ import annotations

import asyncio
import random
from contextlib import suppress
from robot.motion_state import MotionState


class MotionManager:
    def __init__(self, controller) -> None:
        self.controller = controller
        self.state = MotionState.IDLE
        self._lock = asyncio.Lock()
        self._speaking_task: asyncio.Task[None] | None = None
        self._closed = False

    async def _run_locked(self, func, *args) -> None:
        async with self._lock:
            await asyncio.to_thread(func, *args)

    async def change(self, state: MotionState) -> None:
        if self._closed or self.state == state:
            return

        print(f"\n===== Motion -> {state.value} =====")

        if self.state == MotionState.SPEAKING:
            await self._stop_speaking_loop()

        self.state = state

        if state == MotionState.IDLE:
            await self._run_locked(self.controller.neutral)
        elif state == MotionState.LISTENING:
            await self._run_locked(self.controller.listening)
        elif state == MotionState.THINKING:
            await self._run_locked(self.controller.thinking)
        elif state == MotionState.GREETING:
            await self._run_locked(self.controller.greeting)
        elif state == MotionState.SPEAKING:
            self._speaking_task = asyncio.create_task(self._speaking_loop())
        elif state == MotionState.ENDING:
            await self._run_locked(self.controller.finish)

    async def _speaking_loop(self) -> None:
        try:
            while not self._closed and self.state == MotionState.SPEAKING:
                choice = random.choices(
                    ("pulse", "pulse", "nod", "curious"),
                    weights=(5, 5, 1, 1),
                    k=1,
                )[0]

                if choice == "pulse":
                    await self._run_locked(self.controller.speaking_pulse)
                elif choice == "nod":
                    await self._run_locked(self.controller.nod, 1)
                else:
                    await self._run_locked(self.controller.curious)

                await asyncio.sleep(random.uniform(0.18, 0.42))
        except asyncio.CancelledError:
            raise

    async def _stop_speaking_loop(self) -> None:
        if self._speaking_task is None:
            return
        self._speaking_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._speaking_task
        self._speaking_task = None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_speaking_loop()
        await self._run_locked(self.controller.neutral)
