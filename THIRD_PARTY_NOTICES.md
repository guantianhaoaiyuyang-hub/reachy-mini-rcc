# Third-Party Notices

Reachy Mini RCC uses third-party software, libraries, services and development tools.

The repository's Apache License 2.0 applies to original project material owned by the project author and contributors. It does not automatically replace the licenses of third-party software.

Important dependencies and ecosystems may include:

- Reachy Mini SDK / Pollen Robotics
- Python
- CustomTkinter
- OpenCV
- MediaPipe
- Pillow
- NumPy
- GStreamer
- PyGObject / GI
- websockets
- requests
- httpx
- aiohttp
- bleak
- sounddevice
- python-dotenv
- Torch, where applicable
- external cloud voice services such as Doubao / Volcengine
- Inno Setup

Each component remains subject to its own upstream license and notices.

## Models

Third-party model files are excluded from the initial source release unless redistribution permission has been reviewed.

## Music and Audio

Commercial or copyrighted music is not automatically part of the open-source project. Only audio assets with appropriate redistribution rights should be published.

## Bundled Runtime

A standalone Windows runtime may include separately licensed Python packages, native DLLs, GStreamer components, media libraries, computer-vision libraries and machine-learning libraries.

Before publishing a complete offline runtime or installer, perform a release-level license inventory.

## Dependency Source of Truth

The actual Python dependency set for a release should be checked against:

```text
pyproject.toml
uv.lock
```

Nothing in this file relicenses third-party code.