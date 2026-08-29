from __future__ import annotations

import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from reachy_mini import ReachyMini


from config.robot_discovery import discover_robot
WINDOW_NAME = "Reachy Mini Face Tracker"

MODEL_PATH = Path("models/blaze_face_short_range.tflite")
CAPTURE_DIR = Path("captures")

DEAD_ZONE_X_RATIO = 0.10
DEAD_ZONE_Y_RATIO = 0.10

COMMAND_INTERVAL = 0.80
MOVEMENT_DURATION = 0.25

SMOOTHING_ALPHA = 0.30
DETECTION_CONFIDENCE = 0.50


def draw_text(
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


def clamp(
    value: int,
    minimum: int,
    maximum: int,
) -> int:
    return max(minimum, min(value, maximum))


def main() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Face detector model not found: {MODEL_PATH.resolve()}"
        )

    CAPTURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_options = mp.tasks.BaseOptions(
        model_asset_path=str(MODEL_PATH),
    )

    detector_options = mp.tasks.vision.FaceDetectorOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        min_detection_confidence=DETECTION_CONFIDENCE,
        min_suppression_threshold=0.30,
    )

    tracking_enabled = True

    smooth_x: float | None = None
    smooth_y: float | None = None

    last_command_time = 0.0
    last_frame_time = time.perf_counter()

    smoothed_fps = 0.0

    start_time = time.monotonic()
    last_timestamp_ms = -1

    print("=" * 64)
    print("Reachy Mini MediaPipe Face Tracker")
    print("=" * 64)
    print("T: enable or disable tracking")
    print("S: save snapshot")
    print("Q or Esc: quit")
    print()

    with mp.tasks.vision.FaceDetector.create_from_options(
        detector_options
    ) as detector:

        print()
        print("[RCC] Discovering Reachy Mini...")
        robot_host = discover_robot()
        print(f"[RCC] Reachy Mini found: {robot_host}")

        with ReachyMini(
            host=robot_host,
            connection_mode="network",
        ) as mini:

            print("Connected to Reachy Mini.")

            print("Enabling motors...")
            mini.enable_motors()
            time.sleep(1)

            print("Waking up robot...")
            mini.wake_up()
            time.sleep(3)

            print("Waiting for camera frames...")

            frame = None
            deadline = time.monotonic() + 20.0

            while (
                frame is None
                and time.monotonic() < deadline
            ):
                frame = mini.media.get_frame()
                time.sleep(0.05)

            if frame is None:
                raise RuntimeError(
                    "No camera frame received within 20 seconds."
                )

            height, width = frame.shape[:2]

            print(
                f"Camera ready: {width} x {height}"
            )
            print("Face tracking started.")

            cv2.namedWindow(
                WINDOW_NAME,
                cv2.WINDOW_NORMAL,
            )

            cv2.resizeWindow(
                WINDOW_NAME,
                960,
                540,
            )

            try:
                while True:
                    frame = mini.media.get_frame()

                    if frame is None:
                        time.sleep(0.01)
                        continue

                    now = time.perf_counter()

                    frame_delta = max(
                        now - last_frame_time,
                        0.0001,
                    )

                    current_fps = 1.0 / frame_delta
                    last_frame_time = now

                    if smoothed_fps == 0.0:
                        smoothed_fps = current_fps
                    else:
                        smoothed_fps = (
                            smoothed_fps * 0.90
                            + current_fps * 0.10
                        )

                    display = frame.copy()

                    height, width = display.shape[:2]

                    center_x = width // 2
                    center_y = height // 2

                    dead_zone_x = int(
                        width * DEAD_ZONE_X_RATIO
                    )

                    dead_zone_y = int(
                        height * DEAD_ZONE_Y_RATIO
                    )

                    rgb_frame = cv2.cvtColor(
                        frame,
                        cv2.COLOR_BGR2RGB,
                    )

                    rgb_frame = np.ascontiguousarray(
                        rgb_frame
                    )

                    mp_image = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=rgb_frame,
                    )

                    timestamp_ms = int(
                        (
                            time.monotonic()
                            - start_time
                        )
                        * 1000
                    )

                    if (
                        timestamp_ms
                        <= last_timestamp_ms
                    ):
                        timestamp_ms = (
                            last_timestamp_ms + 1
                        )

                    last_timestamp_ms = timestamp_ms

                    result = detector.detect_for_video(
                        mp_image,
                        timestamp_ms,
                    )

                    selected_detection = None
                    selected_area = 0

                    for detection in result.detections:
                        box = detection.bounding_box

                        area = (
                            box.width
                            * box.height
                        )

                        if area > selected_area:
                            selected_area = area
                            selected_detection = detection

                    face_detected = (
                        selected_detection is not None
                    )

                    if face_detected:
                        box = (
                            selected_detection
                            .bounding_box
                        )

                        x = clamp(
                            box.origin_x,
                            0,
                            width - 1,
                        )

                        y = clamp(
                            box.origin_y,
                            0,
                            height - 1,
                        )

                        w = clamp(
                            box.width,
                            1,
                            width - x,
                        )

                        h = clamp(
                            box.height,
                            1,
                            height - y,
                        )

                        raw_x = x + w / 2.0
                        raw_y = y + h / 2.0

                        if (
                            smooth_x is None
                            or smooth_y is None
                        ):
                            smooth_x = raw_x
                            smooth_y = raw_y
                        else:
                            smooth_x = (
                                SMOOTHING_ALPHA
                                * raw_x
                                + (
                                    1.0
                                    - SMOOTHING_ALPHA
                                )
                                * smooth_x
                            )

                            smooth_y = (
                                SMOOTHING_ALPHA
                                * raw_y
                                + (
                                    1.0
                                    - SMOOTHING_ALPHA
                                )
                                * smooth_y
                            )

                        target_x = clamp(
                            int(smooth_x),
                            0,
                            width - 1,
                        )

                        target_y = clamp(
                            int(smooth_y),
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
                            (x + w, y + h),
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

                        if (
                            tracking_enabled
                            and outside_dead_zone
                            and (
                                now
                                - last_command_time
                            )
                            >= COMMAND_INTERVAL
                        ):
                            try:
                                mini.look_at_image(
                                    u=target_x,
                                    v=target_y,
                                    duration=(
                                        MOVEMENT_DURATION
                                    ),
                                    perform_movement=True,
                                )

                            except TimeoutError:
                                print(
                                    "Head movement timeout; continuing."
                                )

                            except Exception as exc:
                                print(
                                    "Head movement error:",
                                    repr(exc),
                                )

                            finally:
                                last_command_time = now

                        confidence = 0.0

                        if (
                            selected_detection
                            .categories
                        ):
                            confidence = (
                                selected_detection
                                .categories[0]
                                .score
                            )

                        face_status = (
                            "Face: DETECTED "
                            f"confidence={confidence:.2f}"
                        )

                    else:
                        smooth_x = None
                        smooth_y = None

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

                    tracking_status = (
                        "Tracking: ON"
                        if tracking_enabled
                        else "Tracking: OFF"
                    )

                    draw_text(
                        display,
                        tracking_status,
                        (20, 32),
                    )

                    draw_text(
                        display,
                        face_status,
                        (20, 62),
                    )

                    draw_text(
                        display,
                        f"FPS: {smoothed_fps:.1f}",
                        (20, 92),
                    )

                    draw_text(
                        display,
                        (
                            "T: tracking  "
                            "S: snapshot  "
                            "Q: quit"
                        ),
                        (20, height - 20),
                        scale=0.55,
                    )

                    cv2.imshow(
                        WINDOW_NAME,
                        display,
                    )

                    key = (
                        cv2.waitKey(1)
                        & 0xFF
                    )

                    if key in (
                        ord("q"),
                        ord("Q"),
                        27,
                    ):
                        break

                    if key in (
                        ord("t"),
                        ord("T"),
                    ):
                        tracking_enabled = (
                            not tracking_enabled
                        )

                        if tracking_enabled:
                            print(
                                "Tracking enabled."
                            )
                        else:
                            print(
                                "Tracking disabled."
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
                            CAPTURE_DIR
                            / (
                                "reachy_face_"
                                f"{timestamp}.jpg"
                            )
                        )

                        saved = cv2.imwrite(
                            str(output_path),
                            display,
                        )

                        if saved:
                            print(
                                "Snapshot saved:",
                                output_path.resolve(),
                            )
                        else:
                            print(
                                "Snapshot save failed."
                            )

            finally:
                cv2.destroyAllWindows()

    print("Face tracking stopped.")


if __name__ == "__main__":
    main()