from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from reachy_mini.utils import create_head_pose


@dataclass(frozen=True)
class MotionConfig:
    duration: float = 0.45
    return_duration: float = 0.55
    antenna_angle_deg: float = 18.0
    nod_pitch_deg: float = 8.0
    tilt_roll_deg: float = 8.0
    look_yaw_deg: float = 12.0


class ReachyMotionController:
    """
    Reachy Mini 保守动作控制器。

    设计原则：
    - 动作幅度小
    - 使用 goto_target 平滑插值
    - 每个动作结束后回到中立位
    - 暂不控制 body_yaw
    """

    def __init__(
        self,
        mini: Any,
        config: MotionConfig | None = None,
    ) -> None:
        self.mini = mini
        self.config = config or MotionConfig()

    def neutral(self, duration: float | None = None) -> None:
        self.mini.goto_target(
            head=create_head_pose(),
            antennas=np.deg2rad([0.0, 0.0]),
            duration=duration or self.config.return_duration,
            method="minjerk",
        )

    def greet(self) -> None:
        """轻微抬头并张开天线。"""
        angle = self.config.antenna_angle_deg

        self.mini.goto_target(
            head=create_head_pose(
                pitch=-5.0,
                degrees=True,
            ),
            antennas=np.deg2rad([angle, -angle]),
            duration=0.55,
            method="cartoon",
        )
        time.sleep(0.15)

        self.mini.goto_target(
            head=create_head_pose(),
            antennas=np.deg2rad([0.0, 0.0]),
            duration=0.55,
            method="minjerk",
        )

    def nod(self, count: int = 2) -> None:
        """小幅点头。"""
        count = max(1, min(count, 3))
        pitch = self.config.nod_pitch_deg

        for _ in range(count):
            self.mini.goto_target(
                head=create_head_pose(
                    pitch=pitch,
                    degrees=True,
                ),
                duration=0.28,
                method="ease_in_out",
            )
            self.mini.goto_target(
                head=create_head_pose(
                    pitch=-2.0,
                    degrees=True,
                ),
                duration=0.28,
                method="ease_in_out",
            )

        self.neutral(duration=0.4)

    def curious(self) -> None:
        """轻微歪头。"""
        roll = self.config.tilt_roll_deg

        self.mini.goto_target(
            head=create_head_pose(
                roll=roll,
                degrees=True,
            ),
            antennas=np.deg2rad([8.0, -8.0]),
            duration=0.5,
            method="cartoon",
        )
        time.sleep(0.25)
        self.neutral()

    def look_left_right(self) -> None:
        """小幅左右看。"""
        yaw = self.config.look_yaw_deg

        self.mini.goto_target(
            head=create_head_pose(
                yaw=yaw,
                degrees=True,
            ),
            duration=0.45,
            method="minjerk",
        )
        self.mini.goto_target(
            head=create_head_pose(
                yaw=-yaw,
                degrees=True,
            ),
            duration=0.65,
            method="minjerk",
        )
        self.neutral()

    def speaking_pulse(self) -> None:
        """一次轻微的说话天线脉冲。"""
        self.mini.goto_target(
            antennas=np.deg2rad([7.0, -7.0]),
            duration=0.22,
            method="ease_in_out",
        )
        self.mini.goto_target(
            antennas=np.deg2rad([0.0, 0.0]),
            duration=0.22,
            method="ease_in_out",
        )

    def listening(self) -> None:
        """倾听状态不执行动作，避免噪声频繁触发和阻塞。"""
        return

    def thinking(self) -> None:
        """思考状态不执行动作，保证豆包尽快开始回答。"""
        return

    def greeting(self) -> None:
        """Greeting state: raise the head and move antennas."""
        self.greet()

    def finish(self) -> None:
        """Ending state: nod once and return to neutral."""
        self.nod(count=1)