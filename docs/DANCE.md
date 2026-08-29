# DANCE

## Overview

DANCE mode provides robot dance and timeline playback for Reachy Mini RCC.

The open-source release separates movement logic from copyrighted audio assets.

## Public Repository Policy

Dance code, choreography timing logic and timeline definitions may be open-sourced.

Commercial/copyrighted music must not be included unless redistribution rights are known.

## Timeline Files

Dance timeline/config files may use JSON-based data.

The project has previously encountered UTF-8 BOM issues in dance JSON files.

When compatibility matters, readers may need to support UTF-8 with BOM (`utf-8-sig`).

## Runtime Expectations

Dance playback may coordinate:

- head movement;
- body rotation;
- antennas;
- timing;
- audio synchronization where available.

## Safety

Use conservative ranges and keep sufficient physical clearance around the robot.

Always retain a way to stop the current mode.

## Regression Guidance

When modifying DANCE behavior, verify:

- timeline loads;
- encoding is handled;
- motion remains within intended limits;
- stop behavior still works;
- playback remains synchronized enough for the intended choreography.