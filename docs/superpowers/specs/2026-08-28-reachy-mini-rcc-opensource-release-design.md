# Reachy Mini RCC v3.0.0 Open-Source Release Design

## 1. Project Identity

Project name:

`Reachy Mini RCC`

Version:

`v3.0.0`

Primary author:

`Neil Guan`

Copyright notice:

`Copyright 2026 Neil Guan`

Primary software license:

`Apache License 2.0`

The Apache-2.0 license applies only to original project content owned
by the project author and contributors. Third-party software, models,
media and other assets remain governed by their original licenses.

---

## 2. Open-Source Workspace

The public release workspace is:

`F:\ReachyMini\OpenSource\ReachyMini_RCC_v3.0.0`

The validated development source remains separate and must not be
modified by open-source packaging work.

Open-source preparation must never modify the stable development
project as a side effect.

---

## 3. Project Positioning

Reachy Mini RCC is a multimodal interaction and robot control project
for Reachy Mini.

The public project should present the system as an integrated robotics
software stack rather than as a single AI model.

Primary capabilities include:

- realtime conversational voice interaction;
- robot motion control;
- motion generation and voice-driven motion;
- V1 interaction mode;
- V2 voice and motion mode;
- V3.5 voice and motion mode;
- VISION face tracking mode;
- DANCE mode;
- combined V3.5 + VISION mode;
- Reachy Mini body audio playback;
- MediaPipe-based visual perception;
- dynamic robot discovery;
- cross-Wi-Fi robot discovery;
- Reachy Mini hotspot support;
- Network Preflight;
- stale daemon network-state recovery;
- secure Doubao credential configuration;
- Windows Credential Manager integration;
- RCC desktop graphical control center;
- standalone Windows deployment architecture;
- Inno Setup installer architecture.

---

## 4. Public Repository Strategy

The main source-code repository should use GitHub as the canonical
source repository.

Hugging Face should complement GitHub rather than replace it.

Recommended publication structure:

### GitHub

Use for:

- complete source code;
- issue tracking;
- pull requests;
- releases;
- source documentation;
- Windows installer releases;
- version history.

Recommended repository name:

`reachy-mini-rcc`

### Hugging Face

Use for:

- project presentation;
- future Reachy Mini web/Space demonstrations;
- future datasets;
- future trained models;
- project Collections.

The current Windows CustomTkinter RCC must not be represented as a
cloud-native Hugging Face Space without a separate compatible web
implementation.

---

## 5. Repository Root Documentation

The first public release must contain:

- `README.md`
- `LICENSE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `THIRD_PARTY_NOTICES.md`
- `.gitignore`
- `.env.example`

These files form the public-facing release contract.

---

## 6. README Design

README.md should be primarily English so that the repository can be
used internationally.

Chinese documentation may coexist under `docs/`.

README must include:

1. Project title.
2. Short project description.
3. Current version.
4. Author.
5. Main capability overview.
6. Six validated RCC modes.
7. System architecture overview.
8. Repository structure.
9. Installation/development prerequisites.
10. Configuration instructions.
11. Doubao credential security explanation.
12. Robot discovery explanation.
13. Launch instructions.
14. Known limitations.
15. Documentation links.
16. License information.
17. Third-party notice.
18. Project status.

README must not claim functionality that has not been validated.

---

## 7. Validated Production Modes

The first public release preserves the currently validated six-mode
structure.

The production modes are:

- V1
- V2
- V3.5
- VISION
- DANCE
- V3.5 + VISION

The currently validated production module mappings must remain
unchanged for v3.0.0.

The existing `tests` package contains several production mode modules.
This unusual layout is intentional for v3.0.0 because it reflects the
tested working system.

Do not reorganize these production modules merely for repository
appearance before the initial release.

Future versions may refactor production modes into a dedicated
`modes/` package after regression testing.

---

## 8. V3.5 Launch Contract

V3.5 must retain the validated launch chain:

RCC
→ `launcher.run_mode`
→ `tests.reachy_voice_motion_v3_test`

The historical direct subprocess path must not be restored.

---

## 9. Vision Preview Contract

Embedded VISION preview must retain the Pillow-based JPEG transport
implementation that replaced the unstable repeated OpenCV
`cv2.imencode` preview path.

The open-source v3.0.0 release must not revert this fix.

VISION and V3.5 + VISION must retain the validated embedded-preview
architecture.

---

## 10. Robot Discovery Contract

Production modes must use dynamic robot discovery instead of a fixed
development-machine robot IP address.

The repository must not contain historical fixed robot addresses such
as development LAN addresses.

`config/robot_state.json` is transient state and must not contain a
developer robot address in a public release.

The Reachy Mini hotspot address:

`10.42.0.1`

is allowed where it forms part of intentional hotspot-mode logic.

It must not be removed merely because it is an IP address.

---

## 11. Network Preflight Contract

The public RCC must preserve Network Preflight behavior.

The system should:

- discover the Reachy Mini dynamically;
- validate the daemon API;
- resolve the active robot address;
- compare daemon-reported WLAN state;
- validate media availability;
- identify stale daemon WLAN state;
- recover the daemon when required;
- revalidate after recovery;
- cancel mode launch when required validation fails.

Network recovery code is part of production behavior and must not be
simplified merely for open-source presentation.

---

## 12. Credential Security

Real credentials must never be committed to the public repository.

The public repository must not contain:

- real Doubao access tokens;
- real Doubao App Keys;
- private API keys;
- Windows Credential Manager exports;
- `.env` containing user credentials;
- credentials copied into documentation or screenshots.

`.env.example` may contain variable names and placeholder values only.

For installed RCC use:

### Non-sensitive configuration

Store under:

`%LOCALAPPDATA%\ReachyMiniRCC\settings.json`

### Sensitive configuration

Store in Windows Credential Manager.

Current sensitive fields include:

- Doubao Access Token
- Doubao App Key

Environment-variable names and configuration field names are not
themselves secrets.

---

## 13. Files That Must Not Be Published

The first public source repository must exclude:

- `.env`
- private credentials;
- `.venv`
- bundled `runtime/`
- Python cache files;
- `__pycache__`
- `.pyc`
- `.pyo`
- developer logs;
- temporary preview images;
- local cache data;
- backup files;
- `.before_*` files;
- private test recordings;
- user images;
- private screenshots;
- generated installer `dist/`;
- Windows installer EXE in the source tree;
- unreviewed music;
- unreviewed third-party model files.

Windows installer binaries may later be distributed through GitHub
Releases after final release verification.

---

## 14. Music Policy

Robot dance source code and dance timeline logic may be open-sourced.

Audio assets must not be included by default.

A music file may be published only when redistribution rights are
known and compatible with public distribution.

The initial repository should contain a `music/README.md` explaining
this policy.

---

## 15. Model Policy

Third-party model files must be reviewed individually before
redistribution.

Unknown-license models must not be published.

Where appropriate, the repository should provide download
instructions or scripts rather than redistributing third-party model
weights directly.

The initial repository should contain a `models/README.md`.

---

## 16. Third-Party Software

`THIRD_PARTY_NOTICES.md` should identify important external
dependencies used by the project.

At minimum, review and document dependencies such as:

- Reachy Mini SDK / Pollen Robotics;
- Python;
- OpenCV;
- MediaPipe;
- GStreamer;
- PyGObject / GI;
- CustomTkinter;
- Pillow;
- NumPy;
- websockets;
- requests;
- httpx;
- aiohttp;
- bleak;
- sounddevice;
- Torch, where applicable;
- python-dotenv;
- other dependencies present in `pyproject.toml`.

The notice must not state that all third-party packages use
Apache-2.0.

Each dependency remains subject to its own upstream license.

---

## 17. License

The project source owned by Neil Guan will be released under:

Apache License 2.0

Copyright notice:

Copyright 2026 Neil Guan

The repository `LICENSE` file must contain the standard Apache License
2.0 text without modifying the license terms.

Where useful, repository documentation may separately state:

`Copyright 2026 Neil Guan`

---

## 18. Security Policy

`SECURITY.md` must tell users not to publish sensitive credentials in
issues, logs or pull requests.

Security reports should avoid including:

- access tokens;
- App Keys;
- full credentials;
- private network information that is not required;
- personally identifying recordings or images.

The document should explain credential rotation after accidental
exposure.

---

## 19. Contribution Policy

`CONTRIBUTING.md` should explain:

- how to create a development environment;
- how to submit changes;
- code-style expectations;
- requirement to avoid committing secrets;
- requirement to preserve dynamic robot discovery;
- requirement to preserve validated production mode behavior;
- requirement to add or update tests for behavioral changes;
- requirement to test relevant robot functionality where hardware is
  available.

Changes that alter V3.5, VISION, V3.5 + VISION, robot discovery,
audio transport or Network Preflight should receive additional
regression attention.

---

## 20. Documentation Structure

The planned documentation tree is:

docs/
├─ ARCHITECTURE.md
├─ QUICK_START.md
├─ NETWORKING.md
├─ DOUBAO_SETUP.md
├─ VISION.md
├─ DANCE.md
├─ TROUBLESHOOTING.md
├─ DEVELOPMENT_HISTORY.md
└─ superpowers/
   ├─ specs/
   └─ plans/

The large Chinese development teaching notebook may later be added
after confirming that it contains no private credentials, identifying
information, private logs or copyrighted material that should not be
redistributed.

---

## 21. Initial Release Scope

The first open-source release is a source release.

It does not need to include:

- a downloadable runtime;
- the 1+ GB standalone Python environment;
- licensed music files;
- unreviewed model weights;
- the Windows installer EXE;
- a Hugging Face hosted RCC implementation.

Those may be published separately when appropriate.

---

## 22. GitHub Release Strategy

After the source repository has been validated:

1. Initialize the public Git repository.
2. Perform a final secret scan.
3. Verify repository content.
4. Run available automated tests.
5. Run appropriate real-robot regression tests.
6. Commit the release.
7. Tag `v3.0.0`.
8. Publish the GitHub repository.
9. Optionally publish the validated Windows installer in GitHub
   Releases.
10. Publish SHA256 checksums for distributed binaries.

---

## 23. Hugging Face Strategy

Hugging Face should initially provide a project-facing presence rather
than duplicate the full Windows repository structure without purpose.

Future Hugging Face resources may include:

- a Reachy Mini RCC Space;
- robot interaction datasets;
- motion datasets;
- dance/timeline datasets;
- trained policies;
- perception models;
- a Reachy Mini RCC Collection.

GitHub remains the canonical source repository unless explicitly
changed in a future release policy.

---

## 24. Release Quality Gate

The repository is not ready for public upload until all of the
following are true:

- no real `.env` exists;
- no real credentials are detected;
- no historical developer robot IP exists;
- no developer-machine absolute paths exist;
- no `.venv` or standalone runtime is included;
- no cache/backup/log contamination exists;
- Reachy hotspot logic remains intact;
- repository root documentation exists;
- third-party notices exist;
- License is present;
- tests pass;
- production mode mapping has not been accidentally changed.

---

## 25. Success Criteria

Stage 3 is complete when the repository has a professional public
documentation layer and all documentation accurately describes the
validated Reachy Mini RCC v3.0.0 behavior.

The resulting repository should allow a technically capable developer
to understand:

- what Reachy Mini RCC is;
- what it can currently do;
- how its major subsystems fit together;
- how to configure it safely;
- how to run the source;
- what is intentionally not bundled;
- how to contribute;
- how third-party software is treated;
- where the project is headed.
