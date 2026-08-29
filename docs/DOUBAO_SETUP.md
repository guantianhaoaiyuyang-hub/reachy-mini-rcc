# Doubao Setup

## Purpose

Reachy Mini RCC can use Doubao / Volcengine realtime voice services for conversational interaction.

## Public Repository Rule

Real credentials must never be committed.

The repository contains `.env.example` only as a development reference.

## Configuration Names

```text
DOUBAO_WS_URL
DOUBAO_APP_ID
DOUBAO_ACCESS_TOKEN
DOUBAO_APP_KEY
DOUBAO_RESOURCE_ID
DOUBAO_MODEL
```

## Installed RCC Storage

Non-sensitive settings may be stored under:

```text
%LOCALAPPDATA%\ReachyMiniRCC\settings.json
```

Sensitive values such as Access Token and App Key are stored in Windows Credential Manager.

At runtime the RCC loads required values into the process environment so child modes can inherit configuration.

## First-Run Configuration

The installed RCC includes first-run configuration flow for required Doubao settings.

Do not embed credentials into source files as a shortcut.

## Secret Exposure

If a real token or App Key is exposed publicly:

```text
treat as compromised
        鈫?revoke / rotate
        鈫?update local credential
        鈫?remove exposed content
        鈫?review Git history
```

Deleting only the latest copy does not make the old credential safe.

## Troubleshooting

If voice mode does not start:

- verify required fields are configured;
- verify internet access;
- verify WebSocket/service endpoint accessibility;
- verify the credential has not expired or been revoked;
- check RCC logs without publishing secret values.