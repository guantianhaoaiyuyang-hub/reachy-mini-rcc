# Reachy Mini RCC Public Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the public-facing documentation layer required for the first Reachy Mini RCC v3.0.0 open-source source release.

**Architecture:** The repository keeps production code unchanged and adds a documentation layer at the repository root. README acts as the primary project entry point, while security, contribution, licensing and third-party dependency responsibilities are separated into dedicated files.

**Tech Stack:** Markdown, Apache License 2.0, Git/GitHub-oriented repository conventions.

**Spec:** `docs/superpowers/specs/2026-08-28-reachy-mini-rcc-opensource-release-design.md`

## Global Constraints

- Open-source workspace: `F:\ReachyMini\OpenSource\ReachyMini_RCC_v3.0.0`
- Author: Neil Guan
- Copyright: Copyright 2026 Neil Guan
- License for original project source: Apache License 2.0
- Do not modify the stable development project.
- Do not publish real credentials.
- Do not publish `.env`.
- Do not publish bundled runtime or virtual environments.
- Preserve the six validated RCC production modes.
- Preserve dynamic robot discovery.
- Preserve Reachy Mini hotspot logic using `10.42.0.1`.
- Preserve Network Preflight behavior.
- Preserve the validated V3.5 launcher path.
- Preserve the Pillow-based VISION preview fix.
- Third-party software remains governed by upstream licenses.

---

### Task 1: Create repository README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: current validated Reachy Mini RCC v3.0.0 behavior
- Produces: primary public repository entry point

- [ ] Describe the project and supported modes.
- [ ] Document architecture and repository structure.
- [ ] Document source-development setup.
- [ ] Explain credentials and security.
- [ ] Explain robot discovery and hotspot support.
- [ ] Document limitations and excluded assets.
- [ ] Add author, license and project status information.
- [ ] Verify README contains no real credentials or local developer paths.

### Task 2: Add Apache-2.0 license

**Files:**
- Create: `LICENSE`

**Interfaces:**
- Consumes: copyright ownership decision
- Produces: repository software license

- [ ] Add the unmodified Apache License 2.0 license text.
- [ ] Keep project copyright attribution in repository documentation.
- [ ] Verify the license terms are not altered.

### Task 3: Create security policy

**Files:**
- Create: `SECURITY.md`

**Interfaces:**
- Consumes: project credential architecture
- Produces: public vulnerability-reporting and secret-handling policy

- [ ] Explain what must never be published.
- [ ] Explain credential rotation after accidental exposure.
- [ ] Explain safe issue/log sharing.
- [ ] Document Windows Credential Manager usage.

### Task 4: Create contribution guide

**Files:**
- Create: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: validated runtime contracts and release constraints
- Produces: contribution and regression-testing rules

- [ ] Document environment setup.
- [ ] Document branch/change workflow.
- [ ] Require behavioral regression testing.
- [ ] Protect robot discovery, V3.5, VISION and Network Preflight contracts.
- [ ] Prohibit secrets and copyrighted assets.

### Task 5: Create third-party notices

**Files:**
- Create: `THIRD_PARTY_NOTICES.md`

**Interfaces:**
- Consumes: project dependency inventory
- Produces: third-party licensing disclosure

- [ ] List important external dependencies.
- [ ] Avoid claiming all dependencies use Apache-2.0.
- [ ] Require upstream-license review for redistribution.
- [ ] Explain model, audio and runtime redistribution boundaries.

### Task 6: Verify documentation release gate

**Files:**
- Verify: `README.md`
- Verify: `LICENSE`
- Verify: `SECURITY.md`
- Verify: `CONTRIBUTING.md`
- Verify: `THIRD_PARTY_NOTICES.md`

**Interfaces:**
- Consumes: Tasks 1-5
- Produces: Stage 3 documentation checkpoint

- [ ] Confirm all files exist.
- [ ] Search documentation for real `.env` references that imply committed secrets.
- [ ] Search for historical development robot IP addresses.
- [ ] Search for known local development paths.
- [ ] Confirm project attribution is present.
- [ ] Confirm Apache License text is present.
