from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Callable

from robot.motion_state import MotionState


class MotionManagerV3:
    """
    V3.5 behavior and motion manager.

    Motion ownership:
    - IDLE: low-frequency idle animation
    - LISTENING: listening animation
    - THINKING: keep the latest pose
    - SPEAKING: continuous speaking animation
    - ENDING: finishing animation

    External systems, such as vision tracking, must call
    run_external() so all robot movement commands use the same lock.
    """

    def __init__(self, controller) -> None:
        self.controller = controller
        self.state = MotionState.IDLE

        self._lock = asyncio.Lock()
        self._background_task: asyncio.Task[None] | None = None
        self._closed = False
        self._step_count = 0

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def vision_tracking_allowed(self) -> bool:
        """
        Vision may control the head only when V3 is not actively
        producing head animation.

        IDLE is allowed because the current V3.5 idle behavior mainly
        controls the antennas. THINKING intentionally holds still.
        """
        return (
            not self._closed
            and self.state
            in {
                MotionState.IDLE,
                MotionState.THINKING,
            }
        )

    async def _run_locked(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        async with self._lock:
            return await asyncio.to_thread(
                func,
                *args,
                **kwargs,
            )

    async def run_external(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Run a robot SDK command from an external subsystem.

        Vision tracking uses this method instead of calling the SDK
        directly. This prevents vision and Motion V3.5 from sending
        overlapping movement commands.
        """
        if self._closed:
            return None

        return await self._run_locked(
            func,
            *args,
            **kwargs,
        )

    async def change(
        self,
        state: MotionState,
    ) -> None:
        if self._closed:
            return

        if (
            self.state == state
            and self._background_task is not None
        ):
            return

        print(
            f"\n===== Motion V3.5 -> {state.value} ====="
        )

        await self._stop_background_loop()
        self.state = state

        if state == MotionState.IDLE:
            await self._run_locked(
                self.controller.idle_entry
            )

            self._background_task = (
                asyncio.create_task(
                    self._idle_loop()
                )
            )

        elif state == MotionState.LISTENING:
            await self._run_locked(
                self.controller.listening_entry
            )

            self._background_task = (
                asyncio.create_task(
                    self._listening_loop()
                )
            )

        elif state == MotionState.THINKING:
            print(
                "[Motion V3.5] Thinking holds "
                "the current pose."
            )

        elif state == MotionState.GREETING:
            await self._run_locked(
                self.controller.greeting
            )

        elif state == MotionState.SPEAKING:
            self._step_count = 0

            await self._run_locked(
                self.controller.speaking_start
            )

            self._background_task = (
                asyncio.create_task(
                    self._speaking_loop()
                )
            )

        elif state == MotionState.ENDING:
            await self._run_locked(
                self.controller.finish
            )

    async def _idle_loop(self) -> None:
        try:
            while (
                not self._closed
                and self.state == MotionState.IDLE
            ):
                hold_time = await self._run_locked(
                    self.controller.idle_step
                )

                await asyncio.sleep(hold_time)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[Motion V3.5] Idle motion error:",
                repr(exc),
            )

    async def _listening_loop(self) -> None:
        try:
            while (
                not self._closed
                and self.state
                == MotionState.LISTENING
            ):
                hold_time = await self._run_locked(
                    self.controller.listening_step
                )

                await asyncio.sleep(hold_time)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[Motion V3.5] Listening motion error:",
                repr(exc),
            )

    async def _speaking_loop(self) -> None:
        try:
            while (
                not self._closed
                and self.state
                == MotionState.SPEAKING
            ):
                await self._run_locked(
                    self.controller.speaking_step
                )

                self._step_count += 1

                if self._step_count % 8 == 0:
                    print(
                        "[Motion V3.5] Speaking steps:",
                        self._step_count,
                    )

                await asyncio.sleep(0.16)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[Motion V3.5] Speaking motion error:",
                repr(exc),
            )

    async def _stop_background_loop(
        self,
    ) -> None:
        if self._background_task is None:
            return

        self._background_task.cancel()

        with suppress(asyncio.CancelledError):
            await self._background_task

        self._background_task = None

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        await self._stop_background_loop()

        await self._run_locked(
            self.controller.neutral,
            0.36,
        )