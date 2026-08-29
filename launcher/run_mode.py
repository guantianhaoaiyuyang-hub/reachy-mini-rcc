from __future__ import annotations

import argparse
import os
import runpy
import threading
import time
from pathlib import Path

import cv2


def install_embedded_vision_bridge(project_root: Path) -> None:
    runtime_dir = project_root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    preview_file = runtime_dir / "vision_preview.jpg"
    temp_file = runtime_dir / "vision_preview.tmp.jpg"

    lock = threading.Lock()
    last_write = 0.0
    write_interval = 1.0 / 12.0

    def embedded_imshow(_window_name, frame):
        nonlocal last_write

        now = time.perf_counter()
        if now - last_write < write_interval or frame is None:
            return

        last_write = now
        height, width = frame.shape[:2]
        transport = frame

        if width > 720:
            target_height = int(height * 720 / width)
            transport = cv2.resize(
                frame,
                (720, target_height),
                interpolation=cv2.INTER_AREA,
            )

        ok, encoded = cv2.imencode(
            ".jpg",
            transport,
            [cv2.IMWRITE_JPEG_QUALITY, 76],
        )
        if not ok:
            return

        try:
            with lock:
                temp_file.write_bytes(encoded.tobytes())
                os.replace(temp_file, preview_file)
        except Exception:
            pass

    cv2.imshow = embedded_imshow
    cv2.namedWindow = lambda *args, **kwargs: None
    cv2.resizeWindow = lambda *args, **kwargs: None
    cv2.destroyAllWindows = lambda *args, **kwargs: None
    cv2.waitKey = lambda *args, **kwargs: -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("module")
    parser.add_argument("--embedded-vision", action="store_true")
    args = parser.parse_args()

    project_root = Path(
        os.environ.get("RCC_PROJECT_ROOT", Path.cwd())
    ).resolve()
    os.chdir(project_root)

    if args.embedded_vision:
        install_embedded_vision_bridge(project_root)

    runpy.run_module(
        args.module,
        run_name="__main__",
        alter_sys=True,
    )


if __name__ == "__main__":
    main()
