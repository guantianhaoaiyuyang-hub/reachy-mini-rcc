# Security Policy

## Supported Version

The current actively maintained open-source release is v3.0.x.

## Never Publish Secrets

Do not submit real `.env` files, Doubao Access Tokens, Doubao App Keys, Volcengine credentials, API keys, Bearer tokens, Windows Credential Manager exports, passwords or private authentication material.

The repository `.env.example` contains placeholders only.

## Installed RCC Credential Storage

Non-sensitive configuration may be stored under:

```text
%LOCALAPPDATA%\ReachyMiniRCC\settings.json
```

Sensitive values such as Doubao Access Token and App Key are stored in Windows Credential Manager and loaded into the process environment at runtime.

## Accidental Credential Exposure

If a real credential is exposed, treat it as compromised. Revoke or rotate it immediately, update the local value, remove the exposed content, and review Git history if necessary.

Deleting only the latest copy of a published secret is not sufficient.

## Safe Logs

Before sharing logs, remove access tokens, App Keys, authorization headers, personal names, unnecessary robot addresses, machine usernames, absolute local paths, private recordings, private camera images and device identifiers.

## Reachy Mini Networking

Production code should use dynamic robot discovery. Historical development-machine IP addresses must not be reintroduced.

`10.42.0.1` may legitimately appear because it is used by Reachy Mini hotspot-mode logic.

## Media Privacy

VISION, microphone and audio functions may process personal data. Obtain appropriate permission before recording, storing or publishing data involving other people.

## Robot Safety

Changes to motion code can cause unexpected physical movement. Test with sufficient clearance, conservative limits and a reliable way to stop the active mode.