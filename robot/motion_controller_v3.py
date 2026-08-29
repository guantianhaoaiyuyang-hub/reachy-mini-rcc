from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
from reachy_mini.utils import create_head_pose


@dataclass(frozen=True)
class MotionConfigV35:
    """V3.5 Behavior 参数。"""

    return_duration: float = 0.34
    nod_pitch_deg: float = 10.0

    # Speaking：沿用 V3.4 的主要幅度
    max_pitch_deg: float = 4.0
    max_roll_deg: float = 6.0
    max_yaw_deg: float = 8.0
    antenna_base_deg: float = 16.0
    antenna_wave_deg: float = 8.0


class ReachyMotionControllerV3:
    """
    Reachy Mini V3.5 Behavior 动作控制器。

    目标：
    - Idle 有轻微、低频、随机待机动作
    - Listening 有更明确但仍克制的倾听动作
    - Thinking 不主动发送动作
    - Listening -> Speaking 不先回中位
    - Speaking 稳态保持 V3.4 的幅度和连续曲线
    """

    def __init__(
        self,
        mini: Any,
        config: MotionConfigV35 | None = None,
    ) -> None:
        self.mini = mini
        self.config = config or MotionConfigV35()
        self._speech_index = 0
        self._steps_per_cycle = 32
        self._rng = random.Random()

    def _goto(
        self,
        *,
        pitch: float = 0.0,
        roll: float = 0.0,
        yaw: float = 0.0,
        left_antenna: float = 0.0,
        right_antenna: float = 0.0,
        duration: float = 0.4,
    ) -> None:
        self.mini.goto_target(
            head=create_head_pose(
                pitch=pitch,
                roll=roll,
                yaw=yaw,
                degrees=True,
            ),
            antennas=np.deg2rad([left_antenna, right_antenna]),
            duration=duration,
            method="minjerk",
        )

    def neutral(self, duration: float | None = None) -> None:
        self._goto(duration=duration or self.config.return_duration)

    def _goto_antennas(
        self,
        *,
        left_antenna: float,
        right_antenna: float,
        duration: float,
    ) -> None:
        """只移动天线，不向头部发送新目标。"""
        self.mini.goto_target(
            antennas=np.deg2rad([left_antenna, right_antenna]),
            duration=duration,
            method="minjerk",
        )

    def idle_entry(self) -> None:
        """
        进入待机时只整理天线。

        不控制头部，避免待机阶段出现幅度很小但肉眼可见的头部颤动。
        """
        self._goto_antennas(
            left_antenna=8.0,
            right_antenna=-8.0,
            duration=0.55,
        )

    def idle_step(self) -> float:
        """
        待机阶段仅摆动天线，并返回建议保持时间。

        两根天线以不完全对称的方式缓慢变化，避免机械式同步摆动。
        """
        antenna_center = self._rng.uniform(8.0, 19.0)
        antenna_delta = self._rng.uniform(-4.0, 4.0)

        self._goto_antennas(
            left_antenna=antenna_center + antenna_delta,
            right_antenna=-(antenna_center - antenna_delta),
            duration=self._rng.uniform(0.9, 1.5),
        )
        return self._rng.uniform(1.8, 3.4)

    def listening_entry(self) -> None:
        """进入倾听时抬起天线并轻微靠近。"""
        self._goto(
            pitch=2.0,
            roll=1.0,
            left_antenna=14.0,
            right_antenna=-14.0,
            duration=0.34,
        )

    def listening_step(self) -> float:
        """生成一次随机倾听姿态，不采用固定左右循环。"""
        pitch = self._rng.uniform(0.7, 3.0)
        roll = self._rng.uniform(-2.2, 2.2)
        yaw = self._rng.uniform(-3.2, 3.2)
        antenna_center = self._rng.uniform(11.0, 17.0)
        antenna_delta = self._rng.uniform(-2.5, 2.5)

        self._goto(
            pitch=pitch,
            roll=roll,
            yaw=yaw,
            left_antenna=antenna_center + antenna_delta,
            right_antenna=-(antenna_center - antenna_delta),
            duration=self._rng.uniform(0.75, 1.15),
        )
        return self._rng.uniform(0.85, 1.55)

    def greeting(self) -> None:
        self.speaking_start()

    def speaking_start(self) -> None:
        """只重置讲话轨迹，不发送回中位或起始姿态命令。"""
        self._speech_index = 0

    def speaking_step(self) -> None:
        """V3.4 连续讲话曲线，前 8 步柔和渐入完整幅度。"""
        index = self._speech_index
        phase = 2.0 * math.pi * (index % self._steps_per_cycle) / self._steps_per_cycle
        self._speech_index += 1

        ramp = min(1.0, 0.28 + index / 8.0)

        yaw = self.config.max_yaw_deg * math.sin(phase) * ramp
        roll = self.config.max_roll_deg * math.sin(phase) * ramp
        pitch = -0.5 + self.config.max_pitch_deg * math.sin(2.0 * phase) * ramp

        antenna_wave = (
            self.config.antenna_wave_deg
            * math.sin(2.0 * phase + math.pi / 5.0)
            * ramp
        )
        antenna_asymmetry = 3.0 * math.sin(phase - math.pi / 6.0) * ramp

        left_antenna = self.config.antenna_base_deg + antenna_wave + antenna_asymmetry
        right_antenna = -(
            self.config.antenna_base_deg + antenna_wave - antenna_asymmetry
        )

        self._goto(
            pitch=pitch,
            roll=roll,
            yaw=yaw,
            left_antenna=left_antenna,
            right_antenna=right_antenna,
            duration=0.46,
        )

    def nod(self, count: int = 1) -> None:
        count = max(1, min(count, 2))
        for _ in range(count):
            self._goto(
                pitch=self.config.nod_pitch_deg,
                left_antenna=12.0,
                right_antenna=-12.0,
                duration=0.28,
            )
            self._goto(
                pitch=-2.0,
                left_antenna=7.0,
                right_antenna=-7.0,
                duration=0.28,
            )
        self.neutral(duration=0.32)

    def finish(self) -> None:
        self.nod(count=1)
