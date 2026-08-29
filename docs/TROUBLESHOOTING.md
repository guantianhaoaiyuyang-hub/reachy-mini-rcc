# Troubleshooting

## RCC Does Not Start

Check:

```text
Python environment
dependencies
launcher imports
configuration
Windows runtime prerequisites
```

If using source mode, verify the environment was created from `pyproject.toml` / `uv.lock`.

## Robot Not Found

Check:

```text
robot power
PC network
same LAN or hotspot
daemon API on port 8000
VPN/TUN interference
Network Preflight output
```

Do not immediately hardcode a robot IP into production code.

## Reachy Mini Hotspot

When connected through Reachy Mini hotspot mode, `10.42.0.1` is expected.

## Network Changed but RCC Still Fails

The robot daemon may be reporting stale WLAN state.

Run/observe Network Preflight so the RCC can detect, recover and revalidate the connection.

## V3.5 Launch Failure

Confirm the mode still launches through:

```text
launcher.run_mode
```

Do not replace this with an untested direct subprocess launch.

## VISION Instability

Confirm the embedded preview still uses the validated Pillow-based JPEG path rather than repeated `cv2.imencode`.

Also check media connectivity and native runtime dependencies.

## Dance Timeline Parse Error

Check file encoding.

JSON files with BOM may require UTF-8-SIG compatible reading.

## Audio Warning

Some Windows/native media warnings may be non-blocking.

Treat a warning as fatal only if it actually prevents required audio behavior.

## Doubao Voice Failure

Check:

```text
internet access
credential presence
credential validity
service endpoint
WebSocket connectivity
```

Never paste full credentials into public logs or issues.

## Installer vs Source Differences

The packaged Windows build uses a bundled runtime that may behave differently from the source environment.

If a failure occurs only after packaging, test the same subsystem inside the packaged runtime before changing source logic.