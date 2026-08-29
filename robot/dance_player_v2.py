from __future__ import annotations

import json
import math
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

import numpy as np
import miniaudio
from reachy_mini.utils import create_head_pose


@dataclass
class DanceV2Config:
    intensity: float = 0.75
    start_delay: float = 0.20
    return_duration: float = 1.20

    max_head_yaw_deg: float = 24.0
    max_head_roll_deg: float = 15.0
    max_head_pitch_deg: float = 12.0
    max_body_yaw_deg: float = 21.0
    max_antenna_deg: float = 68.0

    minimum_duration: float = 0.30
    maximum_duration: float = 0.68
    audio_chunk_seconds: float = 0.040
    audio_pipeline_warmup: float = 0.35
    stream_start_timeout: float = 12.0
    motion_update_hz: float = 45.0
    transition_softness: float = 0.82
    accent_probability: float = 0.18
    antenna_left_down_center_deg: float = -38.0
    antenna_right_down_center_deg: float = 38.0
    antenna_down_travel_deg: float = 36.0
    antenna_up_rebound_deg: float = 14.0
    antenna_left_min_deg: float = -82.0
    antenna_left_max_deg: float = 18.0
    antenna_right_min_deg: float = -18.0
    antenna_right_max_deg: float = 82.0


class DanceTimeline:
    def __init__(
        self,
        timeline_path: str | Path,
    ) -> None:
        self.path = Path(timeline_path).resolve()

        if not self.path.exists():
            raise FileNotFoundError(
                f"Dance timeline not found: {self.path}"
            )

        data = json.loads(
            self.path.read_text(encoding="utf-8-sig")
        )

        if data.get("format") != "reachy-dance-timeline-v2":
            raise ValueError(
                "Unsupported dance timeline format."
            )

        self.title = str(data.get("title", "Untitled"))
        self.audio_file = str(data["audio_file"])
        self.duration = float(data["duration"])
        self.source_bpm = float(data.get("source_bpm", 0.0))
        self.motion_bpm = float(data.get("motion_bpm", 0.0))
        self.style = str(data.get("style", "emotion"))
        self.events: list[dict[str, Any]] = list(
            data.get("events", [])
        )

        if not self.events:
            raise ValueError(
                "Dance timeline contains no motion events."
            )

    def resolve_audio_path(self) -> Path:
        return (
            self.path.parent / self.audio_file
        ).resolve()

    def actual_audio_duration(self) -> float:
        audio_path = self.resolve_audio_path()

        if MutagenFile is None:
            return self.duration

        try:
            metadata = MutagenFile(audio_path)

            if (
                metadata is not None
                and metadata.info is not None
            ):
                duration = float(metadata.info.length)

                if duration > 0:
                    return duration
        except Exception:
            pass

        return self.duration

    def events_for_duration(
        self,
        target_duration: float,
    ) -> list[dict[str, Any]]:
        original = sorted(
            self.events,
            key=lambda event: float(event["time"]),
        )

        if not original:
            return []

        last_original_time = float(
            original[-1]["time"]
        )

        if last_original_time >= target_duration - 1.0:
            return [
                dict(event)
                for event in original
                if float(event["time"]) < target_duration
            ]

        if len(original) >= 2:
            intervals = [
                float(original[index + 1]["time"])
                - float(original[index]["time"])
                for index in range(len(original) - 1)
            ]
            positive = [
                value
                for value in intervals
                if value > 0.05
            ]
            interval = (
                sum(positive) / len(positive)
                if positive
                else 0.84
            )
        else:
            interval = 0.84

        extended = [
            dict(event)
            for event in original
        ]

        next_time = last_original_time + interval
        pattern_index = 0

        while next_time < target_duration - 0.8:
            template = dict(
                original[
                    pattern_index % len(original)
                ]
            )
            progress = next_time / max(
                target_duration,
                0.1,
            )

            template["time"] = round(
                next_time,
                3,
            )

            if progress > 0.92:
                template["section"] = "ending"
                template["energy"] = max(
                    0.30,
                    float(template.get("energy", 0.65))
                    * (
                        (1.0 - progress)
                        / 0.08
                    ),
                )
            elif progress > 0.72:
                template["section"] = "bridge"
            elif progress > 0.40:
                template["section"] = "chorus"
            else:
                template["section"] = "verse"

            extended.append(template)
            next_time += interval
            pattern_index += 1

        return extended


class ReachyDancePlayerV2:
    """
    Lightweight timeline-driven dance player.

    There is no runtime beat analysis. Music and movement are scheduled
    from one monotonic clock using a prebuilt JSON timeline.
    """

    def __init__(
        self,
        mini,
        config: DanceV2Config | None = None,
        volume_file: str | Path | None = None,
        settings_file: str | Path | None = None,
    ) -> None:
        self.mini = mini
        self.config = config or DanceV2Config()
        self.volume_file = (
            Path(volume_file).resolve()
            if volume_file is not None
            else None
        )
        self.settings_file = (
            Path(settings_file).resolve()
            if settings_file is not None
            else None
        )

        self._stopped = False
        self._audio_thread: threading.Thread | None = None
        self._audio_started = threading.Event()
        self._audio_finished = threading.Event()
        self._audio_error: Exception | None = None
        self._playback_zero = 0.0
        self._cached_volume = 0.25
        self._last_volume_read = 0.0
        self.settings_file: Path | None = None
        self._settings_cache = {
            "total_intensity": self.config.intensity,
            "head_yaw_scale": 1.0,
            "head_roll_scale": 1.0,
            "head_pitch_scale": 1.0,
            "body_yaw_scale": 1.0,
            "antenna_scale": 1.0,
            "motion_speed": 1.0,
        }
        self._last_settings_read = 0.0
        self._motion_phase = 0.0
        self._last_pose = {
            "yaw": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "body": 0.0,
            "left_antenna": 0.0,
            "right_antenna": 0.0,
        }

    def prepare(self) -> None:
        print("[Dance V3.8] Enabling motors...")
        self.mini.enable_motors()
        time.sleep(0.8)

        print("[Dance V3.8] Waking robot...")
        self.mini.wake_up()
        time.sleep(2.4)

        self.mini.set_automatic_body_yaw(False)

        self.neutral(
            duration=self.config.return_duration
        )
        time.sleep(self.config.return_duration)

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
        timeline: DanceTimeline,
    ) -> None:
        audio_path = timeline.resolve_audio_path()

        if not audio_path.exists():
            raise FileNotFoundError(
                f"Music file not found: {audio_path}"
            )

        actual_duration = timeline.actual_audio_duration()
        playback_duration = max(
            timeline.duration,
            actual_duration,
        )
        playback_events = timeline.events_for_duration(
            playback_duration
        )

        print("=" * 64)
        print(f"[Dance V3.8] Song: {timeline.title}")
        print(
            f"[Dance V3.8] Project duration: "
            f"{timeline.duration:.2f} s"
        )
        print(
            f"[Dance V3.8] Audio duration: "
            f"{actual_duration:.2f} s"
        )
        print(
            f"[Dance V3.8] Playback duration: "
            f"{playback_duration:.2f} s"
        )
        print(f"[Dance V3.8] Source BPM: {timeline.source_bpm:.1f}")
        print(f"[Dance V3.8] Motion BPM: {timeline.motion_bpm:.1f}")
        print(f"[Dance V3.8] Events: {len(playback_events)}")
        print("=" * 64)

        self._stopped = False

        print("[Dance V3.8] Starting live PCM stream...")

        self._audio_started.clear()
        self._audio_finished.clear()
        self._audio_error = None

        self._audio_thread = threading.Thread(
            target=self._stream_audio,
            args=(audio_path,),
            daemon=True,
            name="reachy-dance-audio",
        )
        self._audio_thread.start()

        if not self._audio_started.wait(
            timeout=self.config.stream_start_timeout
        ):
            self._stopped = True
            raise RuntimeError(
                "Audio stream did not start in time."
            )

        if self._audio_error is not None:
            raise RuntimeError(
                f"Audio stream failed: {self._audio_error!r}"
            )

        playback_zero = self._playback_zero

        try:
            for event_index, event in enumerate(
                playback_events
            ):
                if self._stopped:
                    break

                event_time = float(event["time"])
                self._sleep_until(
                    playback_zero + event_time
                )

                if self._stopped:
                    break

                next_time = (
                    float(
                        playback_events[event_index + 1]["time"]
                    )
                    if event_index + 1 < len(playback_events)
                    else min(
                        playback_duration,
                        event_time + 0.85,
                    )
                )

                available = max(
                    0.20,
                    next_time - event_time,
                )

                movement_duration = float(
                    np.clip(
                        available * 0.70,
                        self.config.minimum_duration,
                        self.config.maximum_duration,
                    )
                )

                next_event = (
                    playback_events[event_index + 1]
                    if event_index + 1 < len(playback_events)
                    else None
                )

                self._play_continuous_segment(
                    current_event=event,
                    next_event=next_event,
                    segment_start=event_time,
                    segment_end=next_time,
                    playback_zero=playback_zero,
                )

                print(
                    "[Dance V3.8] "
                    f"{event_time:6.2f}s  "
                    f"{event['section']:<7}  "
                    f"{event['motion']}"
                )

            if not self._stopped:
                while (
                    not self._audio_finished.is_set()
                    and not self._stopped
                ):
                    time.sleep(0.02)

                if self._audio_error is not None:
                    raise RuntimeError(
                        f"Audio stream failed: {self._audio_error!r}"
                    )

        finally:
            self._finish()

    def stop(self) -> None:
        self._stopped = True

        try:
            self.mini.media.stop_playing()
        except Exception:
            pass

        thread = self._audio_thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)

    def _read_live_volume(self) -> float:
        now = time.perf_counter()

        if (
            self.volume_file is None
            or now - self._last_volume_read < 0.05
        ):
            return self._cached_volume

        self._last_volume_read = now

        try:
            payload = json.loads(
                self.volume_file.read_text(
                    encoding="utf-8"
                )
            )
            volume = float(
                payload.get(
                    "volume",
                    self._cached_volume,
                )
            )
            self._cached_volume = max(
                0.0,
                min(2.2, volume),
            )
        except Exception:
            pass

        return self._cached_volume

    def _stream_audio(
        self,
        audio_path: Path,
    ) -> None:
        try:
            sample_rate = int(
                self.mini.media
                .get_output_audio_samplerate()
            )
            channels = int(
                self.mini.media
                .get_output_channels()
            )
            channels = max(1, channels)

            frames_per_chunk = max(
                256,
                int(
                    sample_rate
                    * self.config.audio_chunk_seconds
                ),
            )

            decoder = miniaudio.stream_file(
                str(audio_path),
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=channels,
                sample_rate=sample_rate,
                frames_to_read=frames_per_chunk,
            )

            # Keep the queue small so live volume changes are audible
            # quickly and stale buffers cannot build up.
            try:
                self.mini.media.set_max_output_buffers(8)
            except Exception:
                pass

            self.mini.media.start_playing()

            # WebRTC/GStreamer needs a short transition from READY to PLAYING.
            # Pushing immediately can return GST_FLOW_FLUSHING.
            time.sleep(self.config.audio_pipeline_warmup)

            if self._stopped:
                return

            self._playback_zero = (
                time.perf_counter()
                + self.config.start_delay
            )
            self._audio_started.set()

            frame_cursor = 0

            # Prime the WebRTC appsrc with a few silent buffers.
            silent = np.zeros(
                (frames_per_chunk, channels),
                dtype=np.float32,
            )
            for _ in range(3):
                if self._stopped:
                    return
                self.mini.media.push_audio_sample(silent)
                time.sleep(
                    frames_per_chunk / sample_rate
                )

            self._playback_zero = time.perf_counter()

            for decoded_chunk in decoder:
                if self._stopped:
                    break

                target_time = (
                    self._playback_zero
                    + frame_cursor / sample_rate
                )
                self._sleep_until(target_time)

                if self._stopped:
                    break

                samples = np.asarray(
                    decoded_chunk,
                    dtype=np.float32,
                )

                if channels > 1:
                    samples = samples.reshape(
                        -1,
                        channels,
                    )

                gain = self._read_live_volume()

                amplified = (
                    samples * gain
                )

                # Soft limiter: boosts quieter recordings while avoiding
                # harsh digital clipping when gain is above 1.0.
                scaled = (
                    np.tanh(amplified * 1.25)
                    / np.tanh(1.25)
                ).astype(
                    np.float32,
                    copy=False,
                )

                self.mini.media.push_audio_sample(
                    scaled
                )

                frame_cursor += (
                    scaled.shape[0]
                    if scaled.ndim > 1
                    else len(scaled) // channels
                )

        except Exception as exc:
            self._audio_error = exc
            self._stopped = True
            self._audio_started.set()

        finally:
            self._audio_finished.set()

    def _finish(self) -> None:
        print("[Dance V3.8] Returning to neutral...")

        try:
            self.mini.set_target(
                head=create_head_pose(),
                antennas=np.deg2rad([0.0, 0.0]),
                body_yaw=0.0,
            )
            time.sleep(self.config.return_duration)
        except Exception as exc:
            print(
                "[Dance V3.8] Neutral warning:",
                repr(exc),
            )

        try:
            self.mini.media.stop_playing()
        except Exception:
            pass

        thread = self._audio_thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)

    @staticmethod
    def _smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    @staticmethod
    def _smootherstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return (
            value * value * value
            * (
                value * (value * 6.0 - 15.0)
                + 10.0
            )
        )

    def _read_motion_settings(self) -> dict[str, float]:
        now = time.perf_counter()

        if (
            self.settings_file is None
            or now - self._last_settings_read < 0.08
        ):
            return self._settings_cache

        self._last_settings_read = now

        try:
            payload = json.loads(
                self.settings_file.read_text(
                    encoding="utf-8-sig"
                )
            )

            limits = {
                "total_intensity": (0.30, 1.00),
                "head_yaw_scale": (0.30, 1.35),
                "head_roll_scale": (0.30, 1.35),
                "head_pitch_scale": (0.30, 1.35),
                "body_yaw_scale": (0.25, 1.35),
                "antenna_scale": (0.30, 1.40),
                "motion_speed": (0.65, 1.35),
            }

            for key, (minimum, maximum) in limits.items():
                value = float(
                    payload.get(
                        key,
                        self._settings_cache[key],
                    )
                )
                self._settings_cache[key] = max(
                    minimum,
                    min(maximum, value),
                )
        except Exception:
            pass

        return self._settings_cache

    def _motion_vector(
        self,
        event: dict[str, Any],
        local_phase: float,
    ) -> dict[str, float]:
        config = self.config
        motion = str(event.get("motion", "sway_left"))
        section = str(event.get("section", "verse"))
        event_energy = float(event.get("energy", 0.68))

        settings = self._read_motion_settings()

        shaped_energy = 0.50 + 0.50 * event_energy
        energy = float(
            np.clip(
                shaped_energy
                * settings["total_intensity"],
                0.32,
                1.0,
            )
        )

        yaw_scale = settings["head_yaw_scale"]
        roll_scale = settings["head_roll_scale"]
        pitch_scale = settings["head_pitch_scale"]
        body_scale_setting = settings["body_yaw_scale"]
        antenna_scale_setting = settings["antenna_scale"]

        direction = (
            -1.0
            if motion.endswith("left")
            else 1.0
        )

        # Continuous base oscillators.
        wave = math.sin(math.pi * local_phase)
        full_wave = math.sin(
            2.0 * math.pi * local_phase
        )
        quarter_wave = math.sin(
            0.5 * math.pi * local_phase
        )
        pulse = math.sin(
            math.pi * local_phase
        ) ** 2

        yaw = (
            direction
            * config.max_head_yaw_deg
            * energy
            * wave
        )
        roll = (
            -direction
            * config.max_head_roll_deg
            * energy
            * wave
        )
        pitch = (
            -config.max_head_pitch_deg
            * energy
            * 0.16
            * pulse
        )
        body = (
            direction
            * config.max_body_yaw_deg
            * energy
            * 0.70
            * wave
        )

        # The two antenna motors are mirrored. Their downward directions
        # therefore use opposite signs: left negative, right positive.
        antenna_wave_left = math.sin(
            2.0 * math.pi * local_phase + 0.35
        )
        antenna_wave_right = math.sin(
            2.0 * math.pi * local_phase - 0.35
        )

        left_antenna = (
            config.antenna_left_down_center_deg
            - config.antenna_down_travel_deg
            * energy
            * max(0.0, antenna_wave_left)
            + config.antenna_up_rebound_deg
            * energy
            * min(0.0, antenna_wave_left)
            * -1.0
        )

        right_antenna = (
            config.antenna_right_down_center_deg
            + config.antenna_down_travel_deg
            * energy
            * max(0.0, antenna_wave_right)
            - config.antenna_up_rebound_deg
            * energy
            * min(0.0, antenna_wave_right)
            * -1.0
        )

        if motion.startswith("nod"):
            yaw *= 0.45
            roll *= 0.28
            pitch = (
                -config.max_head_pitch_deg
                * energy
                * math.sin(
                    math.pi * local_phase
                )
            )
            body *= 0.40

            left_antenna = (
                config.max_antenna_deg
                * energy
                * 0.72
                * pulse
            )
            right_antenna = (
                -config.max_antenna_deg
                * energy
                * 0.72
                * pulse
            )

        elif motion.startswith("open"):
            yaw *= 1.05
            roll *= 0.78
            pitch = (
                config.max_head_pitch_deg
                * energy
                * 0.30
                * pulse
            )
            body *= 1.10

            left_antenna = (
                config.max_antenna_deg
                * energy
                * quarter_wave
            )
            right_antenna = (
                -config.max_antenna_deg
                * energy
                * quarter_wave
            )

        elif motion.startswith("soft"):
            yaw *= 0.72
            roll *= 0.78
            pitch = (
                config.max_head_pitch_deg
                * energy
                * 0.20
                * full_wave
            )
            body *= 0.46

            left_antenna = (
                config.max_antenna_deg
                * energy
                * 0.42
                * math.sin(
                    2.0 * math.pi * local_phase
                )
            )
            right_antenna = (
                config.max_antenna_deg
                * energy
                * 0.42
                * math.sin(
                    2.0 * math.pi * local_phase
                    + math.pi
                )
            )

        elif motion.startswith("sway"):
            # Add a subtle head ellipse instead of a flat left-right line.
            yaw = (
                direction
                * config.max_head_yaw_deg
                * energy
                * wave
            )
            roll = (
                -direction
                * config.max_head_roll_deg
                * energy
                * 0.82
                * wave
            )
            pitch = (
                config.max_head_pitch_deg
                * energy
                * 0.34
                * full_wave
            )

        # Phrase-level variation derived from the event time. This keeps
        # choreography deterministic but avoids repeating identical cycles.
        phrase_index = int(
            float(event.get("time", 0.0)) / 3.2
        )
        variation = phrase_index % 6

        if variation == 1:
            body *= -0.72
            left_antenna *= 1.10
            right_antenna *= 0.55

        elif variation == 2:
            pitch += (
                -config.max_head_pitch_deg
                * energy
                * 0.42
                * pulse
            )
            left_antenna = (
                config.max_antenna_deg
                * energy
                * math.sin(
                    2.0 * math.pi * local_phase
                )
            )
            right_antenna = (
                config.max_antenna_deg
                * energy
                * math.sin(
                    2.0 * math.pi * local_phase
                    + math.pi / 2.0
                )
            )

        elif variation == 3:
            yaw *= 0.72
            roll += (
                direction
                * config.max_head_roll_deg
                * energy
                * 0.42
                * full_wave
            )
            body *= 1.18

        elif variation == 4:
            left_antenna *= 1.28
            right_antenna *= 1.28
            pitch += (
                config.max_head_pitch_deg
                * energy
                * 0.24
                * pulse
            )

        elif variation == 5:
            yaw += (
                direction
                * config.max_head_yaw_deg
                * energy
                * 0.25
                * full_wave
            )
            body *= 0.50

        # Chorus gets broader and faster antenna waves.
        if section == "chorus":
            yaw *= 1.08
            body *= 1.12
            left_antenna += (
                config.max_antenna_deg
                * energy
                * 0.25
                * full_wave
            )
            right_antenna -= (
                config.max_antenna_deg
                * energy
                * 0.25
                * full_wave
            )

        elif section == "ending":
            yaw *= 0.70
            roll *= 0.70
            pitch *= 0.70
            body *= 0.62
            left_antenna *= 0.65
            right_antenna *= 0.65

        yaw *= yaw_scale
        roll *= roll_scale
        pitch *= pitch_scale
        body *= body_scale_setting
        left_antenna *= antenna_scale_setting
        right_antenna *= antenna_scale_setting

        # Re-map motif output to downward-biased mechanical coordinates.
        # Any motif contribution is treated as a smaller expressive offset
        # around the downward center rather than around zero.
        left_expression = float(
            np.clip(
                left_antenna,
                -config.max_antenna_deg,
                config.max_antenna_deg,
            )
        )
        right_expression = float(
            np.clip(
                right_antenna,
                -config.max_antenna_deg,
                config.max_antenna_deg,
            )
        )

        left_antenna = (
            config.antenna_left_down_center_deg
            + 0.42 * left_expression
        )
        right_antenna = (
            config.antenna_right_down_center_deg
            + 0.42 * right_expression
        )

        left_antenna = float(
            np.clip(
                left_antenna,
                config.antenna_left_min_deg,
                config.antenna_left_max_deg,
            )
        )
        right_antenna = float(
            np.clip(
                right_antenna,
                config.antenna_right_min_deg,
                config.antenna_right_max_deg,
            )
        )

        return {
            "yaw": float(
                np.clip(
                    yaw,
                    -config.max_head_yaw_deg,
                    config.max_head_yaw_deg,
                )
            ),
            "roll": float(
                np.clip(
                    roll,
                    -config.max_head_roll_deg,
                    config.max_head_roll_deg,
                )
            ),
            "pitch": float(
                np.clip(
                    pitch,
                    -config.max_head_pitch_deg,
                    config.max_head_pitch_deg,
                )
            ),
            "body": float(
                np.clip(
                    body,
                    -config.max_body_yaw_deg,
                    config.max_body_yaw_deg,
                )
            ),
            "left_antenna": left_antenna,
            "right_antenna": right_antenna,
        }

    def _play_continuous_segment(
        self,
        current_event: dict[str, Any],
        next_event: dict[str, Any] | None,
        segment_start: float,
        segment_end: float,
        playback_zero: float,
    ) -> None:
        settings = self._read_motion_settings()
        speed = settings["motion_speed"]

        duration = max(
            0.18,
            (segment_end - segment_start)
            / max(0.65, speed),
        )
        update_period = (
            1.0
            / (
                self.config.motion_update_hz
                * max(0.65, speed)
            )
        )

        segment_wall_start = (
            playback_zero + segment_start
        )
        segment_wall_end = (
            playback_zero + segment_end
        )

        while not self._stopped:
            now = time.perf_counter()

            if now >= segment_wall_end:
                break

            progress = (
                now - segment_wall_start
            ) / duration
            progress = max(
                0.0,
                min(1.0, progress),
            )

            current_vector = self._motion_vector(
                current_event,
                progress,
            )

            if next_event is not None:
                next_vector = self._motion_vector(
                    next_event,
                    0.0,
                )
            else:
                next_vector = {
                    key: 0.0
                    for key in current_vector
                }

            # Blend only near the end of the segment, preserving the
            # current motif while guaranteeing a soft handoff.
            blend_start = self.config.transition_softness
            if progress <= blend_start:
                blend = 0.0
            else:
                blend = self._smootherstep(
                    (
                        progress - blend_start
                    ) / max(
                        0.001,
                        1.0 - blend_start,
                    )
                )

            vector = {
                key: (
                    current_vector[key]
                    * (1.0 - blend)
                    + next_vector[key]
                    * blend
                )
                for key in current_vector
            }

            # Low-pass blend from the previously commanded pose.
            smoothing = 0.30
            filtered = {
                key: (
                    self._last_pose[key]
                    + smoothing
                    * (
                        vector[key]
                        - self._last_pose[key]
                    )
                )
                for key in vector
            }
            self._last_pose = filtered

            self.mini.set_target(
                head=create_head_pose(
                    yaw=filtered["yaw"],
                    roll=filtered["roll"],
                    pitch=filtered["pitch"],
                    degrees=True,
                ),
                antennas=np.deg2rad(
                    [
                        filtered["left_antenna"],
                        filtered["right_antenna"],
                    ]
                ),
                body_yaw=math.radians(
                    filtered["body"]
                ),
            )

            target_next_update = (
                now + update_period
            )
            self._sleep_until(
                target_next_update
            )

    def _pose_for_event(
        self,
        event: dict[str, Any],
        duration: float,
    ) -> dict[str, Any]:
        config = self.config
        motion = str(event["motion"])
        event_energy = float(event.get("energy", 0.6))

        # Preserve section dynamics, but avoid barely visible motion
        # at normal slider values. At 75% intensity, a medium-energy beat
        # now produces roughly 55% to 65% of the configured maximum pose.
        shaped_energy = 0.45 + 0.55 * event_energy

        energy = float(
            np.clip(
                shaped_energy * config.intensity,
                0.28,
                1.0,
            )
        )

        direction = (
            -1.0
            if motion.endswith("left")
            else 1.0
        )

        yaw = direction * config.max_head_yaw_deg
        roll = -direction * config.max_head_roll_deg
        pitch = 0.0
        body_scale = 0.55
        antenna_scale = 0.55
        method = "minjerk"

        if motion.startswith("nod"):
            yaw *= 0.55
            roll *= 0.35
            pitch = -config.max_head_pitch_deg
            antenna_scale = 0.72

        elif motion.startswith("open"):
            yaw *= 1.0
            roll *= 0.82
            pitch = config.max_head_pitch_deg * 0.25
            body_scale = 1.0
            antenna_scale = 1.0
            method = "minjerk"

        elif motion.startswith("soft"):
            yaw *= 0.62
            roll *= 0.65
            pitch = config.max_head_pitch_deg * 0.15
            body_scale = 0.35
            antenna_scale = 0.40

        elif motion.startswith("sway"):
            pitch = -config.max_head_pitch_deg * 0.12
            body_scale = 0.72
            antenna_scale = 0.62

        yaw *= energy
        roll *= energy
        pitch *= energy

        body_yaw = math.radians(
            direction
            * config.max_body_yaw_deg
            * energy
            * body_scale
        )

        antenna = (
            config.max_antenna_deg
            * energy
            * antenna_scale
        )

        antennas_deg = (
            antenna,
            -antenna,
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

    def _sleep_until(
        self,
        target_time: float,
    ) -> None:
        while not self._stopped:
            remaining = target_time - time.perf_counter()

            if remaining <= 0:
                return

            time.sleep(
                min(remaining, 0.02)
            )
