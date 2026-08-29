# Architecture

## Overview

Reachy Mini RCC v3.0.0 is a Windows-oriented multimodal control stack for Reachy Mini. It coordinates GUI control, cloud voice interaction, robot motion, perception, audio, dance playback, network discovery and deployment concerns.

At a high level:

```text
User
  鈹?  鈻?Reachy Mini RCC
  鈹?  鈹溾攢 Voice / Doubao realtime interaction
  鈹溾攢 Motion control
  鈹溾攢 Vision / MediaPipe
  鈹溾攢 Dance playback
  鈹溾攢 Audio bridge
  鈹斺攢 Network discovery / preflight
  鈹?  鈻?Reachy Mini SDK / Daemon API
  鈹?  鈻?Reachy Mini Hardware
```

## Major Areas

### `launcher/`

Contains the desktop RCC and mode-launch orchestration.

Important files include:

```text
launcher/app.py
launcher/run_mode.py
launcher/setup/
```

`launcher/app.py` is the primary RCC user interface. `launcher.run_mode` is part of the validated mode-launch path and must not be bypassed casually.

### `config/`

Contains robot discovery and transient connection state.

Important files include:

```text
config/robot_discovery.py
config/robot_state.json
```

Production modes use dynamic discovery rather than fixed development-machine robot addresses.

### `doubao/`

Contains realtime cloud voice integration and protocol/configuration code.

Secrets must never be hardcoded in source.

### `robot/`

Contains robot-facing behavior such as motion controllers, audio bridging, dance playback and vision support.

### `tests/`

The v3.0.0 repository intentionally contains several production mode entry modules under `tests/`.

These paths are preserved because they have already been validated in the working RCC.

## Validated Production Modes

```text
V1
V2
V3.5
VISION
DANCE
V3.5 + VISION
```

The current mode mappings must remain stable for v3.0.0.

## V3.5 Runtime Contract

Validated launch path:

```text
RCC
  鈫?launcher.run_mode
  鈫?tests.reachy_voice_motion_v3_test
```

The historical direct subprocess path should not be restored without regression testing.

## Vision Runtime Contract

The embedded vision preview retains a Pillow-based JPEG generation path.

This replaced repeated OpenCV `cv2.imencode` calls that were associated with instability in the packaged Windows runtime.

## Network Architecture

Robot connection resolution is dynamic.

Typical discovery order:

```text
valid cached state
      鈫?Reachy Mini hostname / mDNS
      鈫?physical private IPv4 subnet scan
      鈫?daemon API validation
```

Virtual/TUN/VPN interfaces should not be preferred.

The hotspot gateway/API address `10.42.0.1` is intentional and may appear in networking code.

## Network Preflight

Before mode launch, RCC may:

```text
discover robot
  鈫?validate daemon API
  鈫?resolve current robot address
  鈫?inspect daemon WLAN state
  鈫?validate media connectivity
  鈫?detect stale daemon state
  鈫?recover/restart daemon when required
  鈫?revalidate
  鈫?launch selected mode
```

This behavior is part of the production architecture.

## Configuration and Credentials

Normal application settings may be stored under:

```text
%LOCALAPPDATA%\ReachyMiniRCC\settings.json
```

Sensitive values are stored in Windows Credential Manager and injected into the process environment at runtime.

The public repository includes `.env.example` only as a development reference.

## Deployment Architecture

The source repository does not include the large standalone runtime.

Windows packaged builds use a separate bundled runtime and an Inno Setup installer source:

```text
installer/ReachyMini_RCC_Setup.iss
```

Compiled installer binaries should be distributed separately from the source tree.