# Contributing to Reachy Mini RCC

Thank you for considering a contribution.

## Core Rules

Preserve the following unless a dedicated regression-tested change proves a replacement is safe:

- dynamic Reachy Mini discovery;
- Reachy Mini hotspot support;
- Network Preflight;
- validated V3.5 routing through `launcher.run_mode`;
- validated Pillow-based VISION preview behavior;
- existing validated production mode mappings.

Do not commit real credentials, `.env`, private logs, private media, copyrighted music without redistribution rights or third-party model files with unclear licenses.

## Development Environment

Use the dependency metadata in:

```text
pyproject.toml
uv.lock
```

With `uv`:

```powershell
uv sync
```

## Change Workflow

Prefer focused changes. Understand the current behavior, create or update focused tests, make the minimum implementation change, run relevant tests, run broader regression checks, and test on real hardware when appropriate.

## High-Risk Areas

Changes to V3.5, VISION, V3.5 + VISION, robot discovery, Network Preflight, audio transport, motion control or credential startup require extra regression attention.

## Production Modules Under `tests/`

The v3.0.0 project intentionally preserves several production mode modules under `tests/` because those exact module paths are validated. Do not move them as part of unrelated cleanup.

## Pull Requests

Explain what changed, why, how it was tested, whether real Reachy Mini hardware was used, and whether networking, audio, vision or motion behavior changed.

## License

Contributions intentionally submitted for inclusion may be distributed under the repository's Apache License 2.0 unless explicitly stated otherwise before incorporation. Third-party code must retain its own license and attribution requirements.