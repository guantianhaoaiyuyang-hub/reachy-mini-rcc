from __future__ import annotations

import time
import requests

from config.robot_discovery import discover_robot


class ReachyConnection:
    def __init__(self):
        self.host: str | None = None
        self.base_url: str | None = None
        self.session = requests.Session()

    def discover(self) -> str:
        print("[RCC] Discovering Reachy Mini...")

        self.host = discover_robot()
        self.base_url = f"http://{self.host}:8000"

        print(f"[RCC] Robot address : {self.host}")
        print(f"[RCC] Robot API     : {self.base_url}")

        return self.host

    def _ensure_address(self):
        if not self.host or not self.base_url:
            self.discover()

    def get(self, path: str, timeout: float = 5):
        self._ensure_address()

        url = self.base_url + path
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()

        if response.content:
            return response.json()

        return None

    def post(self, path: str, json=None, timeout: float = 10):
        self._ensure_address()

        url = self.base_url + path
        response = self.session.post(
            url,
            json=json,
            timeout=timeout,
        )
        response.raise_for_status()

        if response.content:
            try:
                return response.json()
            except Exception:
                return response.text

        return None

    def check_daemon(self) -> dict:
        print("[RCC] Checking daemon...")

        status = self.get("/api/daemon/status")

        state = status.get("state")
        version = status.get("version")
        wlan_ip = status.get("wlan_ip")

        print(f"[RCC] Daemon state  : {state}")
        print(f"[RCC] SDK version   : {version}")
        print(f"[RCC] WLAN IP       : {wlan_ip}")

        if state != "running":
            raise RuntimeError(
                f"Reachy daemon is not running: {state}"
            )

        return status

    def check_media(self) -> dict:
        print("[RCC] Checking media...")

        status = self.get("/api/media/status")

        print(
            "[RCC] Media          : "
            f"available={status.get('available')}, "
            f"released={status.get('released')}"
        )

        return status

    def get_motor_mode(self) -> str:
        status = self.get("/api/motors/status")
        return status.get("mode", "unknown")

    def enable_motors(self):
        mode = self.get_motor_mode()

        print(f"[RCC] Motor mode     : {mode}")

        if mode == "enabled":
            print("[RCC] Motors already enabled.")
            return

        print("[RCC] Enabling motors...")

        self.post("/api/motors/set_mode/enabled")

        time.sleep(1)

        mode = self.get_motor_mode()

        if mode != "enabled":
            raise RuntimeError(
                f"Failed to enable motors. Current mode: {mode}"
            )

        print("[RCC] Motors enabled.")

    def wake_up(self):
        print("[RCC] Sending wake-up command...")

        self.post("/api/move/play/wake_up")

        time.sleep(2)

        print("[RCC] Wake-up command sent.")

    def connect(self, wake: bool = True):
        print()
        print("========================================")
        print(" RCC Reachy Mini Connection")
        print("========================================")

        self.discover()
        self.check_daemon()
        self.check_media()

        if wake:
            self.enable_motors()
            self.wake_up()

        print()
        print("========================================")
        print(" Reachy Mini READY")
        print("========================================")
        print(f" HOST : {self.host}")
        print(f" API  : {self.base_url}")
        print()

        return self


if __name__ == "__main__":
    robot = ReachyConnection()
    robot.connect()
