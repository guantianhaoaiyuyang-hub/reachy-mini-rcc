from __future__ import annotations

import importlib.util
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import shutil
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
from reachy_mini import ReachyMini


from config.robot_discovery import discover_robot
import asyncio
from bleak import BleakClient, BleakScanner
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = PROJECT_ROOT / "resources" / "icons"
PNG_ICON = ICON_DIR / "reachy_control_center.png"
ICO_ICON = ICON_DIR / "reachy_control_center.ico"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
PREVIEW_FILE = RUNTIME_DIR / "vision_preview.jpg"
MUSIC_LIBRARY_DIR = PROJECT_ROOT / "music" / "library"
DANCE_PROJECT_DIR = PROJECT_ROOT / "music" / "projects"
DANCE_VOLUME_FILE = RUNTIME_DIR / "dance_volume.json"
DANCE_MOTION_SETTINGS_FILE = RUNTIME_DIR / "dance_motion_settings.json"
ROBOT_HOST = None
BLE_SERVICE_ADV = "12345678-1234-5678-1234-56789abcdef3"
BLE_CHAR_WRITE = "12345678-1234-5678-1234-56789abcdef1"
BLE_CHAR_NOTIFY = "12345678-1234-5678-1234-56789abcdef2"
BLE_CHAR_NET = "12345678-1234-5678-1234-56789abcdef4"
BLE_CHAR_STATE = "12345678-1234-5678-1234-56789abcdef5"
BLE_CHAR_COMMANDS = "12345678-1234-5678-1234-56789abcdef6"
BLE_CHAR_HWID = "12345678-1234-5678-1234-56789abcdef7"
BLE_LAST_KNOWN_ADDRESS = "88:A2:9E:79:4D:C7"

def _get_robot_host(force_rediscover=False):
    global ROBOT_HOST

    if ROBOT_HOST and not force_rediscover:
        return ROBOT_HOST

    ROBOT_HOST = discover_robot()
    return ROBOT_HOST


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


@dataclass(frozen=True)
class ModeInfo:
    key: str
    title: str
    subtitle: str
    badge: str
    module: str
    description: str
    accent: str


MODES = (
    ModeInfo(
        "v1", "V1", "豆包实时语音", "LEGACY",
        "tests.reachy_doubao_realtime_test",
        "第一代豆包实时语音版本，不包含 V2/V3 动作状态机。",
        "#60A5FA",
    ),
    ModeInfo(
        "v2", "V2", "语音动作状态机", "CLASSIC",
        "tests.reachy_voice_motion_v2_test",
        "豆包实时语音与六状态动作系统。",
        "#A78BFA",
    ),
    ModeInfo(
        "v35", "V3.5", "实时语音与行为动作", "CURRENT",
        "tests.reachy_voice_motion_v3_test",
        "当前 Motion V3.5 行为层与连续讲话动作。",
        "#38BDF8",
    ),
    ModeInfo(
        "vision", "VISION", "人脸追踪与监视器", "VISION",
        "tests.reachy_mediapipe_face_tracking_test",
        "独立人脸检测、头部追踪与实时监视器。",
        "#2DD4BF",
    ),
    ModeInfo(
        "dance", "DANCE", "音乐舞蹈中心", "ENTERTAINMENT",
        "tests.reachy_dance_v2_test",
        "使用预制时间轴驱动音乐、头部、天线与 Body Yaw 联动舞蹈。",
        "#F472B6",
    ),
    ModeInfo(
        "full", "V3.5 + VISION", "完整交互模式", "RECOMMENDED",
        "tests.reachy_voice_motion_v3_vision_test",
        "豆包实时语音、Motion V3.5、人脸追踪与摄像头监视器组合版。",
        "#22D3EE",
    ),
)


class RCCApp(ctk.CTk):
    BG = "#070B12"
    PANEL = "#0C1420"
    PANEL_2 = "#101B2A"
    BORDER = "#1C344B"
    TEXT = "#E7F6FF"
    MUTED = "#7F9BB1"
    CYAN = "#22D3EE"
    GREEN = "#34D399"
    RED = "#FB7185"
    AMBER = "#FBBF24"

    def __init__(self) -> None:
        super().__init__()

        os.chdir(PROJECT_ROOT)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if not DANCE_VOLUME_FILE.exists():
            DANCE_VOLUME_FILE.write_text(
                json.dumps({"volume": 0.25}),
                encoding="utf-8",
            )
        if not DANCE_MOTION_SETTINGS_FILE.exists():
            DANCE_MOTION_SETTINGS_FILE.write_text(
                json.dumps(
                    {
                        "preset": "NORMAL",
                        "total_intensity": 0.72,
                        "head_yaw_scale": 1.0,
                        "head_roll_scale": 1.0,
                        "head_pitch_scale": 1.0,
                        "body_yaw_scale": 1.0,
                        "antenna_scale": 1.0,
                        "motion_speed": 1.0,
                        "updated_at": time.time(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        DANCE_PROJECT_DIR.mkdir(parents=True, exist_ok=True)

        self.title("Reachy Mini Control Center v3.0")
        self.geometry("1380x820")
        self.minsize(1180, 720)
        self.configure(fg_color=self.BG)

        if ICO_ICON.exists():
            try:
                self.iconbitmap(str(ICO_ICON))
            except Exception:
                pass

        self.selected_mode = MODES[-1]
        self.mode_cards = {}
        self.process = None
        self.process_mode = None
        self.robot_awake = False
        self.robot_busy = False
        self.log_queue = queue.Queue()
        self._preview_image = None
        self._preview_mtime = 0.0
        self.dance_intensity = ctk.DoubleVar(value=0.75)
        self.dance_song = ctk.StringVar(value='')
        self.dance_song_map = {}
        self.speaker_volume = ctk.DoubleVar(value=25.0)
        self._volume_after_id = None
        self._pending_speaker_volume = 25
        self.motion_settings_window = None
        self.motion_setting_vars = {
            "total_intensity": ctk.DoubleVar(value=0.72),
            "head_yaw_scale": ctk.DoubleVar(value=1.00),
            "head_roll_scale": ctk.DoubleVar(value=1.00),
            "head_pitch_scale": ctk.DoubleVar(value=1.00),
            "body_yaw_scale": ctk.DoubleVar(value=1.00),
            "antenna_scale": ctk.DoubleVar(value=1.00),
            "motion_speed": ctk.DoubleVar(value=1.00),
        }
        self.motion_setting_labels = {}
        self.motion_preset_name = "NORMAL"
        self.dance_editor_window = None
        self.editor_project = None
        self.editor_timeline_path = None
        self.editor_selected_index = None
        self.editor_keyframe_vars = {
            "time": ctk.DoubleVar(value=0.0),
            "duration": ctk.DoubleVar(value=0.60),
            "head_yaw": ctk.DoubleVar(value=0.0),
            "head_roll": ctk.DoubleVar(value=0.0),
            "head_pitch": ctk.DoubleVar(value=0.0),
            "body_yaw": ctk.DoubleVar(value=0.0),
            "left_antenna": ctk.DoubleVar(value=-38.0),
            "right_antenna": ctk.DoubleVar(value=38.0),
        }
        self.editor_method_var = ctk.StringVar(value="minjerk")
        self.editor_status_var = ctk.StringVar(value="No project loaded")
        self.last_fps = "--"
        self.last_camera = "--"
        self.last_tracking = "IDLE"

        self._build_ui()
        self._refresh_music_library(select_first=True)
        self._select_mode(self.selected_mode)
        self.after(100, self._flush_logs)
        self.after(350, self._poll_process)
        self.after(100, self._refresh_preview)
        self.after(1500, self._refresh_robot_connection)
        self.after(1800, self._refresh_network_panel)
        self.after(2200, self._load_speaker_volume)
        self.protocol("WM_DELETE_WINDOW", self._close_app)

        self._log("SYSTEM", "RCC v3.0 已启动。")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(
            self, height=78, corner_radius=0, fg_color="#09111C"
        )
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        if PNG_ICON.exists():
            icon = ctk.CTkImage(
                light_image=Image.open(PNG_ICON),
                dark_image=Image.open(PNG_ICON),
                size=(52, 52),
            )
            ctk.CTkLabel(header, image=icon, text="").grid(
                row=0, column=0, padx=(20, 12), pady=12
            )
            self._header_icon = icon

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            title_box,
            text="REACHY MINI CONTROL CENTER",
            font=ctk.CTkFont("Segoe UI", 21, "bold"),
            text_color=self.TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="ROBOT INTERACTION PLATFORM  ·  RCC v3.0",
            font=ctk.CTkFont("Consolas", 11),
            text_color=self.MUTED,
        ).pack(anchor="w")

        self.connection_chip = ctk.CTkLabel(
            header, text="●  CHECKING",
            width=135, height=34, corner_radius=17,
            fg_color="#172230", text_color=self.AMBER,
            font=ctk.CTkFont("Consolas", 12, "bold"),
        )
        self.connection_chip.grid(row=0, column=2, padx=22)

        sidebar = ctk.CTkFrame(
            self, width=235, corner_radius=0, fg_color="#08101A"
        )
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar, text="ROBOT STATUS",
            font=ctk.CTkFont("Consolas", 13, "bold"),
            text_color=self.CYAN,
        ).pack(anchor="w", padx=20, pady=(25, 12))

        self.status_labels = {}
        for key, name in (
            ("robot", "Robot"),
            ("motors", "Motors"),
            ("media", "Media"),
            ("program", "Program"),
        ):
            row = ctk.CTkFrame(
                sidebar, height=44, corner_radius=10, fg_color=self.PANEL
            )
            row.pack(fill="x", padx=15, pady=5)
            ctk.CTkLabel(
                row, text=name, text_color=self.MUTED,
                font=ctk.CTkFont("Segoe UI", 12),
            ).pack(side="left", padx=12)
            value = ctk.CTkLabel(
                row, text="UNKNOWN", text_color=self.AMBER,
                font=ctk.CTkFont("Consolas", 10, "bold"),
            )
            value.pack(side="right", padx=12)
            self.status_labels[key] = value

        ctk.CTkLabel(
            sidebar, text="POWER CONTROL",
            font=ctk.CTkFont("Consolas", 13, "bold"),
            text_color=self.CYAN,
        ).pack(anchor="w", padx=20, pady=(25, 12))

        self.power_button = ctk.CTkButton(
            sidebar, text="WAKE ROBOT",
            height=50, corner_radius=12,
            fg_color="#0E7490", hover_color="#0891B2",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            command=self._toggle_power,
        )
        self.power_button.pack(fill="x", padx=15)

        self.stop_button = ctk.CTkButton(
            sidebar, text="STOP CURRENT MODE",
            height=43, corner_radius=12,
            fg_color="#3B1622", hover_color="#5E1D2F",
            border_width=1, border_color="#8B2941",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=self._stop_mode, state="disabled",
        )
        self.stop_button.pack(fill="x", padx=15, pady=(12, 0))

        # NETWORK STATUS / REDISCOVERY
        self.network_frame = ctk.CTkFrame(
            sidebar,
            corner_radius=12,
            fg_color="#151C2B",
            border_width=1,
            border_color="#26344A",
        )
        self.network_frame.pack(fill="x", padx=15, pady=(14, 0))

        ctk.CTkLabel(
            self.network_frame,
            text="NETWORK",
            font=ctk.CTkFont("Consolas", 12, "bold"),
            text_color=self.CYAN,
        ).pack(anchor="w", padx=12, pady=(10, 5))

        self.network_state_label = ctk.CTkLabel(
            self.network_frame,
            text="STATE   CHECKING",
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=self.AMBER,
        )
        self.network_state_label.pack(anchor="w", padx=12, pady=(0, 2))

        self.network_host_label = ctk.CTkLabel(
            self.network_frame,
            text="ROBOT   UNKNOWN",
            font=ctk.CTkFont("Consolas", 10),
            text_color="#A7B3C7",
        )
        self.network_host_label.pack(anchor="w", padx=12, pady=2)

        self.network_wifi_label = ctk.CTkLabel(
            self.network_frame,
            text="PC WIFI UNKNOWN",
            font=ctk.CTkFont("Consolas", 10),
            text_color="#A7B3C7",
        )
        self.network_wifi_label.pack(anchor="w", padx=12, pady=(2, 8))

        self.rediscover_button = ctk.CTkButton(
            self.network_frame,
            text="REDISCOVER ROBOT",
            height=34,
            corner_radius=9,
            fg_color="#184B68",
            hover_color="#1E668E",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            command=self._force_rediscover_robot,
        )
        self.rediscover_button.pack(fill="x", padx=10, pady=(0, 10))

        self.bluetooth_button = ctk.CTkButton(
            self.network_frame,
            text="BLUETOOTH RECOVERY",
            height=34,
            corner_radius=9,
            fg_color="#243B59",
            hover_color="#31557D",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            command=self._open_bluetooth_recovery,
        )
        self.bluetooth_button.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            sidebar,
            text="安全提示\n机器人周围至少保留 30 cm 空间。\n切换模式前先停止当前模式。",
            justify="left", wraplength=195,
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#678399",
        ).pack(side="bottom", anchor="w", padx=20, pady=20)

        main = ctk.CTkFrame(self, fg_color=self.BG, corner_radius=0)
        main.grid(row=1, column=1, sticky="nsew", padx=16, pady=14)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            main, text="VERSION CENTER",
            font=ctk.CTkFont("Segoe UI", 23, "bold"),
            text_color=self.TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            main,
            text="选择一个已验证版本，然后启动交互系统",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self.MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew")

        for column in range(3):
            cards.grid_columnconfigure(column, weight=1)

        for index, mode in enumerate(MODES):
            card = self._create_mode_card(cards, mode)
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=5,
                pady=5,
            )
            self.mode_cards[mode.key] = card

        body = ctk.CTkFrame(main, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        control = ctk.CTkFrame(
            body, height=82, corner_radius=13,
            fg_color=self.PANEL, border_width=1,
            border_color=self.BORDER,
        )
        control.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        control.grid_columnconfigure(0, weight=1)

        self.selected_title = ctk.CTkLabel(
            control, text="",
            font=ctk.CTkFont("Segoe UI", 17, "bold"),
            text_color=self.TEXT,
        )
        self.selected_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 1))

        self.selected_description = ctk.CTkLabel(
            control, text="", justify="left", wraplength=760,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self.MUTED,
        )
        self.selected_description.grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        self.dance_controls = ctk.CTkFrame(
            control,
            fg_color="transparent",
        )
        self.dance_controls.grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
            padx=(8, 8),
        )

        ctk.CTkLabel(
            self.dance_controls,
            text="SONG",
            font=ctk.CTkFont("Consolas", 9, "bold"),
            text_color=self.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.dance_song_menu = ctk.CTkOptionMenu(
            self.dance_controls,
            values=["No music"],
            variable=self.dance_song,
            width=160,
            height=30,
            corner_radius=8,
            fg_color="#17334A",
            button_color="#20506F",
            button_hover_color="#276382",
        )
        self.dance_song_menu.grid(row=1, column=0, padx=(0, 12))

        self.music_buttons = ctk.CTkFrame(
            self.dance_controls,
            fg_color="transparent",
        )
        self.music_buttons.grid(
            row=2,
            column=0,
            rowspan=2,
            sticky="w",
            pady=(7, 0),
        )

        ctk.CTkButton(
            self.music_buttons,
            text="+ ADD",
            width=62,
            height=27,
            corner_radius=7,
            fg_color="#14532D",
            hover_color="#166534",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=self._add_music,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            self.music_buttons,
            text="DELETE",
            width=62,
            height=27,
            corner_radius=7,
            fg_color="#3B1622",
            hover_color="#5E1D2F",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=self._delete_music,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            self.music_buttons,
            text="REFRESH",
            width=66,
            height=27,
            corner_radius=7,
            fg_color="#17334A",
            hover_color="#20506F",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=self._refresh_music_library,
        ).pack(side="left")

        ctk.CTkButton(
            self.music_buttons,
            text="MOTION",
            width=68,
            height=27,
            corner_radius=7,
            fg_color="#5B21B6",
            hover_color="#6D28D9",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=self._open_motion_settings,
        ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            self.music_buttons,
            text="DANCE STUDIO",
            width=102,
            height=27,
            corner_radius=7,
            fg_color="#7C2D12",
            hover_color="#9A3412",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=self._open_dance_editor,
        ).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(
            self.dance_controls,
            text="INTENSITY",
            font=ctk.CTkFont("Consolas", 9, "bold"),
            text_color=self.MUTED,
        ).grid(row=0, column=1, sticky="w")

        self.dance_intensity_label = ctk.CTkLabel(
            self.dance_controls,
            text="75%",
            width=42,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color="#F472B6",
        )
        self.dance_intensity_label.grid(row=0, column=2, sticky="e")

        self.dance_intensity_slider = ctk.CTkSlider(
            self.dance_controls,
            from_=0.30,
            to=1.00,
            number_of_steps=70,
            variable=self.dance_intensity,
            width=150,
            command=self._update_dance_intensity_label,
            button_color="#F472B6",
            button_hover_color="#FB7185",
            progress_color="#9D4EDD",
        )
        self.dance_intensity_slider.grid(
            row=1,
            column=1,
            columnspan=2,
            padx=(0, 4),
        )

        ctk.CTkLabel(
            self.dance_controls,
            text="VOLUME",
            font=ctk.CTkFont("Consolas", 9, "bold"),
            text_color=self.MUTED,
        ).grid(row=2, column=1, sticky="w", pady=(7, 0))

        self.speaker_volume_label = ctk.CTkLabel(
            self.dance_controls,
            text="25%",
            width=42,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color="#22D3EE",
        )
        self.speaker_volume_label.grid(
            row=2,
            column=2,
            sticky="e",
            pady=(7, 0),
        )

        self.speaker_volume_slider = ctk.CTkSlider(
            self.dance_controls,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.speaker_volume,
            width=150,
            command=self._on_volume_slider,
            button_color="#22D3EE",
            button_hover_color="#67E8F9",
            progress_color="#0E7490",
        )
        self.speaker_volume_slider.grid(
            row=3,
            column=1,
            columnspan=2,
            padx=(0, 4),
            pady=(0, 2),
        )

        self.run_button = ctk.CTkButton(
            control, text="▶  RUN SELECTED MODE",
            width=225, height=46, corner_radius=11,
            fg_color="#0E7490", hover_color="#0891B2",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            command=self._start_selected_mode,
        )
        self.run_button.grid(row=0, column=2, rowspan=2, padx=(8, 16))

        monitor = ctk.CTkFrame(
            body, corner_radius=13, fg_color=self.PANEL,
            border_width=1, border_color=self.BORDER,
        )
        monitor.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        monitor.grid_columnconfigure(0, weight=1)
        monitor.grid_rowconfigure(1, weight=1)

        monitor_head = ctk.CTkFrame(monitor, fg_color="transparent")
        monitor_head.grid(row=0, column=0, sticky="ew", padx=13, pady=(10, 5))
        monitor_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            monitor_head, text="LIVE VISION MONITOR",
            font=ctk.CTkFont("Consolas", 12, "bold"),
            text_color=self.CYAN,
        ).grid(row=0, column=0, sticky="w")
        self.preview_status = ctk.CTkLabel(
            monitor_head, text="WAITING",
            font=ctk.CTkFont("Consolas", 9, "bold"),
            text_color=self.MUTED,
        )
        self.preview_status.grid(row=0, column=1)

        self.preview_label = ctk.CTkLabel(
            monitor,
            text="启动 VISION 或 V3.5 + VISION 后\n监控画面将在此显示",
            width=640, height=360, corner_radius=9,
            fg_color="#03070C", text_color="#557185",
            font=ctk.CTkFont("Segoe UI", 12),
        )
        self.preview_label.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(0, 10)
        )

        log_panel = ctk.CTkFrame(
            body, corner_radius=13, fg_color=self.PANEL,
            border_width=1, border_color=self.BORDER,
        )
        log_panel.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)

        log_head = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_head.grid(row=0, column=0, sticky="ew", padx=13, pady=(10, 5))
        log_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            log_head, text="SYSTEM LOG",
            font=ctk.CTkFont("Consolas", 12, "bold"),
            text_color=self.CYAN,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            log_head, text="CLEAR", width=66, height=26,
            corner_radius=7, fg_color=self.PANEL_2,
            hover_color="#19324A", command=self._clear_log,
        ).grid(row=0, column=1)

        self.log_box = ctk.CTkTextbox(
            log_panel, corner_radius=9, fg_color="#050A10",
            border_width=1, border_color="#172B3D",
            font=ctk.CTkFont("Consolas", 10),
            text_color="#B7D7E8",
        )
        self.log_box.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(0, 10)
        )
        self.log_box.configure(state="disabled")

        status_bar = ctk.CTkFrame(
            main, height=36, corner_radius=10, fg_color="#09131D"
        )
        status_bar.grid(row=4, column=0, sticky="ew", pady=(9, 0))
        for c in range(5):
            status_bar.grid_columnconfigure(c, weight=1)

        self.footer_labels = {}
        footer_items = (
            ("robot", "ROBOT  --"),
            ("camera", "CAMERA  --"),
            ("tracking", "TRACKING  IDLE"),
            ("fps", "FPS  --"),
            ("audio", "AUDIO  READY"),
        )
        for i, (key, text) in enumerate(footer_items):
            label = ctk.CTkLabel(
                status_bar, text=text,
                font=ctk.CTkFont("Consolas", 9, "bold"),
                text_color=self.MUTED,
            )
            label.grid(row=0, column=i, pady=8)
            self.footer_labels[key] = label

    def _create_mode_card(self, parent, mode):
        available = self._module_available(mode.module)
        card = ctk.CTkFrame(
            parent, height=102, corner_radius=13,
            fg_color=self.PANEL, border_width=1,
            border_color=self.BORDER,
        )
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=mode.badge if available else "FILE MISSING",
            height=21, corner_radius=6,
            fg_color="#132B3B" if available else "#3A1C25",
            text_color=mode.accent if available else self.RED,
            font=ctk.CTkFont("Consolas", 8, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            card, text=mode.title,
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color=self.TEXT if available else "#637582",
        ).grid(row=1, column=0, sticky="w", padx=12)

        ctk.CTkLabel(
            card, text=mode.subtitle,
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=self.MUTED,
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 7))

        ctk.CTkButton(
            card, text="SELECT", width=72, height=28,
            corner_radius=8, fg_color="#17334A",
            hover_color="#20506F",
            font=ctk.CTkFont("Segoe UI", 9, "bold"),
            command=lambda m=mode: self._select_mode(m),
            state="normal" if available else "disabled",
        ).grid(row=0, column=1, rowspan=3, padx=10)

        return card

    @staticmethod
    def _module_available(module):
        try:
            return importlib.util.find_spec(module) is not None
        except Exception:
            return False

    def _select_mode(self, mode):
        self.selected_mode = mode
        for key, card in self.mode_cards.items():
            chosen = key == mode.key
            card.configure(
                border_width=2 if chosen else 1,
                border_color=mode.accent if chosen else self.BORDER,
                fg_color="#102231" if chosen else self.PANEL,
            )
        self.selected_title.configure(
            text=f"{mode.title}  ·  {mode.subtitle}"
        )
        self.selected_description.configure(text=mode.description)
        if hasattr(self, "dance_controls"):
            if mode.key == "dance":
                self.dance_controls.grid()
                self.run_button.configure(text="♪  START DANCE")
            else:
                self.dance_controls.grid_remove()
                self.run_button.configure(text="▶  RUN SELECTED MODE")

    def _safe_music_key(self, name):
        cleaned = []

        for character in name:
            if character.isalnum():
                cleaned.append(character.lower())
            elif character in {"-", "_"}:
                cleaned.append(character)
            elif character.isspace():
                cleaned.append("_")

        key = "".join(cleaned).strip("_-")

        if not key:
            key = f"song_{int(time.time())}"

        return key[:60]

    def _refresh_music_library(self, select_first=False):
        MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        DANCE_PROJECT_DIR.mkdir(parents=True, exist_ok=True)

        supported = {".mp3", ".wav", ".ogg", ".flac"}
        song_map = {}

        for audio_path in sorted(
            MUSIC_LIBRARY_DIR.iterdir(),
            key=lambda path: path.name.lower(),
        ):
            if (
                not audio_path.is_file()
                or audio_path.suffix.lower() not in supported
            ):
                continue

            key = audio_path.stem
            timeline_path = (
                DANCE_PROJECT_DIR
                / f"{key}.dance.json"
            )

            if not timeline_path.exists():
                continue

            display_name = audio_path.name

            song_map[display_name] = {
                "audio": audio_path,
                "timeline": timeline_path,
            }

        self.dance_song_map = song_map
        values = list(song_map) or ["No music"]

        if hasattr(self, "dance_song_menu"):
            self.dance_song_menu.configure(
                values=values
            )

        current = self.dance_song.get()

        if current not in song_map:
            self.dance_song.set(
                values[0]
            )

        if select_first and song_map:
            self.dance_song.set(values[0])

        if hasattr(self, "log_box"):
            self._log(
                "MUSIC",
                f"音乐库已刷新，共 {len(song_map)} 首。",
            )

    def _add_music(self):
        selected = filedialog.askopenfilename(
            title="Add music to Reachy Dance Studio",
            filetypes=[
                (
                    "Audio files",
                    "*.mp3 *.wav *.ogg *.flac",
                ),
                ("MP3", "*.mp3"),
                ("WAV", "*.wav"),
                ("OGG", "*.ogg"),
                ("FLAC", "*.flac"),
            ],
        )

        if not selected:
            return

        source = Path(selected)

        try:
            from mutagen import File as MutagenFile
        except Exception:
            messagebox.showerror(
                "Missing dependency",
                "缺少 mutagen。请先运行 "
                "scripts\\install_rcc_v3_2.ps1。",
            )
            return

        try:
            audio = MutagenFile(source)
            duration = float(audio.info.length)
        except Exception as exc:
            messagebox.showerror(
                "Unable to read music",
                f"无法读取音乐时长：\n{exc}",
            )
            return

        key = self._safe_music_key(source.stem)
        destination = (
            MUSIC_LIBRARY_DIR
            / f"{key}{source.suffix.lower()}"
        )

        suffix_number = 2

        while (
            destination.exists()
            and destination.resolve() != source.resolve()
        ):
            destination = (
                MUSIC_LIBRARY_DIR
                / f"{key}_{suffix_number}"
                f"{source.suffix.lower()}"
            )
            suffix_number += 1

        key = destination.stem
        timeline_path = (
            DANCE_PROJECT_DIR
            / f"{key}.dance.json"
        )

        try:
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)

            project = self._build_default_dance_project(
                key=key,
                audio_filename=destination.name,
                title=source.stem,
                duration=duration,
            )

            timeline_path.write_text(
                json.dumps(
                    project,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        except Exception as exc:
            messagebox.showerror(
                "Add music failed",
                f"音乐添加失败：\n{exc}",
            )
            return

        self._refresh_music_library()
        self.dance_song.set(destination.name)

        self._log(
            "MUSIC",
            f"已添加 {destination.name}，"
            f"时长 {duration:.1f} 秒。",
        )

    def _build_default_dance_project(
        self,
        key,
        audio_filename,
        title,
        duration,
    ):
        interval = 0.84
        motions = [
            "sway_left",
            "sway_right",
            "nod_left",
            "nod_right",
            "open_left",
            "open_right",
            "soft_left",
            "soft_right",
        ]

        events = []
        event_time = 0.8
        index = 0

        while event_time < max(0.8, duration - 1.5):
            progress = (
                event_time / max(duration, 0.1)
            )

            if progress < 0.12:
                energy = 0.55
                section = "intro"
            elif progress < 0.45:
                energy = 0.68
                section = "verse"
            elif progress < 0.78:
                energy = 0.88
                section = "chorus"
            elif progress < 0.92:
                energy = 0.72
                section = "bridge"
            else:
                energy = max(
                    0.30,
                    0.72
                    * (
                        (1.0 - progress)
                        / 0.08
                    ),
                )
                section = "ending"

            events.append(
                {
                    "time": round(event_time, 3),
                    "motion": motions[
                        index % len(motions)
                    ],
                    "energy": round(
                        min(1.0, energy),
                        3,
                    ),
                    "section": section,
                }
            )

            event_time += interval
            index += 1

        return {
            "format": "reachy-dance-timeline-v2",
            "title": title,
            "audio_file": (
                "../library/"
                + audio_filename
            ),
            "duration": duration,
            "source_bpm": 0.0,
            "motion_bpm": round(60.0 / interval, 3),
            "style": "generic",
            "events": events,
        }

    def _delete_music(self):
        display_name = self.dance_song.get()
        info = self.dance_song_map.get(display_name)

        if info is None:
            return

        confirmed = messagebox.askyesno(
            "Delete music",
            "确定删除这首音乐及对应舞蹈工程吗？\n\n"
            f"{display_name}",
        )

        if not confirmed:
            return

        try:
            info["audio"].unlink(missing_ok=True)
            info["timeline"].unlink(missing_ok=True)
        except Exception as exc:
            messagebox.showerror(
                "Delete failed",
                f"删除失败：\n{exc}",
            )
            return

        self._refresh_music_library(
            select_first=True
        )

        self._log(
            "MUSIC",
            f"已删除 {display_name}。",
        )


    def _open_dance_editor(self):
        display_name = self.dance_song.get()
        info = self.dance_song_map.get(display_name)

        if info is None:
            messagebox.showwarning(
                "No song selected",
                "请先在 Music Library 中选择一首音乐。",
            )
            return

        if (
            self.dance_editor_window is not None
            and self.dance_editor_window.winfo_exists()
        ):
            self.dance_editor_window.focus()
            return

        try:
            project = json.loads(
                info["timeline"].read_text(
                    encoding="utf-8-sig"
                )
            )
        except Exception as exc:
            messagebox.showerror(
                "Open failed",
                f"无法读取舞蹈工程：\n{exc}",
            )
            return

        self.editor_project = project
        self.editor_timeline_path = info["timeline"]
        self.editor_selected_index = None

        window = ctk.CTkToplevel(self)
        window.title("RCC v4.0 Visual Dance Editor")
        window.geometry("1180x760")
        window.minsize(1020, 680)
        window.configure(fg_color=self.BG)
        window.transient(self)
        self.dance_editor_window = window

        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, weight=1)
        window.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        header.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(18, 10),
        )
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="DANCE STUDIO",
            font=ctk.CTkFont("Segoe UI", 21, "bold"),
            text_color=self.TEXT,
        ).grid(
            row=0,
            column=0,
            padx=16,
            pady=(12, 3),
            sticky="w",
        )

        ctk.CTkLabel(
            header,
            text=display_name,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#22D3EE",
        ).grid(
            row=0,
            column=1,
            padx=10,
            pady=(12, 3),
            sticky="w",
        )

        ctk.CTkLabel(
            header,
            textvariable=self.editor_status_var,
            font=ctk.CTkFont("Consolas", 10),
            text_color=self.MUTED,
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            padx=16,
            pady=(0, 12),
            sticky="w",
        )

        timeline_frame = ctk.CTkFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        timeline_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 10),
        )
        timeline_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            timeline_frame,
            text="TIMELINE",
            font=ctk.CTkFont("Consolas", 11, "bold"),
            text_color="#22D3EE",
        ).grid(
            row=0,
            column=0,
            padx=14,
            pady=12,
            sticky="w",
        )

        duration = float(
            self.editor_project.get("duration", 60.0)
        )
        self.editor_time_slider = ctk.CTkSlider(
            timeline_frame,
            from_=0.0,
            to=max(1.0, duration),
            number_of_steps=max(100, int(duration * 10)),
            variable=self.editor_keyframe_vars["time"],
            command=self._editor_time_changed,
            progress_color="#0E7490",
            button_color="#22D3EE",
            button_hover_color="#67E8F9",
        )
        self.editor_time_slider.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=12,
            pady=12,
        )

        self.editor_time_label = ctk.CTkLabel(
            timeline_frame,
            text="0.00 s",
            width=84,
            font=ctk.CTkFont("Consolas", 11, "bold"),
            text_color=self.TEXT,
        )
        self.editor_time_label.grid(
            row=0,
            column=2,
            padx=(0, 14),
        )

        list_panel = ctk.CTkFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        list_panel.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(18, 7),
            pady=(0, 12),
        )
        list_panel.grid_columnconfigure(0, weight=1)
        list_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            list_panel,
            text="KEYFRAMES",
            font=ctk.CTkFont("Consolas", 12, "bold"),
            text_color="#22D3EE",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=14,
            pady=(12, 6),
        )

        self.editor_keyframe_list = ctk.CTkScrollableFrame(
            list_panel,
            fg_color="#050B12",
            corner_radius=8,
        )
        self.editor_keyframe_list.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 10),
        )
        self.editor_keyframe_list.grid_columnconfigure(0, weight=1)

        list_actions = ctk.CTkFrame(
            list_panel,
            fg_color="transparent",
        )
        list_actions.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 12),
        )
        list_actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            list_actions,
            text="+ ADD",
            height=36,
            fg_color="#14532D",
            hover_color="#166534",
            command=self._editor_add_keyframe,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            list_actions,
            text="UPDATE",
            height=36,
            fg_color="#0E7490",
            hover_color="#0891B2",
            command=self._editor_update_keyframe,
        ).grid(row=0, column=1, sticky="ew", padx=4)

        ctk.CTkButton(
            list_actions,
            text="DELETE",
            height=36,
            fg_color="#4C0519",
            hover_color="#881337",
            command=self._editor_delete_keyframe,
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        edit_panel = ctk.CTkScrollableFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        edit_panel.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(7, 18),
            pady=(0, 12),
        )
        edit_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            edit_panel,
            text="KEYFRAME EDITOR",
            font=ctk.CTkFont("Consolas", 12, "bold"),
            text_color="#A855F7",
        ).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
            padx=12,
            pady=(12, 8),
        )

        specs = (
            ("time", "时间", 0.0, max(1.0, duration), "s"),
            ("duration", "过渡时长", 0.10, 2.00, "s"),
            ("head_yaw", "头部左右", -24.0, 24.0, "°"),
            ("head_roll", "头部侧倾", -15.0, 15.0, "°"),
            ("head_pitch", "点头", -12.0, 12.0, "°"),
            ("body_yaw", "底座旋转", -21.0, 21.0, "°"),
            ("left_antenna", "左天线", -82.0, 18.0, "°"),
            ("right_antenna", "右天线", -18.0, 82.0, "°"),
        )

        self.editor_value_labels = {}

        for row, (key, title, minimum, maximum, suffix) in enumerate(
            specs,
            start=1,
        ):
            ctk.CTkLabel(
                edit_panel,
                text=title,
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=self.TEXT,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(12, 10),
                pady=9,
            )

            slider = ctk.CTkSlider(
                edit_panel,
                from_=minimum,
                to=maximum,
                number_of_steps=200,
                variable=self.editor_keyframe_vars[key],
                command=lambda value, name=key, unit=suffix: (
                    self._editor_parameter_changed(name, value, unit)
                ),
                progress_color="#7E22CE",
                button_color="#A855F7",
                button_hover_color="#C084FC",
            )
            slider.grid(
                row=row,
                column=1,
                sticky="ew",
                padx=8,
                pady=9,
            )

            label = ctk.CTkLabel(
                edit_panel,
                text="0.00",
                width=76,
                font=ctk.CTkFont("Consolas", 11, "bold"),
                text_color="#F0ABFC",
            )
            label.grid(
                row=row,
                column=2,
                padx=(8, 12),
            )
            self.editor_value_labels[key] = (label, suffix)

        ctk.CTkLabel(
            edit_panel,
            text="插值方式",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=self.TEXT,
        ).grid(
            row=10,
            column=0,
            sticky="w",
            padx=(12, 10),
            pady=9,
        )

        ctk.CTkOptionMenu(
            edit_panel,
            variable=self.editor_method_var,
            values=["minjerk", "linear"],
            fg_color="#17334A",
            button_color="#20506F",
            button_hover_color="#286889",
        ).grid(
            row=10,
            column=1,
            sticky="ew",
            padx=8,
            pady=9,
        )

        preview_actions = ctk.CTkFrame(
            edit_panel,
            fg_color="transparent",
        )
        preview_actions.grid(
            row=11,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=12,
            pady=(14, 10),
        )
        preview_actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            preview_actions,
            text="PREVIEW POSE",
            height=42,
            fg_color="#0E7490",
            hover_color="#0891B2",
            command=self._editor_preview_pose,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 5),
        )

        ctk.CTkButton(
            preview_actions,
            text="RETURN NEUTRAL",
            height=42,
            fg_color="#334155",
            hover_color="#475569",
            command=self._editor_return_neutral,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(5, 0),
        )

        footer = ctk.CTkFrame(
            window,
            fg_color="transparent",
        )
        footer.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 18),
        )
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer,
            text="SAVE PROJECT",
            height=44,
            fg_color="#0E7490",
            hover_color="#0891B2",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=self._editor_save_project,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        ctk.CTkButton(
            footer,
            text="CLOSE",
            width=120,
            height=44,
            fg_color="#334155",
            hover_color="#475569",
            command=window.destroy,
        ).grid(
            row=0,
            column=1,
            padx=(6, 0),
        )

        self._editor_refresh_keyframe_list()
        self._editor_refresh_value_labels()
        self._editor_update_status()

    def _editor_events(self):
        if not isinstance(self.editor_project, dict):
            return []

        events = self.editor_project.setdefault(
            "keyframes",
            []
        )

        if not events:
            legacy_events = self.editor_project.get(
                "events",
                []
            )
            if legacy_events:
                converted = []
                for event in legacy_events:
                    converted.append(
                        {
                            "time": float(event.get("time", 0.0)),
                            "duration": 0.60,
                            "head_yaw": 0.0,
                            "head_roll": 0.0,
                            "head_pitch": 0.0,
                            "body_yaw": 0.0,
                            "left_antenna": -38.0,
                            "right_antenna": 38.0,
                            "method": "minjerk",
                            "source_motion": event.get("motion", ""),
                        }
                    )
                self.editor_project["keyframes"] = converted
                events = converted

        events.sort(
            key=lambda item: float(item.get("time", 0.0))
        )
        return events

    def _editor_update_status(self):
        events = self._editor_events()
        title = (
            self.editor_project.get("title", "Untitled")
            if isinstance(self.editor_project, dict)
            else "Untitled"
        )
        duration = (
            float(self.editor_project.get("duration", 0.0))
            if isinstance(self.editor_project, dict)
            else 0.0
        )
        self.editor_status_var.set(
            f"{title}  |  {duration:.1f}s  |  {len(events)} keyframes"
        )

    def _editor_time_changed(self, value):
        numeric = float(value)
        self.editor_time_label.configure(
            text=f"{numeric:.2f} s"
        )
        if "time" in self.editor_value_labels:
            label, suffix = self.editor_value_labels["time"]
            label.configure(text=f"{numeric:.2f}{suffix}")

    def _editor_parameter_changed(self, key, value, suffix):
        numeric = float(value)
        item = self.editor_value_labels.get(key)
        if item is not None:
            label, _ = item
            label.configure(
                text=f"{numeric:.2f}{suffix}"
            )
        if key == "time":
            self.editor_time_label.configure(
                text=f"{numeric:.2f} s"
            )

    def _editor_refresh_value_labels(self):
        for key, item in self.editor_value_labels.items():
            label, suffix = item
            value = float(
                self.editor_keyframe_vars[key].get()
            )
            label.configure(
                text=f"{value:.2f}{suffix}"
            )
        self.editor_time_label.configure(
            text=(
                f"{float(self.editor_keyframe_vars['time'].get()):.2f} s"
            )
        )

    def _editor_refresh_keyframe_list(self):
        if not hasattr(self, "editor_keyframe_list"):
            return

        for child in self.editor_keyframe_list.winfo_children():
            child.destroy()

        events = self._editor_events()

        for index, event in enumerate(events):
            selected = index == self.editor_selected_index

            button = ctk.CTkButton(
                self.editor_keyframe_list,
                text=(
                    f"{index + 1:03d}   "
                    f"{float(event.get('time', 0.0)):7.2f}s   "
                    f"Y {float(event.get('head_yaw', 0.0)):6.1f}°   "
                    f"B {float(event.get('body_yaw', 0.0)):6.1f}°"
                ),
                height=34,
                anchor="w",
                fg_color=(
                    "#0E7490"
                    if selected
                    else "#0F1B29"
                ),
                hover_color="#17334A",
                font=ctk.CTkFont("Consolas", 10),
                command=lambda idx=index: (
                    self._editor_select_keyframe(idx)
                ),
            )
            button.grid(
                row=index,
                column=0,
                sticky="ew",
                padx=4,
                pady=3,
            )

    def _editor_select_keyframe(self, index):
        events = self._editor_events()

        if not 0 <= index < len(events):
            return

        self.editor_selected_index = index
        event = events[index]

        for key in self.editor_keyframe_vars:
            try:
                value = float(
                    event.get(
                        key,
                        self.editor_keyframe_vars[key].get(),
                    )
                )
            except (TypeError, ValueError):
                continue
            self.editor_keyframe_vars[key].set(value)

        self.editor_method_var.set(
            str(event.get("method", "minjerk"))
        )

        self._editor_refresh_value_labels()
        self._editor_refresh_keyframe_list()

    def _editor_keyframe_from_form(self):
        return {
            "time": round(
                float(self.editor_keyframe_vars["time"].get()),
                3,
            ),
            "duration": round(
                float(self.editor_keyframe_vars["duration"].get()),
                3,
            ),
            "head_yaw": round(
                float(self.editor_keyframe_vars["head_yaw"].get()),
                3,
            ),
            "head_roll": round(
                float(self.editor_keyframe_vars["head_roll"].get()),
                3,
            ),
            "head_pitch": round(
                float(self.editor_keyframe_vars["head_pitch"].get()),
                3,
            ),
            "body_yaw": round(
                float(self.editor_keyframe_vars["body_yaw"].get()),
                3,
            ),
            "left_antenna": round(
                float(self.editor_keyframe_vars["left_antenna"].get()),
                3,
            ),
            "right_antenna": round(
                float(self.editor_keyframe_vars["right_antenna"].get()),
                3,
            ),
            "method": self.editor_method_var.get(),
        }

    def _editor_add_keyframe(self):
        events = self._editor_events()
        events.append(
            self._editor_keyframe_from_form()
        )
        events.sort(
            key=lambda item: float(item.get("time", 0.0))
        )
        current_time = float(
            self.editor_keyframe_vars["time"].get()
        )
        self.editor_selected_index = min(
            range(len(events)),
            key=lambda idx: abs(
                float(events[idx].get("time", 0.0))
                - current_time
            ),
        )
        self._editor_refresh_keyframe_list()
        self._editor_update_status()

    def _editor_update_keyframe(self):
        events = self._editor_events()

        if (
            self.editor_selected_index is None
            or not 0 <= self.editor_selected_index < len(events)
        ):
            messagebox.showwarning(
                "No keyframe selected",
                "请先选择一个关键帧。",
            )
            return

        events[self.editor_selected_index] = (
            self._editor_keyframe_from_form()
        )
        events.sort(
            key=lambda item: float(item.get("time", 0.0))
        )
        self._editor_refresh_keyframe_list()
        self._editor_update_status()

    def _editor_delete_keyframe(self):
        events = self._editor_events()

        if (
            self.editor_selected_index is None
            or not 0 <= self.editor_selected_index < len(events)
        ):
            return

        del events[self.editor_selected_index]
        self.editor_selected_index = None
        self._editor_refresh_keyframe_list()
        self._editor_update_status()

    def _editor_preview_pose(self):
        pose = self._editor_keyframe_from_form()

        script = (
            "from reachy_mini import ReachyMini;"
            "from reachy_mini.utils import create_head_pose;"
            "import numpy as np, math;"
            f"mini=ReachyMini(host='{_get_robot_host()}');"
            "mini.enable_motors();"
            f"mini.goto_target("
            f"head=create_head_pose("
            f"yaw={pose['head_yaw']},"
            f"roll={pose['head_roll']},"
            f"pitch={pose['head_pitch']},"
            f"degrees=True),"
            f"antennas=np.deg2rad([{pose['left_antenna']},{pose['right_antenna']}]),"
            f"body_yaw=math.radians({pose['body_yaw']}),"
            f"duration={max(0.15, pose['duration'])},"
            f"method='{pose['method']}');"
            "mini.close()"
        )

        try:
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                ],
                cwd=str(PROJECT_ROOT),
            )
            self._log(
                "EDITOR",
                "正在预览当前关键帧。",
            )
        except Exception as exc:
            messagebox.showerror(
                "Preview failed",
                f"动作预览失败：\n{exc}",
            )

    def _editor_return_neutral(self):
        script = (
            "from reachy_mini import ReachyMini;"
            "from reachy_mini.utils import create_head_pose;"
            "import numpy as np;"
            f"mini=ReachyMini(host='{_get_robot_host()}');"
            "mini.enable_motors();"
            "mini.goto_target("
            "head=create_head_pose(),"
            "antennas=np.deg2rad([0.0,0.0]),"
            "body_yaw=0.0,"
            "duration=0.8,"
            "method='minjerk');"
            "mini.close()"
        )

        try:
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                ],
                cwd=str(PROJECT_ROOT),
            )
        except Exception as exc:
            messagebox.showerror(
                "Return failed",
                f"回中位失败：\n{exc}",
            )

    def _editor_save_project(self):
        if (
            self.editor_timeline_path is None
            or not isinstance(self.editor_project, dict)
        ):
            return

        try:
            self.editor_project["editor_version"] = "4.0-alpha"
            self.editor_project["keyframes"] = self._editor_events()
            self.editor_timeline_path.write_text(
                json.dumps(
                    self.editor_project,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror(
                "Save failed",
                f"保存失败：\n{exc}",
            )
            return

        self._editor_update_status()
        self._log(
            "EDITOR",
            f"舞蹈工程已保存：{self.editor_timeline_path.name}",
        )
        messagebox.showinfo(
            "Saved",
            "舞蹈工程已经保存。",
        )

    def _motion_presets(self):
        return {
            "GENTLE": {
                "total_intensity": 0.52,
                "head_yaw_scale": 0.65,
                "head_roll_scale": 0.60,
                "head_pitch_scale": 0.60,
                "body_yaw_scale": 0.55,
                "antenna_scale": 0.65,
                "motion_speed": 0.82,
            },
            "NORMAL": {
                "total_intensity": 0.72,
                "head_yaw_scale": 1.00,
                "head_roll_scale": 1.00,
                "head_pitch_scale": 1.00,
                "body_yaw_scale": 1.00,
                "antenna_scale": 1.00,
                "motion_speed": 1.00,
            },
            "ENERGETIC": {
                "total_intensity": 0.92,
                "head_yaw_scale": 1.20,
                "head_roll_scale": 1.18,
                "head_pitch_scale": 1.18,
                "body_yaw_scale": 1.22,
                "antenna_scale": 1.28,
                "motion_speed": 1.22,
            },
        }

    def _open_motion_settings(self):
        if (
            self.motion_settings_window is not None
            and self.motion_settings_window.winfo_exists()
        ):
            self.motion_settings_window.focus()
            return

        self._load_motion_settings_for_selected_song()

        window = ctk.CTkToplevel(self)
        window.title("Dance Motion Settings")
        window.geometry("570x670")
        window.minsize(520, 620)
        window.configure(fg_color=self.BG)
        window.transient(self)
        self.motion_settings_window = window

        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            window,
            text="DANCE MOTION CONTROL",
            font=ctk.CTkFont("Segoe UI", 21, "bold"),
            text_color=self.TEXT,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=22,
            pady=(20, 2),
        )

        ctk.CTkLabel(
            window,
            text=(
                "参数会保存到当前歌曲工程；"
                "舞蹈播放期间拖动滑块也会实时生效。"
            ),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self.MUTED,
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=22,
            pady=(0, 14),
        )

        preset_frame = ctk.CTkFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        preset_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=20,
            pady=(0, 12),
        )
        for column in range(3):
            preset_frame.grid_columnconfigure(
                column,
                weight=1,
            )

        preset_specs = (
            ("GENTLE", "GENTLE\n温柔", "#0F766E"),
            ("NORMAL", "NORMAL\n标准", "#0E7490"),
            ("ENERGETIC", "ENERGETIC\n活力", "#9D174D"),
        )

        for column, (key, title, color) in enumerate(
            preset_specs
        ):
            ctk.CTkButton(
                preset_frame,
                text=title,
                height=54,
                corner_radius=10,
                fg_color=color,
                hover_color=color,
                font=ctk.CTkFont(
                    "Segoe UI",
                    12,
                    "bold",
                ),
                command=lambda name=key: (
                    self._apply_motion_preset(name)
                ),
            ).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=6,
                pady=8,
            )

        sliders_frame = ctk.CTkScrollableFrame(
            window,
            fg_color=self.PANEL,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER,
        )
        sliders_frame.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=20,
            pady=(0, 12),
        )
        sliders_frame.grid_columnconfigure(1, weight=1)

        slider_specs = (
            (
                "total_intensity",
                "总动作强度",
                0.30,
                1.00,
                70,
                "percent",
            ),
            (
                "head_yaw_scale",
                "头部左右幅度",
                0.30,
                1.35,
                105,
                "scale",
            ),
            (
                "head_roll_scale",
                "头部侧倾幅度",
                0.30,
                1.35,
                105,
                "scale",
            ),
            (
                "head_pitch_scale",
                "点头幅度",
                0.30,
                1.35,
                105,
                "scale",
            ),
            (
                "body_yaw_scale",
                "底座旋转幅度",
                0.25,
                1.35,
                110,
                "scale",
            ),
            (
                "antenna_scale",
                "天线运动幅度",
                0.30,
                1.40,
                110,
                "scale",
            ),
            (
                "motion_speed",
                "动作速度",
                0.65,
                1.35,
                70,
                "scale",
            ),
        )

        for row, spec in enumerate(slider_specs):
            (
                key,
                title,
                minimum,
                maximum,
                steps,
                display_mode,
            ) = spec

            ctk.CTkLabel(
                sliders_frame,
                text=title,
                font=ctk.CTkFont(
                    "Segoe UI",
                    12,
                ),
                text_color=self.TEXT,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(10, 12),
                pady=11,
            )

            slider = ctk.CTkSlider(
                sliders_frame,
                from_=minimum,
                to=maximum,
                number_of_steps=steps,
                variable=self.motion_setting_vars[key],
                command=lambda value, name=key, mode=display_mode: (
                    self._on_motion_setting_change(
                        name,
                        value,
                        mode,
                    )
                ),
                button_color="#A855F7",
                button_hover_color="#C084FC",
                progress_color="#7E22CE",
            )
            slider.grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(0, 12),
                pady=11,
            )

            value_label = ctk.CTkLabel(
                sliders_frame,
                text="",
                width=62,
                font=ctk.CTkFont(
                    "Consolas",
                    11,
                    "bold",
                ),
                text_color="#F0ABFC",
            )
            value_label.grid(
                row=row,
                column=2,
                padx=(0, 10),
            )
            self.motion_setting_labels[key] = (
                value_label,
                display_mode,
            )

        action_frame = ctk.CTkFrame(
            window,
            fg_color="transparent",
        )
        action_frame.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=20,
            pady=(0, 18),
        )
        action_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            action_frame,
            text="SAVE TO CURRENT SONG",
            height=44,
            corner_radius=10,
            fg_color="#0E7490",
            hover_color="#0891B2",
            font=ctk.CTkFont(
                "Segoe UI",
                12,
                "bold",
            ),
            command=self._save_motion_settings_to_song,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        ctk.CTkButton(
            action_frame,
            text="CLOSE",
            width=110,
            height=44,
            corner_radius=10,
            fg_color="#334155",
            hover_color="#475569",
            command=window.destroy,
        ).grid(
            row=0,
            column=1,
            padx=(6, 0),
        )

        self._refresh_motion_setting_labels()
        self._write_motion_settings_file()

    def _on_motion_setting_change(
        self,
        key,
        value,
        display_mode,
    ):
        self.motion_preset_name = "CUSTOM"
        self._refresh_motion_setting_label(
            key,
            float(value),
            display_mode,
        )
        self._write_motion_settings_file()

    def _refresh_motion_setting_label(
        self,
        key,
        value,
        display_mode,
    ):
        item = self.motion_setting_labels.get(key)

        if item is None:
            return

        label, _ = item

        if display_mode == "percent":
            text = f"{int(round(value * 100))}%"
        else:
            text = f"{value:.2f}×"

        label.configure(text=text)

    def _refresh_motion_setting_labels(self):
        for key, item in self.motion_setting_labels.items():
            _, display_mode = item
            self._refresh_motion_setting_label(
                key,
                float(
                    self.motion_setting_vars[
                        key
                    ].get()
                ),
                display_mode,
            )

    def _apply_motion_preset(self, preset_name):
        preset = self._motion_presets()[
            preset_name
        ]

        self.motion_preset_name = preset_name

        for key, value in preset.items():
            self.motion_setting_vars[key].set(
                value
            )

        self.dance_intensity.set(
            preset["total_intensity"]
        )
        self.dance_intensity_label.configure(
            text=(
                f"{int(preset['total_intensity'] * 100)}%"
            )
        )

        self._refresh_motion_setting_labels()
        self._write_motion_settings_file()

        self._log(
            "MOTION",
            f"已应用 {preset_name} 舞蹈预设。",
        )

    def _current_motion_settings(self):
        return {
            "preset": self.motion_preset_name,
            "total_intensity": float(
                self.motion_setting_vars[
                    "total_intensity"
                ].get()
            ),
            "head_yaw_scale": float(
                self.motion_setting_vars[
                    "head_yaw_scale"
                ].get()
            ),
            "head_roll_scale": float(
                self.motion_setting_vars[
                    "head_roll_scale"
                ].get()
            ),
            "head_pitch_scale": float(
                self.motion_setting_vars[
                    "head_pitch_scale"
                ].get()
            ),
            "body_yaw_scale": float(
                self.motion_setting_vars[
                    "body_yaw_scale"
                ].get()
            ),
            "antenna_scale": float(
                self.motion_setting_vars[
                    "antenna_scale"
                ].get()
            ),
            "motion_speed": float(
                self.motion_setting_vars[
                    "motion_speed"
                ].get()
            ),
            "updated_at": time.time(),
        }

    def _write_motion_settings_file(self):
        settings = self._current_motion_settings()

        temporary = (
            DANCE_MOTION_SETTINGS_FILE
            .with_suffix(".tmp")
        )

        try:
            temporary.write_text(
                json.dumps(
                    settings,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(
                temporary,
                DANCE_MOTION_SETTINGS_FILE,
            )
        except Exception as exc:
            self._queue_log(
                "[MOTION] Failed to write settings: "
                f"{exc!r}\n"
            )

    def _load_motion_settings_for_selected_song(self):
        display_name = self.dance_song.get()
        info = self.dance_song_map.get(display_name)

        settings = None

        if info is not None:
            try:
                project = json.loads(
                    info["timeline"].read_text(
                        encoding="utf-8-sig"
                    )
                )
                settings = project.get(
                    "motion_settings"
                )
            except Exception:
                settings = None

        if not isinstance(settings, dict):
            try:
                settings = json.loads(
                    DANCE_MOTION_SETTINGS_FILE.read_text(
                        encoding="utf-8-sig"
                    )
                )
            except Exception:
                settings = None

        if not isinstance(settings, dict):
            settings = self._motion_presets()[
                "NORMAL"
            ]
            settings = {
                "preset": "NORMAL",
                **settings,
            }

        self.motion_preset_name = str(
            settings.get(
                "preset",
                "CUSTOM",
            )
        )

        defaults = self._motion_presets()[
            "NORMAL"
        ]

        for key, default in defaults.items():
            try:
                value = float(
                    settings.get(key, default)
                )
            except (TypeError, ValueError):
                value = default

            self.motion_setting_vars[key].set(
                value
            )

        total = float(
            self.motion_setting_vars[
                "total_intensity"
            ].get()
        )
        self.dance_intensity.set(total)
        self.dance_intensity_label.configure(
            text=f"{int(total * 100)}%"
        )

        self._write_motion_settings_file()

    def _save_motion_settings_to_song(self):
        display_name = self.dance_song.get()
        info = self.dance_song_map.get(display_name)

        if info is None:
            messagebox.showwarning(
                "No song selected",
                "请先选择一首音乐。",
            )
            return

        try:
            project = json.loads(
                info["timeline"].read_text(
                    encoding="utf-8-sig"
                )
            )
            project["motion_settings"] = (
                self._current_motion_settings()
            )
            info["timeline"].write_text(
                json.dumps(
                    project,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror(
                "Save failed",
                f"保存参数失败：\n{exc}",
            )
            return

        self._write_motion_settings_file()

        self._log(
            "MOTION",
            f"动作参数已保存到 {display_name}。",
        )
        messagebox.showinfo(
            "Saved",
            "当前舞蹈参数已保存到歌曲工程。",
        )

    def _update_dance_intensity_label(self, value):
        numeric = float(value)
        self.dance_intensity_label.configure(
            text=f"{int(numeric * 100)}%"
        )

        if hasattr(self, "motion_setting_vars"):
            self.motion_setting_vars[
                "total_intensity"
            ].set(numeric)
            self.motion_preset_name = "CUSTOM"
            self._refresh_motion_setting_labels()
            self._write_motion_settings_file()

    def _on_volume_slider(self, value):
        volume = int(round(float(value)))
        self._pending_speaker_volume = volume

        self.speaker_volume_label.configure(
            text=f"{volume}%"
        )

        self._write_dance_volume_file(volume)

        dance_running = (
            self.process is not None
            and self.process.poll() is None
            and self.process_mode is not None
            and self.process_mode.key == "dance"
        )

        if dance_running:
            return

        if self._volume_after_id is not None:
            try:
                self.after_cancel(self._volume_after_id)
            except Exception:
                pass

        self._volume_after_id = self.after(
            250,
            lambda v=volume: self._set_speaker_volume(v),
        )

    def _write_dance_volume_file(self, volume):
        RUNTIME_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = DANCE_VOLUME_FILE.with_suffix(
            ".tmp"
        )

        # RCC slider 0-100 maps to software gain 0.0-2.2.
        # Values above 1.0 are protected by a soft limiter in the
        # dance audio streamer.
        software_gain = (
            float(volume) / 100.0
        ) * 2.2

        payload = {
            "volume": max(
                0.0,
                min(2.2, software_gain),
            ),
            "slider_percent": int(volume),
            "updated_at": time.time(),
        }

        try:
            temporary.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            os.replace(
                temporary,
                DANCE_VOLUME_FILE,
            )
        except Exception as exc:
            self._queue_log(
                f"[VOLUME] Failed to write live volume: {exc!r}\n"
            )

    def _load_speaker_volume(self):
        def worker():
            try:
                with urllib.request.urlopen(
                    f"http://{_get_robot_host()}:8000/api/volume/current",
                    timeout=5,
                ) as response:
                    payload = json.loads(
                        response.read().decode("utf-8")
                    )

                value = payload.get("volume")

                if value is None:
                    value = payload.get("current_volume")

                if value is None:
                    return

                value = max(0, min(100, int(round(float(value)))))

                self.after(
                    0,
                    lambda: self._apply_loaded_volume(value),
                )

            except Exception as exc:
                self._queue_log(
                    f"[VOLUME] Unable to read current volume: {exc!r}\n"
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _apply_loaded_volume(self, value):
        self._pending_speaker_volume = value
        self.speaker_volume.set(value)
        self.speaker_volume_label.configure(
            text=f"{value}%"
        )
        self._write_dance_volume_file(value)

    def _set_speaker_volume_before_dance(self, volume):
        payload = json.dumps(
            {"volume": int(volume)}
        ).encode("utf-8")

        request = urllib.request.Request(
            f"http://{_get_robot_host()}:8000/api/volume/set",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=6,
        ) as response:
            response.read()

    def _set_speaker_volume(self, volume):
        self._volume_after_id = None

        def worker():
            payload = json.dumps(
                {"volume": int(volume)}
            ).encode("utf-8")

            request = urllib.request.Request(
                f"http://{_get_robot_host()}:8000/api/volume/set",
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            try:
                with urllib.request.urlopen(
                    request,
                    timeout=6,
                ) as response:
                    response.read()

                self._queue_log(
                    f"[VOLUME] Speaker volume set to {volume}%.\n"
                )

            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(
                    "utf-8",
                    errors="replace",
                )
                self._queue_log(
                    "[VOLUME] Volume API rejected the request: "
                    f"HTTP {exc.code} {detail}\n"
                )

            except Exception as exc:
                self._queue_log(
                    f"[VOLUME] Failed to set volume: {exc!r}\n"
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _set_status(self, key, text, color):
        self.status_labels[key].configure(text=text, text_color=color)

    def _api_request(
        self,
        path,
        method="GET",
        payload=None,
        timeout=5,
    ):
        """Call the Reachy Mini daemon and return decoded JSON when available."""
        url = f"http://{_get_robot_host()}:8000{path}"

        data = None
        headers = {
            "Accept": "application/json",
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif method.upper() in {"POST", "PUT", "PATCH"}:
            # Explicit empty body prevents urllib from silently turning
            # some POST requests into GET requests.
            data = b""

        request = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers=headers,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                raw = response.read()
                if not raw:
                    return {}

                content_type = response.headers.get(
                    "Content-Type",
                    "",
                ).lower()

                decoded = raw.decode(
                    "utf-8",
                    errors="replace",
                )

                if (
                    "application/json" in content_type
                    or decoded.lstrip().startswith(("{", "["))
                ):
                    return json.loads(decoded)

                return {
                    "text": decoded,
                    "status": response.status,
                }

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )
            raise RuntimeError(
                f"HTTP {exc.code} {path}: {detail}"
            ) from exc

        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"无法连接机器人接口 {path}: {exc.reason}"
            ) from exc

    @staticmethod
    def _flatten_api_values(value):
        """Yield scalar values from an arbitrarily nested API response."""
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key).lower()
                yield from RCCApp._flatten_api_values(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from RCCApp._flatten_api_values(item)
        elif value is not None:
            yield value

    def _parse_motor_state(self, payload):
        """Return True, False, or None from different daemon response shapes."""
        if isinstance(payload, dict):
            direct_keys = (
                "enabled",
                "motors_enabled",
                "motor_enabled",
                "awake",
                "is_awake",
                "powered",
            )

            for key in direct_keys:
                if key in payload:
                    value = payload[key]
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, (int, float)):
                        return bool(value)
                    if isinstance(value, str):
                        normalized = value.strip().lower()
                        if normalized in {
                            "true",
                            "1",
                            "enabled",
                            "awake",
                            "on",
                            "running",
                            "active",
                        }:
                            return True
                        if normalized in {
                            "false",
                            "0",
                            "disabled",
                            "sleep",
                            "sleeping",
                            "off",
                            "stopped",
                            "inactive",
                        }:
                            return False

        tokens = {
            str(value).strip().lower()
            for value in self._flatten_api_values(payload)
        }

        if tokens & {
            "enabled",
            "awake",
            "on",
            "running",
            "active",
            "ready",
        }:
            return True

        if tokens & {
            "disabled",
            "sleep",
            "sleeping",
            "off",
            "stopped",
            "inactive",
        }:
            return False

        return None

    def _parse_program_state(self, payload):
        """Return a compact program status from the daemon response."""
        if self.process is not None and self.process.poll() is None:
            if self.process_mode is not None:
                return self.process_mode.title, self.process_mode.accent
            return "RUNNING", self.GREEN

        if payload in (None, {}, [], ""):
            return "STOPPED", self.MUTED

        if isinstance(payload, dict):
            for key in (
                "name",
                "app_name",
                "current_app",
                "app",
                "status",
                "state",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    normalized = value.strip()
                    lowered = normalized.lower()

                    if lowered in {
                        "none",
                        "null",
                        "idle",
                        "stopped",
                        "not_running",
                        "no_app",
                    }:
                        return "STOPPED", self.MUTED

                    return normalized[:18].upper(), self.GREEN

            for key in (
                "running",
                "is_running",
                "active",
            ):
                value = payload.get(key)
                if isinstance(value, bool):
                    return (
                        ("RUNNING", self.GREEN)
                        if value
                        else ("STOPPED", self.MUTED)
                    )

        tokens = [
            str(value).strip()
            for value in self._flatten_api_values(payload)
            if str(value).strip()
        ]

        lowered_tokens = {
            token.lower()
            for token in tokens
        }

        if lowered_tokens & {
            "none",
            "null",
            "idle",
            "stopped",
            "not_running",
            "no_app",
        }:
            return "STOPPED", self.MUTED

        if tokens:
            return tokens[-1][:18].upper(), self.GREEN

        return "STOPPED", self.MUTED



    def _open_bluetooth_recovery(self):
        win = ctk.CTkToplevel(self)
        win.title("Reachy Mini Bluetooth Recovery")
        win.geometry("560x700")
        win.resizable(False, False)
        try:
            win.transient(self)
        except Exception:
            pass

        ctk.CTkLabel(
            win,
            text="BLUETOOTH NETWORK RECOVERY",
            font=ctk.CTkFont("Consolas", 17, "bold"),
            text_color=self.CYAN,
        ).pack(anchor="w", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            win,
            text="Use BLE to authenticate, read network status, or start robot hotspot.",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#8FA4BC",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 14))

        status = ctk.CTkLabel(
            win,
            text="BLE STATUS   IDLE",
            font=ctk.CTkFont("Consolas", 11, "bold"),
            text_color=self.AMBER,
        )
        status.pack(anchor="w", padx=20, pady=(0, 8))

        result_box = ctk.CTkTextbox(
            win,
            height=170,
            corner_radius=10,
            font=ctk.CTkFont("Consolas", 10),
        )
        result_box.pack(fill="x", padx=20, pady=(0, 12))
        result_box.insert("end", "Ready.\n")
        result_box.configure(state="disabled")

        pin_row = ctk.CTkFrame(win, fg_color="transparent")
        pin_row.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            pin_row,
            text="PIN (last 5 digits)",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#A7B3C7",
        ).pack(side="left")

        pin_entry = ctk.CTkEntry(
            pin_row,
            width=150,
            show="*",
            placeholder_text="12345",
        )
        pin_entry.pack(side="right")

        def append_line(line):
            try:
                result_box.configure(state="normal")
                result_box.insert("end", line + "\n")
                result_box.see("end")
                result_box.configure(state="disabled")
            except Exception:
                pass

        def set_status(text_value, color):
            try:
                status.configure(
                    text=f"BLE STATUS   {text_value}",
                    text_color=color,
                )
            except Exception:
                pass

        def run_action(action):
            pin = pin_entry.get().strip()

            if len(pin) != 5 or not pin.isdigit():
                append_line("ERROR: PIN must be exactly 5 digits.")
                set_status("BAD PIN", self.RED)
                return

            set_status("WORKING", self.AMBER)
            append_line(f"Starting BLE action: {action}")

            def worker():
                try:
                    result = asyncio.run(
                        self._ble_recovery_action(
                            pin=pin,
                            action=action,
                        )
                    )

                    def done():
                        set_status("ONLINE", self.GREEN)
                        append_line(result)
                        if action == "HOTSPOT":
                            append_line("Hotspot command sent. Robot network may disconnect now.")

                    self.after(0, done)

                except Exception as exc:
                    def fail():
                        set_status("FAILED", self.RED)
                        append_line(f"FAILED: {type(exc).__name__}: {exc}")
                    self.after(0, fail)

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="SCAN + STATUS",
            height=36,
            command=lambda: run_action("STATUS"),
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))

        ctk.CTkButton(
            btn_frame,
            text="START HOTSPOT",
            height=36,
            fg_color="#7A4D10",
            hover_color="#9A6418",
            command=lambda: run_action("HOTSPOT"),
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))


        wifi_frame = ctk.CTkFrame(
            win,
            corner_radius=10,
            fg_color="#171C24",
            border_width=1,
            border_color="#303A49",
        )
        wifi_frame.pack(fill="x", padx=20, pady=(8, 10))

        ctk.CTkLabel(
            wifi_frame,
            text="WIFI SETUP (PC connected to reachy-mini-ap)",
            font=ctk.CTkFont("Consolas", 11, "bold"),
            text_color=self.CYAN,
        ).pack(anchor="w", padx=12, pady=(10, 8))

        scan_row = ctk.CTkFrame(
            wifi_frame,
            fg_color="transparent",
        )
        scan_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            scan_row,
            text="TARGET WIFI",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#A7B3C7",
        ).pack(side="left")

        wifi_ssid_combo = ctk.CTkComboBox(
            scan_row,
            width=250,
            values=["Click SCAN WIFI"],
        )
        wifi_ssid_combo.pack(side="left", padx=(12, 8))

        scan_wifi_button = ctk.CTkButton(
            scan_row,
            text="SCAN WIFI",
            width=110,
            height=30,
        )
        scan_wifi_button.pack(side="right")

        password_row = ctk.CTkFrame(
            wifi_frame,
            fg_color="transparent",
        )
        password_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            password_row,
            text="PASSWORD",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#A7B3C7",
        ).pack(side="left")

        wifi_password_entry = ctk.CTkEntry(
            password_row,
            width=290,
            show="*",
            placeholder_text="Wi-Fi password",
        )
        wifi_password_entry.pack(side="right")

        wifi_result_label = ctk.CTkLabel(
            wifi_frame,
            text="STATUS: READY",
            font=ctk.CTkFont("Consolas", 9, "bold"),
            text_color=self.AMBER,
        )
        wifi_result_label.pack(
            anchor="w",
            padx=12,
            pady=(0, 7),
        )

        wifi_button = ctk.CTkButton(
            wifi_frame,
            text="CONNECT ROBOT TO WIFI",
            height=36,
            fg_color="#1D6D4E",
            hover_color="#278663",
        )
        wifi_button.pack(
            fill="x",
            padx=12,
            pady=(2, 10),
        )

        def scan_robot_wifi():
            scan_wifi_button.configure(
                state="disabled",
                text="SCANNING...",
            )
            wifi_result_label.configure(
                text="STATUS: SCANNING WIFI",
                text_color=self.AMBER,
            )

            def worker():
                try:
                    networks = self._scan_robot_wifi_from_hotspot()

                    def done():
                        if networks:
                            wifi_ssid_combo.configure(
                                values=networks
                            )
                            wifi_ssid_combo.set(
                                networks[0]
                            )
                            wifi_result_label.configure(
                                text=f"STATUS: FOUND {len(networks)} NETWORKS",
                                text_color=self.GREEN,
                            )
                            append_line(
                                "Visible Wi-Fi: " + ", ".join(networks)
                            )
                        else:
                            wifi_ssid_combo.configure(
                                values=["No networks found"]
                            )
                            wifi_ssid_combo.set(
                                "No networks found"
                            )
                            wifi_result_label.configure(
                                text="STATUS: NO WIFI FOUND",
                                text_color=self.RED,
                            )

                        scan_wifi_button.configure(
                            state="normal",
                            text="SCAN WIFI",
                        )

                    self.after(0, done)

                except Exception as exc:
                    def fail():
                        wifi_result_label.configure(
                            text="STATUS: SCAN FAILED",
                            text_color=self.RED,
                        )
                        append_line(
                            f"Wi-Fi scan failed: {type(exc).__name__}: {exc}"
                        )
                        scan_wifi_button.configure(
                            state="normal",
                            text="SCAN WIFI",
                        )

                    self.after(0, fail)

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        def connect_robot_to_wifi():
            target_ssid = wifi_ssid_combo.get().strip()
            target_password = wifi_password_entry.get()
            pin = pin_entry.get().strip()

            if (
                not target_ssid
                or target_ssid in {
                    "Click SCAN WIFI",
                    "No networks found",
                }
            ):
                append_line(
                    "ERROR: Scan and select a target Wi-Fi first."
                )
                return

            if len(pin) != 5 or not pin.isdigit():
                append_line(
                    "ERROR: BLE PIN must be exactly 5 digits."
                )
                return

            wifi_button.configure(
                state="disabled",
                text="CONNECTING + VERIFYING...",
            )
            scan_wifi_button.configure(
                state="disabled",
            )
            wifi_result_label.configure(
                text="STATUS: CONNECTING...",
                text_color=self.AMBER,
            )
            append_line(
                f"Connecting robot to Wi-Fi: {target_ssid}"
            )

            def worker():
                try:
                    result = self._connect_robot_wifi_verified(
                        target_ssid,
                        target_password,
                        pin,
                    )

                    def done():
                        wifi_password_entry.delete(0, "end")

                        host = result.get("robot_host")
                        network = result.get("network", "")

                        if host:
                            wifi_result_label.configure(
                                text=f"STATUS: CONNECTED / {host}",
                                text_color=self.GREEN,
                            )
                            append_line(
                                f"SUCCESS: robot connected to {target_ssid}; "
                                f"RCC rediscovered robot at {host}."
                            )
                            self._refresh_robot_connection()
                        else:
                            wifi_result_label.configure(
                                text="STATUS: ROBOT CONNECTED - SWITCH PC WIFI",
                                text_color=self.GREEN,
                            )
                            append_line(
                                f"SUCCESS: robot left hotspot and reports {network}."
                            )
                            append_line(
                                f"Now connect this PC to {target_ssid}, "
                                "then click REDISCOVER ROBOT."
                            )

                        wifi_button.configure(
                            state="normal",
                            text="CONNECT ROBOT TO WIFI",
                        )
                        scan_wifi_button.configure(
                            state="normal",
                        )

                    self.after(0, done)

                except Exception as exc:
                    def fail():
                        wifi_password_entry.delete(0, "end")
                        wifi_result_label.configure(
                            text="STATUS: CONNECTION FAILED",
                            text_color=self.RED,
                        )
                        append_line(
                            f"FAILED: {type(exc).__name__}: {exc}"
                        )
                        wifi_button.configure(
                            state="normal",
                            text="CONNECT ROBOT TO WIFI",
                        )
                        scan_wifi_button.configure(
                            state="normal",
                        )

                    self.after(0, fail)

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        scan_wifi_button.configure(
            command=scan_robot_wifi
        )
        wifi_button.configure(
            command=connect_robot_to_wifi
        )

        ctk.CTkLabel(
            win,
            text=(
                "START HOTSPOT changes robot network state. "
                "Use it only when RCC cannot reach the robot on Wi-Fi."
            ),
            font=ctk.CTkFont("Segoe UI", 9),
            text_color="#9E7E56",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(4, 0))

    async def _ble_find_reachy(self):
        devices = await BleakScanner.discover(
            timeout=12.0,
            return_adv=True,
        )

        candidates = []

        for _, pair in devices.items():
            device, adv = pair
            name = (device.name or adv.local_name or "").lower().strip()
            services = [x.lower() for x in (adv.service_uuids or [])]

            if (
                "reachymini" in name
                or "reachy mini" in name
                or BLE_SERVICE_ADV.lower() in services
                or str(device.address).upper() == BLE_LAST_KNOWN_ADDRESS.upper()
            ):
                candidates.append((device, adv))

        if not candidates:
            device = await BleakScanner.find_device_by_address(
                BLE_LAST_KNOWN_ADDRESS,
                timeout=8.0,
            )
            if device is None:
                raise RuntimeError("ReachyMini BLE not found.")
            return device

        candidates.sort(
            key=lambda item: item[1].rssi or -999,
            reverse=True,
        )
        return candidates[0][0]

    async def _ble_read_text(self, client, uuid):
        raw = await client.read_gatt_char(uuid)
        return raw.decode("utf-8", errors="replace").strip("\x00\r\n ")

    async def _ble_write_text(self, client, text_value):
        await client.write_gatt_char(
            BLE_CHAR_WRITE,
            text_value.encode("utf-8"),
            response=True,
        )
        await asyncio.sleep(0.8)

    async def _ble_recovery_action(self, pin, action):
        device = await self._ble_find_reachy()

        async with BleakClient(
            device,
            timeout=30.0,
        ) as client:
            if not client.is_connected:
                raise RuntimeError("BLE connection failed.")

            await self._ble_write_text(
                client,
                f"PIN_{pin}",
            )

            await self._ble_write_text(
                client,
                "STATUS",
            )

            network = await self._ble_read_text(
                client,
                BLE_CHAR_NET,
            )
            state = await self._ble_read_text(
                client,
                BLE_CHAR_STATE,
            )
            commands = await self._ble_read_text(
                client,
                BLE_CHAR_COMMANDS,
            )
            hwid = await self._ble_read_text(
                client,
                BLE_CHAR_HWID,
            )

            if action == "STATUS":
                return (
                    f"NETWORK: {network}\n"
                    f"STATE: {state}\n"
                    f"COMMANDS: {commands}\n"
                    f"HARDWARE_ID: {hwid}"
                )

            if action == "HOTSPOT":
                if "HOTSPOT" not in commands:
                    raise RuntimeError(
                        "Robot firmware does not report HOTSPOT support."
                    )

                await self._ble_write_text(
                    client,
                    "CMD_HOTSPOT",
                )

                return (
                    f"NETWORK(before): {network}\n"
                    f"STATE(before): {state}\n"
                    "CMD_HOTSPOT sent successfully."
                )

            raise RuntimeError(
                f"Unknown BLE action: {action}"
            )


    def _hotspot_http_json(self, path, method="GET", timeout=10):
        """Direct no-proxy HTTP request to the Reachy Mini hotspot API."""
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )
        req = urllib.request.Request(
            "http://10.42.0.1:8000" + path,
            method=method,
            headers={
                "Accept": "application/json",
                "Connection": "close",
                "User-Agent": "RCC-Hotspot-Direct/2.0",
            },
        )
        with opener.open(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None
            try:
                return json.loads(raw)
            except Exception:
                return raw

    def _scan_robot_wifi_from_hotspot(self):
        """Return visible Wi-Fi SSIDs reported by Reachy Mini itself."""
        try:
            status = self._hotspot_http_json(
                "/wifi/status",
                method="GET",
                timeout=6,
            )
        except Exception as exc:
            raise RuntimeError(
                "Reachy hotspot API is not reachable. "
                "Connect this PC to reachy-mini-ap first."
            ) from exc

        if not isinstance(status, dict) or status.get("mode") != "hotspot":
            raise RuntimeError(
                "Robot is not currently in hotspot mode."
            )

        networks = self._hotspot_http_json(
            "/wifi/scan_and_list",
            method="POST",
            timeout=15,
        )

        if not isinstance(networks, list):
            raise RuntimeError(
                f"Unexpected Wi-Fi scan response: {networks!r}"
            )

        cleaned = []
        seen = set()

        for item in networks:
            ssid = str(item or "").strip()
            if not ssid:
                continue
            if ssid.lower() == "reachy-mini-ap":
                continue
            if ssid in seen:
                continue
            seen.add(ssid)
            cleaned.append(ssid)

        return cleaned

    async def _ble_verify_robot_network(self, pin, attempts=12):
        """Verify over BLE that the robot has left hotspot mode and obtained WLAN."""
        last_network = ""
        last_state = ""

        for _ in range(attempts):
            try:
                device = await self._ble_find_reachy()

                async with BleakClient(
                    device,
                    timeout=20.0,
                ) as client:
                    if not client.is_connected:
                        raise RuntimeError("BLE connection failed.")

                    await self._ble_write_text(
                        client,
                        f"PIN_{pin}",
                    )
                    await self._ble_write_text(
                        client,
                        "STATUS",
                    )

                    last_network = await self._ble_read_text(
                        client,
                        BLE_CHAR_NET,
                    )
                    last_state = await self._ble_read_text(
                        client,
                        BLE_CHAR_STATE,
                    )

                    upper = last_network.upper()

                    if (
                        "CONNECTED" in upper
                        and "HOTSPOT" not in upper
                        and "0.0.0.0" not in upper
                    ):
                        return True, last_network, last_state

            except Exception:
                pass

            await asyncio.sleep(2.0)

        return False, last_network, last_state

    def _connect_robot_wifi_verified(self, ssid, password, pin):
        """
        Connect Reachy Mini to Wi-Fi using hotspot API and verify via BLE.
        """
        if len(pin) != 5 or not pin.isdigit():
            raise RuntimeError("BLE PIN must be exactly 5 digits.")

        status = self._hotspot_http_json(
            "/wifi/status",
            method="GET",
            timeout=6,
        )

        if not isinstance(status, dict) or status.get("mode") != "hotspot":
            raise RuntimeError(
                "Reachy Mini is not in hotspot mode."
            )

        try:
            self._hotspot_http_json(
                "/wifi/reset_error",
                method="POST",
                timeout=5,
            )
        except Exception:
            pass

        query = urllib.parse.urlencode(
            {
                "ssid": ssid,
                "password": password,
            }
        )

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

        req = urllib.request.Request(
            "http://10.42.0.1:8000/wifi/connect?" + query,
            method="POST",
            headers={
                "Accept": "application/json",
                "Connection": "close",
                "User-Agent": "RCC-WiFi-Connect/2.0",
            },
        )

        submit_result = "request_sent"

        try:
            with opener.open(req, timeout=12) as response:
                body = response.read().decode(
                    "utf-8",
                    errors="replace",
                )
                submit_result = (
                    f"HTTP {response.status}"
                    + (f" {body[:200]}" if body.strip() else "")
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )
            raise RuntimeError(
                f"Wi-Fi API returned HTTP {exc.code}: {body[:300]}"
            ) from exc
        except Exception:
            submit_result = "hotspot_closed_during_switch"

        ok, network, state = asyncio.run(
            self._ble_verify_robot_network(
                pin=pin,
                attempts=15,
            )
        )

        if not ok:
            try:
                err = self._hotspot_http_json(
                    "/wifi/error",
                    method="GET",
                    timeout=5,
                )
            except Exception:
                err = None

            raise RuntimeError(
                "Robot did not confirm a normal WLAN connection over BLE. "
                f"submit={submit_result}; network={network or 'UNKNOWN'}; "
                f"state={state or 'UNKNOWN'}; wifi_error={err!r}"
            )

        discovered = None
        try:
            current_pc_wifi = self._get_current_wifi_name()
            if current_pc_wifi == ssid:
                discovered = _get_robot_host(
                    force_rediscover=True
                )
        except Exception:
            discovered = None

        return {
            "ssid": ssid,
            "network": network,
            "state": state,
            "robot_host": discovered,
        }

    def _get_current_wifi_name(self):
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                creationflags=flags,
            )
            if result.returncode != 0:
                return "UNKNOWN"

            for line in result.stdout.splitlines():
                stripped = line.strip()
                if "SSID" in stripped and "BSSID" not in stripped and ":" in stripped:
                    value = stripped.split(":", 1)[1].strip()
                    if value:
                        return value
        except Exception:
            pass

        return "UNKNOWN"

    def _refresh_network_panel(self):
        try:
            wifi_name = self._get_current_wifi_name()
            host = ROBOT_HOST or "UNKNOWN"

            if hasattr(self, "network_wifi_label"):
                self.network_wifi_label.configure(text=f"PC WIFI {wifi_name}")

            if hasattr(self, "network_host_label"):
                self.network_host_label.configure(text=f"ROBOT   {host}")

            if hasattr(self, "network_state_label"):
                state_text = "ONLINE" if host != "UNKNOWN" else "SEARCHING"
                state_color = self.GREEN if host != "UNKNOWN" else self.AMBER
                self.network_state_label.configure(
                    text=f"STATE   {state_text}",
                    text_color=state_color,
                )
        except Exception:
            pass

        try:
            self.after(5000, self._refresh_network_panel)
        except Exception:
            pass

    def _force_rediscover_robot(self):
        if getattr(self, "robot_busy", False):
            self._log("SYSTEM", "机器人正在执行操作，请稍后再重新发现。")
            return

        if hasattr(self, "rediscover_button"):
            self.rediscover_button.configure(state="disabled", text="SEARCHING...")

        if hasattr(self, "network_state_label"):
            self.network_state_label.configure(
                text="STATE   SEARCHING",
                text_color=self.AMBER,
            )

        self._log("SYSTEM", "正在重新扫描当前网络中的 Reachy Mini...")

        def worker():
            global ROBOT_HOST

            try:
                old_host = ROBOT_HOST
                ROBOT_HOST = None
                new_host = _get_robot_host(force_rediscover=True)

                self._api_request(
                    "/api/daemon/status",
                    timeout=5,
                )

                self._log(
                    "SYSTEM",
                    f"重新发现成功: {old_host or 'UNKNOWN'} -> {new_host}"
                )

                def on_success():
                    if hasattr(self, "network_host_label"):
                        self.network_host_label.configure(text=f"ROBOT   {new_host}")

                    if hasattr(self, "network_state_label"):
                        self.network_state_label.configure(
                            text="STATE   ONLINE",
                            text_color=self.GREEN,
                        )

                    if hasattr(self, "rediscover_button"):
                        self.rediscover_button.configure(
                            state="normal",
                            text="REDISCOVER ROBOT",
                        )

                    self._refresh_robot_connection()

                self.after(0, on_success)

            except Exception as exc:
                self._log("ERROR", f"重新发现 Reachy Mini 失败: {exc}")

                def on_failure():
                    if hasattr(self, "network_state_label"):
                        self.network_state_label.configure(
                            text="STATE   NOT FOUND",
                            text_color=self.RED,
                        )
                    if hasattr(self, "network_host_label"):
                        self.network_host_label.configure(text="ROBOT   UNKNOWN")
                    if hasattr(self, "rediscover_button"):
                        self.rediscover_button.configure(
                            state="normal",
                            text="REDISCOVER ROBOT",
                        )

                self.after(0, on_failure)

        threading.Thread(target=worker, daemon=True).start()

    def _rediscover_robot_host(self):
        global ROBOT_HOST
        try:
            old_host = ROBOT_HOST
            new_host = _get_robot_host(force_rediscover=True)
            if old_host != new_host:
                self._log(
                    "SYSTEM",
                    f"Reachy Mini 地址已更新: {old_host or 'UNKNOWN'} -> {new_host}"
                )
            return new_host
        except Exception as exc:
            self._log(
                "WARN",
                f"自动重新发现 Reachy Mini 失败: {exc}"
            )
            return None

    def _refresh_robot_connection(self):
        def worker():
            try:
                daemon_status = self._api_request(
                    "/api/daemon/status",
                    timeout=4,
                )

                try:
                    motor_status = self._api_request(
                        "/api/motors/status",
                        timeout=4,
                    )
                except Exception:
                    motor_status = None

                try:
                    program_status = self._api_request(
                        "/api/apps/current-app-status",
                        timeout=4,
                    )
                except Exception:
                    program_status = None

                motor_awake = self._parse_motor_state(
                    motor_status
                )
                program_text, program_color = (
                    self._parse_program_state(
                        program_status
                    )
                )

                self.after(
                    0,
                    lambda: self._show_connected(
                        motor_awake,
                        program_text,
                        program_color,
                    ),
                )

            except Exception:
                self.after(
                    0,
                    self._show_disconnected,
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

        self.after(
            5000,
            self._refresh_robot_connection,
        )

    def _show_connected(
        self,
        motor_awake=None,
        program_text=None,
        program_color=None,
    ):
        self.connection_chip.configure(
            text="●  ONLINE",
            text_color=self.GREEN,
            fg_color="#102A24",
        )
        self._set_status(
            "robot",
            "ONLINE",
            self.GREEN,
        )
        self._set_status(
            "media",
            "AVAILABLE",
            self.GREEN,
        )
        self.footer_labels["robot"].configure(
            text="ROBOT  ONLINE",
            text_color=self.GREEN,
        )

        if motor_awake is not None:
            self.robot_awake = bool(
                motor_awake
            )
            self._update_power_ui()
        else:
            self._set_status(
                "motors",
                "UNKNOWN",
                self.AMBER,
            )

        if (
            self.process is None
            or self.process.poll() is not None
        ):
            self._set_status(
                "program",
                program_text or "STOPPED",
                program_color or self.MUTED,
            )

    def _show_disconnected(self):
        self.connection_chip.configure(
            text="●  OFFLINE",
            text_color=self.RED,
            fg_color="#321822",
        )
        self._set_status(
            "robot",
            "OFFLINE",
            self.RED,
        )
        self._set_status(
            "motors",
            "UNKNOWN",
            self.AMBER,
        )
        self._set_status(
            "media",
            "UNKNOWN",
            self.AMBER,
        )

        if (
            self.process is None
            or self.process.poll() is not None
        ):
            self._set_status(
                "program",
                "UNKNOWN",
                self.AMBER,
            )

        self.footer_labels["robot"].configure(
            text="ROBOT  OFFLINE",
            text_color=self.RED,
        )

    def _toggle_power(self):
        if self.robot_busy:
            return

        self._run_robot_action(
            "sleep"
            if self.robot_awake
            else "wake"
        )


    def _run_robot_action(self, action):
        self.robot_busy = True

        self.power_button.configure(
            state="disabled"
        )

        def worker():
            try:
                if action == "sleep":
                    self._stop_mode(wait=True)

                    self._log(
                        "ROBOT",
                        "正在让 Reachy Mini 进入休眠状态..."
                    )

                    try:
                        self._api_request(
                            "/api/move/play/goto_sleep",
                            method="POST",
                            timeout=15,
                        )
                    except Exception as exc:
                        self._log(
                            "WARN",
                            f"休眠动作返回异常，将继续尝试关闭电机：{exc}"
                        )

                    time.sleep(2.0)

                    try:
                        self._api_request(
                            "/api/motors/set_mode/disabled",
                            method="POST",
                            timeout=10,
                        )
                    except Exception as exc:
                        self._log(
                            "WARN",
                            f"关闭电机时返回异常：{exc}"
                        )

                    expected = False

                else:
                    self._log(
                        "ROBOT",
                        "正在唤醒 Reachy Mini..."
                    )

                    try:
                        motor_payload = self._api_request(
                            "/api/motors/status",
                            timeout=4,
                        )
                        current_state = self._parse_motor_state(
                            motor_payload
                        )
                    except Exception:
                        current_state = None

                    if current_state is not True:
                        self._log(
                            "ROBOT",
                            "正在启用机器人电机..."
                        )

                        self._api_request(
                            "/api/motors/set_mode/enabled",
                            method="POST",
                            timeout=10,
                        )

                        motors_enabled = False

                        for _ in range(12):
                            time.sleep(0.35)

                            try:
                                motor_payload = self._api_request(
                                    "/api/motors/status",
                                    timeout=4,
                                )
                                state = self._parse_motor_state(
                                    motor_payload
                                )

                                if state is True:
                                    motors_enabled = True
                                    break
                            except Exception:
                                pass

                        if not motors_enabled:
                            self._log(
                                "WARN",
                                "电机启用请求已发送，但状态尚未确认。继续执行唤醒动作。"
                            )

                    time.sleep(0.4)

                    self._api_request(
                        "/api/move/play/wake_up",
                        method="POST",
                        timeout=15,
                    )

                    expected = True

                confirmed_state = None

                for _ in range(12):
                    time.sleep(0.35)

                    try:
                        motor_payload = self._api_request(
                            "/api/motors/status",
                            timeout=4,
                        )
                        confirmed_state = self._parse_motor_state(
                            motor_payload
                        )
                    except Exception:
                        confirmed_state = None

                    if confirmed_state is expected:
                        break

                if confirmed_state is None:
                    confirmed_state = expected

                self.robot_awake = bool(
                    confirmed_state
                )

                self.after(
                    0,
                    self._update_power_ui,
                )

                if self.robot_awake:
                    self._log(
                        "ROBOT",
                        "Reachy Mini 已成功唤醒，电机已启用。"
                    )
                else:
                    self._log(
                        "ROBOT",
                        "Reachy Mini 已进入休眠状态，电机已关闭。"
                    )

                self.after(
                    300,
                    self._refresh_robot_connection,
                )

            except Exception as exc:
                self._log(
                    "ERROR",
                    f"机器人电源控制失败：{exc}",
                )

                self.after(
                    0,
                    self._refresh_robot_connection,
                )

            finally:
                self.robot_busy = False

                self.after(
                    0,
                    lambda: self.power_button.configure(
                        state="normal"
                    ),
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _update_power_ui(self):
        if self.robot_awake:
            self.power_button.configure(
                text="SLEEP ROBOT",
                fg_color="#334155",
                hover_color="#475569",
            )
            self._set_status(
                "motors",
                "ENABLED",
                self.GREEN,
            )
        else:
            self.power_button.configure(
                text="WAKE ROBOT",
                fg_color="#0E7490",
                hover_color="#0891B2",
            )
            self._set_status(
                "motors",
                "SLEEP",
                self.MUTED,
            )

    def _network_preflight(self):
        """
        Validate Reachy Mini network/daemon/media state before launching a mode.

        Returns:
            True  - safe to launch
            False - network/daemon/media validation failed
        """
        global ROBOT_HOST

        self._log("NETWORK", "Running Network Preflight...")

        def resolve_ipv4(host):
            try:
                infos = socket.getaddrinfo(
                    host,
                    8000,
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                )
                for info in infos:
                    ip = info[4][0]
                    if ip:
                        return ip
            except Exception:
                pass

            # host may already be an IPv4 literal
            try:
                socket.inet_aton(host)
                return host
            except Exception:
                return None

        def validate_once(force_rediscover=True):
            global ROBOT_HOST

            if force_rediscover:
                ROBOT_HOST = None

            host = _get_robot_host(
                force_rediscover=force_rediscover
            )

            daemon = self._api_request(
                "/api/daemon/status",
                timeout=5,
            )

            if not isinstance(daemon, dict):
                raise RuntimeError(
                    "Invalid daemon/status response"
                )

            robot_name = str(
                daemon.get("robot_name", "")
            ).lower()

            if "reachy" not in robot_name:
                raise RuntimeError(
                    f"Target device is not Reachy Mini: {robot_name!r}"
                )

            state = str(
                daemon.get("state", "")
            ).lower()

            if state != "running":
                raise RuntimeError(
                    f"Reachy daemon is not running: {state or 'UNKNOWN'}"
                )

            wlan_ip = str(
                daemon.get("wlan_ip") or ""
            ).strip()

            resolved_ip = resolve_ipv4(host)

            if not wlan_ip:
                raise RuntimeError(
                    "Daemon did not report wlan_ip"
                )

            self._log(
                "NETWORK",
                f"Reachy host={host}, resolved={resolved_ip or 'UNKNOWN'}, "
                f"daemon wlan_ip={wlan_ip}"
            )

            # 10.42.0.1 is valid only when RCC is actually using
            # the robot provisioning hotspot.
            pc_wifi = self._get_current_wifi_name()

            stale = False

            if wlan_ip == "10.42.0.1":
                if pc_wifi != "reachy-mini-ap":
                    stale = True

            elif resolved_ip and resolved_ip != wlan_ip:
                stale = True

            if stale:
                raise RuntimeError(
                    "STALE_WLAN_IP:"
                    f" host={resolved_ip or host}, "
                    f"daemon={wlan_ip}, "
                    f"pc_wifi={pc_wifi}"
                )

            media = self._api_request(
                "/api/media/status",
                timeout=5,
            )

            if not isinstance(media, dict):
                raise RuntimeError(
                    "Invalid media/status response"
                )

            if not bool(media.get("available")):
                raise RuntimeError(
                    "Reachy Media is unavailable"
                )

            if bool(media.get("no_media")):
                raise RuntimeError(
                    "Reachy daemon is running in no_media mode"
                )

            return {
                "host": host,
                "resolved_ip": resolved_ip,
                "wlan_ip": wlan_ip,
                "daemon": daemon,
                "media": media,
            }

        # --------------------------------------------------------
        # First validation
        # --------------------------------------------------------
        try:
            result = validate_once(
                force_rediscover=True
            )

            self._log(
                "NETWORK",
                "Network Preflight passed:"
                f" Reachy={result['wlan_ip']}, "
                "daemon=RUNNING, media=READY"
            )

            if hasattr(self, "network_state_label"):
                self.network_state_label.configure(
                    text="STATE   READY",
                    text_color=self.GREEN,
                )

            if hasattr(self, "network_host_label"):
                self.network_host_label.configure(
                    text=f"ROBOT   {result['host']}"
                )

            return True

        except Exception as first_exc:
            message = str(first_exc)

            # ----------------------------------------------------
            # Special recovery for stale daemon wlan_ip
            # ----------------------------------------------------
            if message.startswith("STALE_WLAN_IP:"):
                self._log(
                    "NETWORK",
                    "Stale daemon WLAN IP detected. Restarting daemon..."
                )

                try:
                    # Use currently reachable host for restart.
                    self._api_request(
                        "/api/daemon/restart",
                        method="POST",
                        timeout=5,
                    )
                except Exception as restart_exc:
                    # Connection may drop while daemon restarts.
                    self._log(
                        "NETWORK",
                        "Daemon connection dropped during restart; this may be expected."
                    )

                time.sleep(8)

                try:
                    ROBOT_HOST = None

                    result = validate_once(
                        force_rediscover=True
                    )

                    self._log(
                        "NETWORK",
                        "Daemon network state recovered:"
                        f" Reachy={result['wlan_ip']}"
                    )

                    if hasattr(self, "network_state_label"):
                        self.network_state_label.configure(
                            text="STATE   READY",
                            text_color=self.GREEN,
                        )

                    if hasattr(self, "network_host_label"):
                        self.network_host_label.configure(
                            text=f"ROBOT   {result['host']}"
                        )

                    return True

                except Exception as second_exc:
                    self._log(
                        "ERROR",
                        "Network Preflight recovery failed: "
                        f"{second_exc}"
                    )

                    if hasattr(self, "network_state_label"):
                        self.network_state_label.configure(
                            text="STATE   NETWORK ERROR",
                            text_color=self.RED,
                        )

                    return False

            # ----------------------------------------------------
            # Normal preflight failure
            # ----------------------------------------------------
            self._log(
                "ERROR",
                f"Network Preflight failed: {first_exc}"
            )

            if hasattr(self, "network_state_label"):
                self.network_state_label.configure(
                    text="STATE   NETWORK ERROR",
                    text_color=self.RED,
                )

            return False


    def _start_selected_mode(self):
        if self.process is not None and self.process.poll() is None:
            self._log("SYSTEM", "请先停止当前运行模式。")
            return

        mode = self.selected_mode
        if not self._module_available(mode.module):
            self._log("ERROR", f"找不到模块：{mode.module}")
            return

        if not self._network_preflight():
            self._log(
                "SYSTEM",
                "Network Preflight failed. Mode launch cancelled."
            )
            return

        if not self.robot_awake:
            self._log("SYSTEM", "请先点击 WAKE ROBOT。")
            return

        embedded = mode.key in {"vision", "full"}

        if mode.key == "dance":
            display_name = self.dance_song.get()
            project_info = self.dance_song_map.get(display_name)

            if project_info is None:
                self._log(
                    "ERROR",
                    "请先在 Music Library 中添加并选择音乐。",
                )
                return

            timeline_path = project_info["timeline"]
            music_path = project_info["audio"]

            if not timeline_path.exists():
                self._log(
                    "ERROR",
                    f"找不到舞蹈工程：{timeline_path.name}",
                )
                return

            if not music_path.exists():
                self._log(
                    "ERROR",
                    f"找不到音乐：{music_path.name}",
                )
                return

            requested_volume = int(
                round(self.speaker_volume.get())
            )
            self._write_dance_volume_file(
                requested_volume
            )

            try:
                self._set_speaker_volume_before_dance(
                    100
                )
                self._log(
                    "VOLUME",
                    "机器人硬件音量基准已设为 100%，"
                    "播放中由软件增益实时控制。",
                )
                time.sleep(0.30)
            except Exception as exc:
                self._log(
                    "VOLUME",
                    f"设置硬件音量基准失败：{exc!r}",
                )

            command = [
                sys.executable,
                "-u",
                "-m",
                mode.module,
                "--timeline",
                str(timeline_path),
                "--intensity",
                f"{self.dance_intensity.get():.2f}",
                "--volume-file",
                str(DANCE_VOLUME_FILE),
                "--settings-file",
                str(DANCE_MOTION_SETTINGS_FILE),
            ]

        elif embedded:
            try:
                PREVIEW_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            command = [
                sys.executable, "-u", "-m",
                "launcher.run_mode", mode.module,
                "--embedded-vision",
            ]
            self.preview_status.configure(
                text="INITIALIZING", text_color=self.AMBER
            )
        elif mode.key == "v35":
            command = [
                sys.executable,
                "-u",
                "-m",
                "launcher.run_mode",
                mode.module,
            ]
        elif mode.key != "dance":
            command = [sys.executable, "-u", "-m", mode.module]

        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt" else 0
        )
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["RCC_PROJECT_ROOT"] = str(PROJECT_ROOT)

        self.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
            env=child_env,
        )
        self.process_mode = mode
        self._set_status("program", mode.title, mode.accent)
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        if mode.key == "dance":
            self.footer_labels["tracking"].configure(
                text="DANCE  RUNNING",
                text_color="#F472B6",
            )
        else:
            self.footer_labels["tracking"].configure(
                text="TRACKING  STARTING" if embedded else "TRACKING  OFF",
                text_color=self.AMBER if embedded else self.MUTED,
            )
        self._log("LAUNCH", f"{mode.title} · {mode.subtitle}")

        threading.Thread(
            target=self._read_process_output,
            args=(self.process,),
            daemon=True,
        ).start()

    def _read_process_output(self, process):
        if process.stdout is None:
            return
        for line in process.stdout:
            self._queue_log(line)

    def _stop_mode(self, wait=False):
        process = self.process
        if process is None or process.poll() is not None:
            return

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            else:
                process.send_signal(signal.SIGINT)

            if wait:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

        self.process = None
        self.process_mode = None
        self.after(0, self._show_program_stopped)

    def _show_program_stopped(self):
        self._set_status("program", "STOPPED", self.MUTED)

        latest_volume = int(
            round(self.speaker_volume.get())
        )
        self.speaker_volume_label.configure(
            text=f"{latest_volume}%"
        )
        self._write_dance_volume_file(
            latest_volume
        )
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.preview_status.configure(
            text="WAITING", text_color=self.MUTED
        )
        self.footer_labels["tracking"].configure(
            text="TRACKING  IDLE", text_color=self.MUTED
        )

    def _poll_process(self):
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self.process_mode = None
            self._show_program_stopped()
            self._log("EXIT", f"程序已退出，代码 {code}")
        self.after(350, self._poll_process)

    def _refresh_preview(self):
        try:
            if PREVIEW_FILE.exists():
                mtime = PREVIEW_FILE.stat().st_mtime
                if mtime > self._preview_mtime:
                    self._preview_mtime = mtime
                    with PREVIEW_FILE.open("rb") as stream:
                        image = Image.open(stream).convert("RGB")
                        image.load()

                    original_size = image.size
                    image.thumbnail((640, 360), Image.Resampling.LANCZOS)

                    self._preview_image = ctk.CTkImage(
                        light_image=image,
                        dark_image=image,
                        size=image.size,
                    )
                    self.preview_label.configure(
                        image=self._preview_image,
                        text="",
                    )
                    self.preview_status.configure(
                        text="●  LIVE", text_color=self.GREEN
                    )
                    self.footer_labels["camera"].configure(
                        text=f"CAMERA  {original_size[0]}×{original_size[1]}",
                        text_color=self.GREEN,
                    )
                    self.footer_labels["tracking"].configure(
                        text="TRACKING  ACTIVE", text_color=self.GREEN
                    )
                    self.footer_labels["fps"].configure(
                        text="FPS  ~12", text_color=self.CYAN
                    )
        except Exception:
            pass

        self.after(80, self._refresh_preview)

    def _log(self, tag, text):
        now = time.strftime("%H:%M:%S")
        self._queue_log(f"[{now}] [{tag}] {text}\n")

    def _queue_log(self, text):
        self.log_queue.put(text)

    def _flush_logs(self):
        lines = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break

        if lines:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "".join(lines))
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.after(100, self._flush_logs)

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _close_app(self):
        if self.process is not None and self.process.poll() is None:
            self._stop_mode(wait=True)
        self.destroy()


def main():
    RCCApp().mainloop()


if __name__ == "__main__":
    main()
