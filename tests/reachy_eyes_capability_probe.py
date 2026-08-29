from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

from serial.tools import list_ports


TARGET_VID = 0x2E8A
TARGET_PID = 0x10FC


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None
    serial_number: str | None
    manufacturer: str | None
    product: str | None
    likely_reachy_eyes: bool


def collect_ports() -> list[PortInfo]:
    result: list[PortInfo] = []

    for port in list_ports.comports():
        vid = port.vid
        pid = port.pid

        likely = (
            vid == TARGET_VID
            and pid == TARGET_PID
        )

        result.append(
            PortInfo(
                device=str(port.device or ""),
                description=str(port.description or ""),
                hwid=str(port.hwid or ""),
                vid=vid,
                pid=pid,
                serial_number=port.serial_number,
                manufacturer=port.manufacturer,
                product=port.product,
                likely_reachy_eyes=likely,
            )
        )

    return result


def print_port(port: PortInfo) -> None:
    vid_pid = (
        f"{port.vid:04X}:{port.pid:04X}"
        if port.vid is not None
        and port.pid is not None
        else "UNKNOWN"
    )

    marker = (
        "  <== POSSIBLE REACHY EYES"
        if port.likely_reachy_eyes
        else ""
    )

    print(
        f"- {port.device} | "
        f"VID:PID={vid_pid} | "
        f"{port.description}{marker}"
    )
    print(f"  HWID: {port.hwid}")

    if port.manufacturer:
        print(
            f"  Manufacturer: {port.manufacturer}"
        )

    if port.product:
        print(f"  Product: {port.product}")

    if port.serial_number:
        print(
            f"  Serial: {port.serial_number}"
        )


def import_reachy_eyes() -> tuple[Any, str | None]:
    try:
        import reachy_eyes
    except Exception as exc:
        return None, repr(exc)

    return reachy_eyes, None


def safe_close(eyes: Any) -> None:
    for name in (
        "disable_blinking",
        "off",
        "close",
        "disconnect",
    ):
        method = getattr(eyes, name, None)

        if callable(method):
            try:
                method()
            except Exception:
                pass


def perform_safe_test(
    reachy_eyes: Any,
    intensity: float,
) -> None:
    print()
    print("[TEST] Creating eye controller...")

    eyes = None

    try:
        eyes = reachy_eyes.create()

        print(
            "[TEST] Eye controller created successfully."
        )
        print(
            f"[TEST] Setting low intensity: "
            f"{intensity:.2f}"
        )

        set_intensity = getattr(
            eyes,
            "set_intensity",
            None,
        )

        if callable(set_intensity):
            set_intensity(intensity)

        sequence = (
            ("BLUE", 0.8),
            ("CYAN", 0.8),
            ("GREEN", 0.8),
        )

        for color, duration in sequence:
            print(f"[TEST] Color: {color}")
            eyes.set_color(
                color,
                duration=0.15,
            )
            time.sleep(duration)

        blink = getattr(eyes, "blink", None)

        if callable(blink):
            print("[TEST] Blink")
            blink()
            time.sleep(1.0)

        ack = getattr(eyes, "ack", None)

        if callable(ack):
            print("[TEST] Ack")
            ack()
            time.sleep(1.0)

        print("[TEST] Turning eyes off.")
        eyes.off()

        print()
        print(
            "SUCCESS: Reachy Eyes hardware "
            "responded to software commands."
        )

    finally:
        if eyes is not None:
            safe_close(eyes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Non-destructive Reachy Mini eye "
            "hardware capability probe."
        )
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "After discovery, run a low-brightness "
            "color and blink test."
        ),
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=0.12,
        help=(
            "Test intensity from 0.02 to 0.30. "
            "Default: 0.12."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print serial-port data as JSON.",
    )
    args = parser.parse_args()

    intensity = max(
        0.02,
        min(0.30, float(args.intensity)),
    )

    print("=" * 68)
    print("Reachy Mini Eyes Capability Probe")
    print("=" * 68)
    print(f"System: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}")
    print()

    ports = collect_ports()

    print(
        f"[1/3] Serial devices found: "
        f"{len(ports)}"
    )

    if args.json:
        print(
            json.dumps(
                [asdict(port) for port in ports],
                ensure_ascii=False,
                indent=2,
            )
        )
    elif ports:
        for port in ports:
            print_port(port)
    else:
        print("  NONE")

    matching_ports = [
        port
        for port in ports
        if port.likely_reachy_eyes
    ]

    print()
    print("[2/3] Community eye library")

    reachy_eyes, import_error = (
        import_reachy_eyes()
    )

    if reachy_eyes is None:
        print("  reachy_eyes import: FAILED")
        print(f"  Error: {import_error}")
    else:
        version = getattr(
            reachy_eyes,
            "__version__",
            "unknown",
        )
        print("  reachy_eyes import: OK")
        print(f"  Version: {version}")

    print()
    print("[3/3] Assessment")

    if matching_ports:
        print(
            "  Matching USB eye hardware found:"
        )

        for port in matching_ports:
            print(
                f"  - {port.device} "
                f"(VID:PID 2E8A:10FC)"
            )

        if reachy_eyes is None:
            print(
                "  Hardware is visible, but the "
                "Python library is unavailable."
            )
            return 2

        if args.test:
            try:
                perform_safe_test(
                    reachy_eyes,
                    intensity,
                )
                return 0
            except Exception as exc:
                print()
                print(
                    "TEST FAILED:",
                    repr(exc),
                )
                return 3

        print()
        print(
            "  Discovery succeeded. Run again "
            "with --test to light the eyes safely."
        )
        return 0

    print(
        "  No local USB device matched "
        "VID:PID 2E8A:10FC."
    )
    print()
    print(
        "  This does not yet prove the robot "
        "has no eye module."
    )
    print(
        "  On Reachy Mini Wireless, the module "
        "may be connected internally to the "
        "robot's Raspberry Pi rather than to "
        "this Windows computer."
    )
    print(
        "  Next action: run the same probe "
        "through SSH on the robot."
    )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
