# Networking

## Overview

Reachy Mini RCC is designed to avoid hardcoded development-machine robot IP addresses.

Production modes rely on dynamic robot discovery and daemon validation.

## Discovery Strategy

The project may attempt:

```text
cached valid robot state
        鈫?Reachy Mini hostname / mDNS
        鈫?physical private IPv4 subnet discovery
        鈫?daemon status validation
```

A candidate is only accepted after validation against the Reachy Mini daemon API.

## Transient State

`config/robot_state.json` stores transient connection state.

For public releases it should contain:

```json
{}
```

and must not contain a developer-specific robot address.

## Reachy Mini Hotspot

The address:

```text
10.42.0.1
```

is intentional for Reachy Mini hotspot operation.

Do not remove it solely because it is a fixed IP.

## VPN / TUN Adapters

On Windows, proxy or VPN software may create virtual adapters.

Robot discovery should prefer physical private IPv4 interfaces and avoid unrelated virtual/TUN interfaces.

## Network Preflight

RCC validates networking before mode launch.

Typical checks:

```text
robot discovery
daemon API reachability
active robot address
daemon WLAN state
media connectivity
stale-state detection
recovery
revalidation
```

## Stale WLAN State

A known class of failure occurs when Reachy Mini changes Wi-Fi networks but the daemon still reports an old WLAN address.

The RCC preflight logic detects and recovers from this state before launching robot modes.

## API Port

Reachy Mini daemon/API communication is expected on port:

```text
8000
```

## Diagnostic Guidance

When debugging network issues, record:

- current PC network interface;
- whether robot and PC are on the same network;
- whether Reachy Mini hotspot mode is active;
- daemon/API reachability;
- whether a VPN/TUN adapter is present;
- Network Preflight output.

Do not publish unnecessary private network details in public issues.