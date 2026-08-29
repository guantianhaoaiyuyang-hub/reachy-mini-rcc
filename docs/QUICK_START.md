# Quick Start

## 1. Requirements

Recommended environment:

- Windows 10 or Windows 11 x64
- Python 3.12-class environment
- Reachy Mini
- Robot and computer on a reachable network
- Internet access when cloud voice services are used

## 2. Get the Source

Clone or extract the repository and open PowerShell in the project root.

Example:

```powershell
cd path\to\ReachyMini_RCC_v3.0.0
```

## 3. Install Dependencies

The dependency source of truth is:

```text
pyproject.toml
uv.lock
```

If `uv` is installed:

```powershell
uv sync
```

## 4. Configure Doubao

Use `.env.example` only as a reference.

Never commit real values.

Typical configuration names include:

```text
DOUBAO_WS_URL
DOUBAO_APP_ID
DOUBAO_ACCESS_TOKEN
DOUBAO_APP_KEY
DOUBAO_RESOURCE_ID
DOUBAO_MODEL
```

Installed RCC builds use Windows Credential Manager for sensitive values.

## 5. Connect Reachy Mini

The RCC uses dynamic robot discovery.

You should not need to hardcode a LAN address into production mode files.

The Reachy Mini hotspot path may use:

```text
10.42.0.1
```

## 6. Launch RCC

From the project environment:

```powershell
python -m launcher.app
```

## 7. Wake the Robot

Use the RCC controls to wake/enable the robot before running movement-dependent modes.

## 8. Select a Mode

Available validated v3.0.0 modes:

```text
V1
V2
V3.5
VISION
DANCE
V3.5 + VISION
```

## 9. If Launch Fails

Check:

- robot is powered and reachable;
- Windows network is on the correct Wi-Fi/LAN;
- VPN/TUN adapters are not interfering;
- cloud credentials are configured;
- microphone/audio devices are available;
- Network Preflight output for the actual failure point.

See `TROUBLESHOOTING.md`.