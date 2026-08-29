from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import librosa
import numpy as np
from reachy_mini.utils import create_head_pose


@dataclass(frozen=True)
class DanceAnalysis:
    audio_path: Path
    duration: float
    bpm: float
    beat_times: np.ndarray
    beat_strengths: np.ndarray


@dataclass
class DanceConfig:
    style: str = "emotion"
    intensity: float = 0.72
    movement_every_n_beats: int = 2

    max_head_yaw_deg: float = 9.0
    max_head_roll_deg: float = 6.0
    max_head_pitch_deg: float = 4.5
    max_body_yaw_deg: float = 8.0
    max_antenna_deg: float = 24.0

    minimum_move_duration: float = 0.30
    maximum_move_duration: float = 0.72
    return_duration: float = 1.2


class DanceAnalyzer:
    """
    Offline beat and energy analysis.

    Analysis happens before the robot starts moving, so the dance loop
    does not compete with motor control or audio playback for CPU time.
    """

    def __init__(
        self,
        analysis_sample_rate: int = 11025,
        hop_length: int = 512,
    ) -> None:
        self.analysis_sample_rate = analysis_sample_rate
        self.hop_length = hop_length

    def analyze(
        self,
        audio_path: str | Path,
    ) -> DanceAnalysis:
        path = Path(audio_path).resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"Music file not found: {path}"
            )

        print("[Dance] Analyzing music...")
        print(f"[Dance] File: {path.name}")

        audio, sample_rate = librosa.load(
            path,
            sr=self.analysis_sample_rate,
            mono=True,
        )

        duration = librosa.get_duration(
            y=audio,
            sr=sample_rate,
        )

        onset_envelope = librosa.onset.onset_strength(
            y=audio,
            sr=sample_rate,
            hop_length=self.hop_length,
        )

        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=self.hop_length,
        )

        bpm = float(np.atleast_1d(tempo)[0])

        beat_times = librosa.frames_to_time(
            beat_frames,
            sr=sample_rate,
            hop_length=self.hop_length,
        )

        if len(beat_times) < 4:
            beat_interval = 60.0 / max(bpm, 90.0)
            beat_times = np.arange(
                0.0,
                duration,
                beat_interval,
                dtype=np.float64,
            )

        beat_strengths = self._sample_strengths(
            onset_envelope,
            beat_frames,
        )

        print(f"[Dance] Duration: {duration:.2f} s")
        print(f"[Dance] Estimated BPM: {bpm:.1f}")
        print(f"[Dance] Detected beats: {len(beat_times)}")

        return DanceAnalysis(
            audio_path=path,
            duration=duration,
            bpm=bpm,
            beat_times=beat_times,
            beat_strengths=beat_strengths,
        )

    @staticmethod
    def _sample_strengths(
        onset_envelope: np.ndarray,
        beat_frames: np.ndarray,
    ) -> np.ndarray:
        if len(beat_frames) == 0:
            return np.ones(1, dtype=np.float64)

        indices = np.clip(
            beat_frames,
            0,
            max(0, len(onset_envelope) - 1),
        )

        strengths = onset_envelope[indices].astype(
            np.float64
        )

        low = float(np.percentile(strengths, 10))
        high = float(np.percentile(strengths, 90))

        if high <= low:
            return np.full_like(strengths, 0.5)

        normalized = (strengths - low) / (high - low)

        return np.clip(
            normalized,
            0.0,
            1.0,
        )


class ReachyDanceController:
    """
    Beat-synchronized Reachy Mini dance controller.

    The first version intentionally uses conservative motion limits.
    One movement is generated every two detected beats by default,
    which suits gentle pop music and reduces command pressure.
    """

    def __init__(
        self,
        mini,
        config: DanceConfig | None = None,
    ) -> None:
        self.mini = mini
        self.config = config or DanceConfig()

    def prepare(self) -> None:
        print("[Dance] Preparing robot...")

        self.mini.enable_motors()
        time.sleep(0.8)

        self.mini.wake_up()
        time.sleep(2.5)

        # Dance commands explicitly control body yaw.
        self.mini.set_automatic_body_yaw(False)

        self.neutral(
            duration=self.config.return_duration
        )

    def neutral(
        self,
        duration: float | None = None,
    ) -> None:
        self.mini.goto_target(
            head=create_head_pose(),
            antennas=np.deg2rad([0.0, 0.0]),
            body_yaw=0.0,
            duration=(
                duration
                if duration is not None
                else self.config.return_duration
            ),
            method="minjerk",
        )

    def play(
        self,
        analysis: DanceAnalysis,
    ) -> None:
        config = self.config
        beat_times = analysis.beat_times
        strengths = analysis.beat_strengths

        print("[Dance] Uploading and starting music...")
        self.mini.media.play_sound(
            str(analysis.audio_path)
        )

        playback_started = time.perf_counter()
        step_number = 0

        try:
            for beat_index in range(
                0,
                len(beat_times),
                config.movement_every_n_beats,
            ):
                scheduled_time = float(
                    beat_times[beat_index]
                )

                self._sleep_until(
                    playback_started + scheduled_time
                )

                elapsed = (
                    time.perf_counter()
                    - playback_started
                )

                if elapsed >= analysis.duration:
                    break

                strength = float(
                    strengths[
                        min(
                            beat_index,
                            len(strengths) - 1,
                        )
                    ]
                )

                next_index = min(
                    beat_index
                    + config.movement_every_n_beats,
                    len(beat_times) - 1,
                )

                if next_index > beat_index:
                    movement_window = float(
                        beat_times[next_index]
                        - beat_times[beat_index]
                    )
                else:
                    movement_window = (
                        60.0
                        / max(analysis.bpm, 1.0)
                        * config.movement_every_n_beats
                    )

                movement_duration = np.clip(
                    movement_window * 0.72,
                    config.minimum_move_duration,
                    config.maximum_move_duration,
                )

                progress = min(
                    1.0,
                    elapsed / max(analysis.duration, 0.1),
                )

                pose = self._make_pose(
                    step_number=step_number,
                    strength=strength,
                    progress=progress,
                    duration=float(movement_duration),
                )

                self.mini.goto_target(
                    head=pose["head"],
                    antennas=pose["antennas"],
                    body_yaw=pose["body_yaw"],
                    duration=pose["duration"],
                    method=pose["method"],
                )

                step_number += 1

            remaining = (
                analysis.duration
                - (
                    time.perf_counter()
                    - playback_started
                )
            )

            if remaining > 0:
                time.sleep(remaining)

        finally:
            print("[Dance] Returning to neutral...")
            self.neutral()
            time.sleep(self.config.return_duration)

            try:
                self.mini.media.stop_playing()
            except Exception:
                pass

    def _make_pose(
        self,
        step_number: int,
        strength: float,
        progress: float,
        duration: float,
    ) -> dict:
        config = self.config

        # Low-energy sections remain restrained.
        energy = (
            0.42
            + 0.58 * strength
        ) * config.intensity

        # Gently reduce motion during the final 10% of the song.
        if progress > 0.90:
            energy *= max(
                0.25,
                (1.0 - progress) / 0.10,
            )

        direction = (
            -1.0
            if step_number % 2 == 0
            else 1.0
        )

        phrase = step_number % 8

        yaw = (
            direction
            * config.max_head_yaw_deg
            * energy
        )

        roll = (
            -direction
            * config.max_head_roll_deg
            * energy
        )

        pitch_pattern = (
            0.25,
            -0.45,
            0.40,
            -0.20,
            0.50,
            -0.35,
            0.25,
            -0.15,
        )

        pitch = (
            config.max_head_pitch_deg
            * pitch_pattern[phrase]
            * energy
        )

        # Every fourth dance step opens the pose slightly.
        accent = phrase in {3, 7}

        body_scale = (
            1.0
            if accent
            else 0.58
        )

        body_yaw = math.radians(
            direction
            * config.max_body_yaw_deg
            * energy
            * body_scale
        )

        antenna_angle = (
            config.max_antenna_deg
            * energy
        )

        if phrase in {0, 4}:
            antennas_deg = (
                antenna_angle,
                -antenna_angle * 0.55,
            )
        elif phrase in {2, 6}:
            antennas_deg = (
                antenna_angle * 0.55,
                -antenna_angle,
            )
        elif accent:
            antennas_deg = (
                antenna_angle,
                -antenna_angle,
            )
        else:
            antennas_deg = (
                antenna_angle * 0.45,
                -antenna_angle * 0.45,
            )

        method = (
            "cartoon"
            if accent and strength > 0.62
            else "minjerk"
        )

        return {
            "head": create_head_pose(
                yaw=yaw,
                roll=roll,
                pitch=pitch,
                degrees=True,
            ),
            "antennas": np.deg2rad(
                antennas_deg
            ),
            "body_yaw": body_yaw,
            "duration": duration,
            "method": method,
        }

    @staticmethod
    def _sleep_until(
        target_time: float,
    ) -> None:
        while True:
            remaining = (
                target_time
                - time.perf_counter()
            )

            if remaining <= 0:
                return

            time.sleep(
                min(remaining, 0.02)
            )
