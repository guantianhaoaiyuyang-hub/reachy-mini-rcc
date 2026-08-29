# VISION

## Overview

VISION mode provides MediaPipe-based visual tracking for Reachy Mini RCC.

The current v3.0.0 implementation has been validated both as standalone VISION and as part of V3.5 + VISION.

## Embedded Preview Stability

A critical Windows packaging issue was traced to repeated OpenCV JPEG encoding in the embedded preview pipeline.

The validated implementation uses Pillow-based JPEG generation for preview transport.

This behavior must not be reverted casually.

## Validated Modes

```text
VISION
V3.5 + VISION
```

Both should be regression-tested when changing shared vision code.

## Expected Data Flow

```text
camera/media source
      鈫?frame acquisition
      鈫?MediaPipe processing
      鈫?tracking result
      鈫?robot response
      鈫?embedded preview
```

## Common Failure Areas

- media stream unavailable;
- robot network address stale;
- camera/media negotiation failure;
- native media dependency issue;
- preview encoding instability;
- VPN/TUN interference;
- mismatched packaged runtime dependency.

## Regression Rule

Any change affecting frame acquisition, MediaPipe processing, preview transport or network media access should be tested in:

```text
VISION
V3.5 + VISION
```

and preferably on the packaged Windows runtime as well as the source environment.