from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np


class ReachyVisionTracker:
    """
    Optimized MediaPipe face tracker and camera monitor.

    Performance design:
    - Camera monitor and face detection use different update rates.
    - MediaPipe inference runs in a dedicated worker thread.
    - Head movement runs as a background task.
    - Only one head movement command may be active at a time.
    - The most recent face result is reused between detection frames.
    """

    WINDOW_NAME = "Reachy Mini Vision Monitor"

    def __init__(
        self,
        mini,
        motion,
        model_path: str | Path = (
            "models/blaze_face_short_range.tflite"
        ),
    ) -> None:
        self.mini = mini
        self.motion = motion
        self.model_path = Path(model_path)

        self.capture_dir = Path("captures")

        self.tracking_enabled = True
        self.closed = False

        # Face must leave this central region before the robot moves.
        self.dead_zone_x_ratio = 0.10
        self.dead_zone_y_ratio = 0.10

        # Head movement parameters.
        self.command_interval = 0.80
        self.movement_duration = 0.25

        # Position smoothing.
        self.smoothing_alpha = 0.30

        # Detection settings.
        self.detection_confidence = 0.50

        # Smaller detection image gives a large speed improvement.
        # 320 is normally sufficient for one person near the robot.
        self.detection_width = 320

        # Run face detection at approximately 10 FPS.
        # The camera monitor can continue refreshing faster.
        self.detection_interval = 0.10

        # Target monitor refresh rate.
        self.display_fps_limit = 30.0
        self.display_interval = 1.0 / self.display_fps_limit

        # Keep the last face result briefly if one detection is missed.
        self.face_result_timeout = 0.40

        self.smooth_x: float | None = None
        self.smooth_y: float | None = None

        self.last_command_time = 0.0
        self.last_detection_time = 0.0
        self.last_face_seen_time = 0.0

        self.last_frame_time = time.perf_counter()
        self.smoothed_fps = 0.0

        self.start_time = time.monotonic()
        self.last_timestamp_ms = -1

        self.latest_face: (
            tuple[int, int, int, int, float] | None
        ) = None

        self._detector = None

        # Only one MediaPipe inference runs at a time.
        self._detector_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="reachy-face-detector",
        )

        self._detection_task: asyncio.Task | None = None
        self._head_task: asyncio.Task | None = None

    @staticmethod
    def _clamp(
        value: int,
        minimum: int,
        maximum: int,
    ) -> int:
        return max(
            minimum,
            min(value, maximum),
        )

    @staticmethod
    def _draw_text(
        frame: np.ndarray,
        text: str,
        position: tuple[int, int],
        scale: float = 0.65,
    ) -> None:
        cv2.putText(
            frame,
            text,
            position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            text,
            position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def _create_detector(self):
        if not self.model_path.exists():
            raise FileNotFoundError(
                "Face detector model not found: "
                f"{self.model_path.resolve()}"
            )

        base_options = mp.tasks.BaseOptions(
            model_asset_path=str(
                self.model_path
            )
        )

        options = (
            mp.tasks.vision.FaceDetectorOptions(
                base_options=base_options,
                running_mode=(
                    mp.tasks.vision.RunningMode.VIDEO
                ),
                min_detection_confidence=(
                    self.detection_confidence
                ),
                min_suppression_threshold=0.30,
            )
        )

        return (
            mp.tasks.vision.FaceDetector
            .create_from_options(options)
        )

    def _next_timestamp_ms(self) -> int:
        timestamp_ms = int(
            (
                time.monotonic()
                - self.start_time
            )
            * 1000
        )

        if timestamp_ms <= self.last_timestamp_ms:
            timestamp_ms = (
                self.last_timestamp_ms + 1
            )

        self.last_timestamp_ms = timestamp_ms
        return timestamp_ms

    def _update_fps(self) -> None:
        now = time.perf_counter()

        delta = max(
            now - self.last_frame_time,
            0.0001,
        )

        current_fps = 1.0 / delta
        self.last_frame_time = now

        if self.smoothed_fps == 0.0:
            self.smoothed_fps = current_fps
        else:
            self.smoothed_fps = (
                self.smoothed_fps * 0.90
                + current_fps * 0.10
            )

    def _detect_largest_face_sync(
        self,
        frame: np.ndarray,
    ) -> tuple[int, int, int, int, float] | None:
        """
        Run MediaPipe synchronously.

        This method is executed in the dedicated detector thread,
        not in the asyncio event-loop thread.
        """
        frame_height, frame_width = frame.shape[:2]

        detection_width = min(
            self.detection_width,
            frame_width,
        )

        detection_height = max(
            1,
            int(
                frame_height
                * detection_width
                / frame_width
            ),
        )

        small_frame = cv2.resize(
            frame,
            (
                detection_width,
                detection_height,
            ),
            interpolation=cv2.INTER_AREA,
        )

        rgb_frame = cv2.cvtColor(
            small_frame,
            cv2.COLOR_BGR2RGB,
        )

        rgb_frame = np.ascontiguousarray(
            rgb_frame
        )

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame,
        )

        result = self._detector.detect_for_video(
            mp_image,
            self._next_timestamp_ms(),
        )

        selected_detection = None
        selected_area = 0

        for detection in result.detections:
            box = detection.bounding_box
            area = box.width * box.height

            if area > selected_area:
                selected_area = area
                selected_detection = detection

        if selected_detection is None:
            return None

        box = selected_detection.bounding_box

        scale_x = (
            frame_width / detection_width
        )

        scale_y = (
            frame_height / detection_height
        )

        x = int(box.origin_x * scale_x)
        y = int(box.origin_y * scale_y)

        face_width = int(
            box.width * scale_x
        )

        face_height = int(
            box.height * scale_y
        )

        x = self._clamp(
            x,
            0,
            frame_width - 1,
        )

        y = self._clamp(
            y,
            0,
            frame_height - 1,
        )

        face_width = self._clamp(
            face_width,
            1,
            frame_width - x,
        )

        face_height = self._clamp(
            face_height,
            1,
            frame_height - y,
        )

        confidence = 0.0

        if selected_detection.categories:
            confidence = (
                selected_detection
                .categories[0]
                .score
            )

        return (
            x,
            y,
            face_width,
            face_height,
            confidence,
        )

    async def _detect_face_async(
        self,
        frame: np.ndarray,
    ) -> None:
        """
        Run one face-detection operation without blocking the monitor.
        """
        loop = asyncio.get_running_loop()

        # Copy because the camera backend may reuse its frame buffer.
        frame_copy = frame.copy()

        try:
            face = await loop.run_in_executor(
                self._detector_executor,
                self._detect_largest_face_sync,
                frame_copy,
            )

            self.latest_face = face

            if face is not None:
                self.last_face_seen_time = (
                    time.perf_counter()
                )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[Vision] Detection error:",
                repr(exc),
            )

    def _start_detection_if_needed(
        self,
        frame: np.ndarray,
    ) -> None:
        now = time.perf_counter()

        if (
            now - self.last_detection_time
            < self.detection_interval
        ):
            return

        if (
            self._detection_task is not None
            and not self._detection_task.done()
        ):
            return

        self.last_detection_time = now

        self._detection_task = asyncio.create_task(
            self._detect_face_async(frame),
            name="vision-face-detection",
        )

    async def _move_head(
        self,
        target_x: int,
        target_y: int,
    ) -> None:
        try:
            await self.motion.run_external(
                self.mini.look_at_image,
                u=target_x,
                v=target_y,
                duration=self.movement_duration,
                perform_movement=True,
            )

        except TimeoutError:
            print(
                "[Vision] Head movement timeout; "
                "continuing."
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[Vision] Head movement error:",
                repr(exc),
            )

    def _start_head_move_if_possible(
        self,
        target_x: int,
        target_y: int,
    ) -> None:
        """
        Start a movement in the background.

        A new command is not started while the previous movement
        task is still active. This prevents command queues and video
        freezes.
        """
        if (
            self._head_task is not None
            and not self._head_task.done()
        ):
            return

        self._head_task = asyncio.create_task(
            self._move_head(
                target_x,
                target_y,
            ),
            name="vision-head-movement",
        )

    def _tracking_state_text(self) -> str:
        if not self.tracking_enabled:
            return "Tracking: OFF"

        if self.motion.vision_tracking_allowed:
            return "Tracking: ACTIVE"

        return (
            "Tracking: PAUSED BY "
            f"{self.motion.state.value.upper()}"
        )

    def _get_visible_face(
        self,
    ) -> tuple[int, int, int, int, float] | None:
        """
        Reuse the most recent result briefly.

        A single missed detection will therefore not immediately
        remove the face box or reset smoothing.
        """
        if self.latest_face is None:
            return None

        age = (
            time.perf_counter()
            - self.last_face_seen_time
        )

        if age > self.face_result_timeout:
            self.latest_face = None
            return None

        return self.latest_face

    async def run(self) -> None:
        self.capture_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._detector = (
            self._create_detector()
        )

        print("=" * 64)
        print(
            "Reachy Mini Optimized Vision Tracker "
            "+ Motion V3.5"
        )
        print("=" * 64)
        print("T: toggle head tracking")
        print("S: save snapshot")
        print("Q or Esc: close monitor")
        print()

        print(
            "[Vision] Waiting for camera..."
        )

        frame = None
        deadline = time.monotonic() + 20.0

        while (
            frame is None
            and time.monotonic() < deadline
            and not self.closed
        ):
            frame = self.mini.media.get_frame()
            await asyncio.sleep(0.05)

        if frame is None:
            raise RuntimeError(
                "No camera frame received "
                "within 20 seconds."
            )

        height, width = frame.shape[:2]

        print(
            f"[Vision] Camera ready: "
            f"{width} x {height}"
        )

        print(
            "[Vision] Display target: "
            f"{self.display_fps_limit:.0f} FPS"
        )

        print(
            "[Vision] Detection target: "
            f"{1.0 / self.detection_interval:.0f} FPS"
        )

        cv2.namedWindow(
            self.WINDOW_NAME,
            cv2.WINDOW_NORMAL,
        )

        cv2.resizeWindow(
            self.WINDOW_NAME,
            960,
            540,
        )

        try:
            while not self.closed:
                loop_started = time.perf_counter()

                frame = (
                    self.mini.media.get_frame()
                )

                if frame is None:
                    await asyncio.sleep(0.01)
                    continue

                self._update_fps()

                # Start detection only when due.
                # The current monitor loop does not wait for it.
                self._start_detection_if_needed(
                    frame
                )

                display = frame.copy()

                height, width = (
                    display.shape[:2]
                )

                center_x = width // 2
                center_y = height // 2

                dead_zone_x = int(
                    width
                    * self.dead_zone_x_ratio
                )

                dead_zone_y = int(
                    height
                    * self.dead_zone_y_ratio
                )

                face = self._get_visible_face()

                if face is not None:
                    (
                        x,
                        y,
                        face_width,
                        face_height,
                        confidence,
                    ) = face

                    raw_x = (
                        x + face_width / 2.0
                    )

                    raw_y = (
                        y + face_height / 2.0
                    )

                    if (
                        self.smooth_x is None
                        or self.smooth_y is None
                    ):
                        self.smooth_x = raw_x
                        self.smooth_y = raw_y

                    else:
                        self.smooth_x = (
                            self.smoothing_alpha
                            * raw_x
                            + (
                                1.0
                                - self.smoothing_alpha
                            )
                            * self.smooth_x
                        )

                        self.smooth_y = (
                            self.smoothing_alpha
                            * raw_y
                            + (
                                1.0
                                - self.smoothing_alpha
                            )
                            * self.smooth_y
                        )

                    target_x = self._clamp(
                        int(self.smooth_x),
                        0,
                        width - 1,
                    )

                    target_y = self._clamp(
                        int(self.smooth_y),
                        0,
                        height - 1,
                    )

                    error_x = (
                        target_x - center_x
                    )

                    error_y = (
                        target_y - center_y
                    )

                    outside_dead_zone = (
                        abs(error_x)
                        > dead_zone_x
                        or abs(error_y)
                        > dead_zone_y
                    )

                    cv2.rectangle(
                        display,
                        (x, y),
                        (
                            x + face_width,
                            y + face_height,
                        ),
                        (0, 255, 0),
                        2,
                    )

                    cv2.circle(
                        display,
                        (
                            target_x,
                            target_y,
                        ),
                        8,
                        (0, 255, 0),
                        2,
                    )

                    cv2.line(
                        display,
                        (
                            center_x,
                            center_y,
                        ),
                        (
                            target_x,
                            target_y,
                        ),
                        (0, 255, 0),
                        1,
                    )

                    now = time.perf_counter()

                    should_move = (
                        self.tracking_enabled
                        and self.motion
                        .vision_tracking_allowed
                        and outside_dead_zone
                        and (
                            now
                            - self.last_command_time
                        )
                        >= self.command_interval
                    )

                    if should_move:
                        self.last_command_time = now

                        self._start_head_move_if_possible(
                            target_x,
                            target_y,
                        )

                    face_status = (
                        "Face: DETECTED "
                        f"confidence={confidence:.2f}"
                    )

                else:
                    self.smooth_x = None
                    self.smooth_y = None

                    face_status = (
                        "Face: NOT DETECTED"
                    )

                cv2.rectangle(
                    display,
                    (
                        center_x - dead_zone_x,
                        center_y - dead_zone_y,
                    ),
                    (
                        center_x + dead_zone_x,
                        center_y + dead_zone_y,
                    ),
                    (255, 255, 255),
                    1,
                )

                cv2.drawMarker(
                    display,
                    (
                        center_x,
                        center_y,
                    ),
                    (255, 255, 255),
                    markerType=(
                        cv2.MARKER_CROSS
                    ),
                    markerSize=24,
                    thickness=1,
                )

                self._draw_text(
                    display,
                    self._tracking_state_text(),
                    (20, 32),
                )

                self._draw_text(
                    display,
                    face_status,
                    (20, 62),
                )

                self._draw_text(
                    display,
                    (
                        "Motion: "
                        f"{self.motion.state.value}"
                    ),
                    (20, 92),
                )

                self._draw_text(
                    display,
                    f"Display FPS: {self.smoothed_fps:.1f}",
                    (20, 122),
                )

                self._draw_text(
                    display,
                    (
                        "T: tracking  "
                        "S: snapshot  "
                        "Q: close monitor"
                    ),
                    (20, height - 20),
                    scale=0.55,
                )

                cv2.imshow(
                    self.WINDOW_NAME,
                    display,
                )

                key = cv2.waitKey(1) & 0xFF

                if key in (
                    ord("q"),
                    ord("Q"),
                    27,
                ):
                    print(
                        "[Vision] Monitor closed."
                    )

                    self.closed = True
                    break

                if key in (
                    ord("t"),
                    ord("T"),
                ):
                    self.tracking_enabled = (
                        not self.tracking_enabled
                    )

                    print(
                        "[Vision] Tracking enabled."
                        if self.tracking_enabled
                        else
                        "[Vision] Tracking disabled."
                    )

                if key in (
                    ord("s"),
                    ord("S"),
                ):
                    timestamp = (
                        time.strftime(
                            "%Y%m%d_%H%M%S"
                        )
                    )

                    output_path = (
                        self.capture_dir
                        / (
                            "reachy_monitor_"
                            f"{timestamp}.jpg"
                        )
                    )

                    saved = cv2.imwrite(
                        str(output_path),
                        display,
                    )

                    if saved:
                        print(
                            "[Vision] Snapshot saved:",
                            output_path.resolve(),
                        )
                    else:
                        print(
                            "[Vision] Snapshot "
                            "save failed."
                        )

                elapsed = (
                    time.perf_counter()
                    - loop_started
                )

                remaining = max(
                    0.0,
                    self.display_interval
                    - elapsed,
                )

                await asyncio.sleep(remaining)

        except asyncio.CancelledError:
            raise

        finally:
            pending_tasks = [
                task
                for task in (
                    self._detection_task,
                    self._head_task,
                )
                if (
                    task is not None
                    and not task.done()
                )
            ]

            for task in pending_tasks:
                task.cancel()

            for task in pending_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            if self._detector is not None:
                self._detector.close()
                self._detector = None

            self._detector_executor.shutdown(
                wait=False,
                cancel_futures=True,
            )

            cv2.destroyAllWindows()

            print(
                "[Vision] Optimized tracker stopped."
            )

    async def close(self) -> None:
        self.closed = True
        await asyncio.sleep(0)