# Development History

## Purpose

This document summarizes major technical milestones that shaped Reachy Mini RCC v3.0.0.

It is not intended to reproduce private development logs or credentials.

## Realtime Voice Foundation

The project first established microphone recording, playback, realtime cloud voice interaction and robot-side audio output.

This created the base for later voice-controlled behavior.

## Voice + Motion

Motion control was progressively integrated with voice interaction, leading to V2 and later V3-series behavior.

The project moved from simple responses toward richer head/body/antenna expression.

## V3.5 Stability

A Windows runtime crash in V3.5 was resolved by routing launch through:

```text
launcher.run_mode
```

This launch path became a release contract for v3.0.0.

## Dynamic Robot Discovery

Early development relied on fixed LAN addresses.

This was replaced by dynamic discovery using cached valid state, Reachy Mini hostname/mDNS and physical-subnet scanning with daemon validation.

Historical fixed development IPs were removed from the public release.

## Network Preflight

Wi-Fi changes exposed a daemon state problem where Reachy Mini could remain reachable but still report a stale WLAN address.

Network Preflight was added to detect this condition, recover the daemon and revalidate before mode launch.

## VISION

MediaPipe face tracking was integrated into the RCC.

A packaged Windows heap instability was isolated to repeated OpenCV JPEG encoding in embedded preview.

The preview transport was changed to Pillow-based JPEG generation, producing a stable validated path.

## DANCE

Dance/timeline playback was added as a dedicated RCC mode.

A JSON BOM compatibility issue was resolved by using UTF-8-SIG compatible loading where appropriate.

## Secure Configuration

The installer architecture separated normal settings from sensitive credentials.

Normal configuration is stored under the user's local application-data area.

Sensitive values are stored in Windows Credential Manager and injected into child-mode environments at runtime.

## Windows Packaging

A standalone Windows runtime and Inno Setup installer architecture were developed so the RCC can run without requiring a system Python installation.

The source repository intentionally excludes the large bundled runtime.

## Open-Source Preparation

The public release process created a separate sanitized workspace, removed obsolete fixed-IP test files, reset transient robot state, excluded secrets/runtime/cache data, added public documentation and adopted Apache License 2.0 for original project code.

## v3.0.0 Release Position

v3.0.0 is treated as a validated development milestone with six working RCC modes:

```text
V1
V2
V3.5
VISION
DANCE
V3.5 + VISION
```

Future versions may refactor internal layout only after preserving these validated behaviors through regression testing.