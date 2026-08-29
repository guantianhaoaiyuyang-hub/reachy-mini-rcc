from __future__ import annotations

import argparse
from pathlib import Path

from reachy_mini import ReachyMini

from config.robot_discovery import discover_robot
from robot.dance_player_v2 import (
    DanceTimeline,
    DanceV2Config,
    ReachyDancePlayerV2,
)


DEFAULT_TIMELINE = Path(
    "music/angel.dance.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reachy Mini Dance Engine V2"
    )

    parser.add_argument(
        "--timeline",
        type=Path,
        default=DEFAULT_TIMELINE,
    )

    parser.add_argument(
        "--intensity",
        type=float,
        default=0.75,
        help="Safe range: 0.30 to 1.00.",
    )

    parser.add_argument(
        "--volume-file",
        type=Path,
        default=Path("runtime/dance_volume.json"),
        help="JSON file used for live software volume.",
    )

    parser.add_argument(
        "--settings-file",
        type=Path,
        default=Path(
            "runtime/dance_motion_settings.json"
        ),
        help="Live motion settings JSON file.",
    )

    args = parser.parse_args()

    intensity = max(
        0.30,
        min(float(args.intensity), 1.00),
    )

    timeline = DanceTimeline(
        args.timeline
    )

    config = DanceV2Config(
        intensity=intensity
    )

    print("=" * 64)
    print("Reachy Mini Dance Engine V2")
    print("=" * 64)
    print(f"Timeline: {timeline.path.name}")
    print(f"Music: {timeline.audio_file}")
    print(f"Intensity: {config.intensity:.2f}")
    print()
    print(
        "Keep at least 30 cm of free space "
        "around the robot."
    )
    print(
        "Press Ctrl+C to stop safely."
    )
    print()

    print("[RCC] Discovering Reachy Mini...")
    robot_host = discover_robot()
    print(f"[RCC] Reachy Mini found: {robot_host}")

    with ReachyMini(
        host=robot_host,
        connection_mode="network",
        media_backend="default",
        automatic_body_yaw=False,
    ) as mini:
        player = ReachyDancePlayerV2(
            mini=mini,
            config=config,
            volume_file=args.volume_file,
            settings_file=args.settings_file,
        )

        try:
            player.prepare()
            player.play(timeline)

            print(
                "[Dance V2] Performance finished."
            )

        except KeyboardInterrupt:
            print(
                "\n[Dance V2] Stopped by user."
            )
            player.stop()

            try:
                player.neutral()
            except Exception:
                pass

        finally:
            try:
                mini.set_automatic_body_yaw(True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
