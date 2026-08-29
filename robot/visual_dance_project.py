from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from reachy_mini.utils import create_head_pose


@dataclass
class Keyframe:
    time: float
    duration: float
    head_yaw: float
    head_roll: float
    head_pitch: float
    body_yaw: float
    left_antenna: float
    right_antenna: float
    method: str = "minjerk"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Keyframe":
        return cls(
            time=float(payload.get("time", 0.0)),
            duration=max(
                0.10,
                float(payload.get("duration", 0.60)),
            ),
            head_yaw=float(payload.get("head_yaw", 0.0)),
            head_roll=float(payload.get("head_roll", 0.0)),
            head_pitch=float(payload.get("head_pitch", 0.0)),
            body_yaw=float(payload.get("body_yaw", 0.0)),
            left_antenna=float(
                payload.get("left_antenna", -38.0)
            ),
            right_antenna=float(
                payload.get("right_antenna", 38.0)
            ),
            method=str(payload.get("method", "minjerk")),
        )


class VisualDanceProject:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.data = json.loads(
            self.path.read_text(
                encoding="utf-8-sig"
            )
        )
        self.keyframes = sorted(
            [
                Keyframe.from_dict(item)
                for item in self.data.get(
                    "keyframes",
                    [],
                )
            ],
            key=lambda item: item.time,
        )

    def play(self, mini) -> None:
        if not self.keyframes:
            raise RuntimeError(
                "The project contains no visual-editor keyframes."
            )

        started = time.perf_counter()

        for keyframe in self.keyframes:
            target = started + keyframe.time

            while time.perf_counter() < target:
                time.sleep(0.002)

            mini.goto_target(
                head=create_head_pose(
                    yaw=keyframe.head_yaw,
                    roll=keyframe.head_roll,
                    pitch=keyframe.head_pitch,
                    degrees=True,
                ),
                antennas=np.deg2rad(
                    [
                        keyframe.left_antenna,
                        keyframe.right_antenna,
                    ]
                ),
                body_yaw=math.radians(
                    keyframe.body_yaw
                ),
                duration=keyframe.duration,
                method=keyframe.method,
            )
