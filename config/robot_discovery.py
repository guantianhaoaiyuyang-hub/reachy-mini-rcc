from __future__ import annotations

import ipaddress
import json
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PORT = 8000
STATE_FILE = Path(__file__).resolve().parent / "robot_state.json"

KNOWN_HOSTS = [
    "reachy-mini.local",
]

BAD_ADAPTER_WORDS = (
    "okz", "tun", "tap", "wsl", "hyper-v", "vpn",
    "tailscale", "zerotier", "docker", "vmware",
    "virtualbox", "loopback",
)

def _load_saved_ip() -> str | None:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    for key in ("ip", "host", "robot_ip", "last_ip"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

def _save_ip(host: str) -> None:
    try:
        data = {}
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["ip"] = host
        data["host"] = host
        data["robot_ip"] = host
        STATE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

def _http_json(host: str, path: str, timeout: float = 0.8):
    url = f"http://{host}:{PORT}{path}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8", errors="replace"))

def _is_reachy(host: str, timeout: float = 0.8) -> bool:
    try:
        payload = _http_json(host, "/api/daemon/status", timeout=timeout)
    except Exception:
        return False

    if not isinstance(payload, dict):
        return False

    robot_name = str(payload.get("robot_name", "")).lower()
    dtype = str(payload.get("type", "")).lower()
    version = str(payload.get("version", "")).strip()

    if "reachy" in robot_name:
        return True
    if dtype == "daemon_status" and version:
        return True
    return False

def _powershell_adapters() -> list[dict]:
    ps = r"""
$items = Get-NetIPConfiguration |
  Where-Object {
    $_.NetAdapter.Status -eq 'Up' -and $_.IPv4Address
  } |
  ForEach-Object {
    [PSCustomObject]@{
      Alias = $_.InterfaceAlias
      IPv4 = $_.IPv4Address.IPAddress
      Gateway = if ($_.IPv4DefaultGateway) {
        $_.IPv4DefaultGateway.NextHop
      } else { $null }
    }
  }
$items | ConvertTo-Json -Compress
"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=flags,
        )
        if cp.returncode != 0 or not cp.stdout.strip():
            return []
        data = json.loads(cp.stdout)
        if isinstance(data, dict):
            data = [data]
        return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []

def _candidate_networks() -> list[ipaddress.IPv4Network]:
    rows = _powershell_adapters()
    preferred = []
    fallback = []

    for row in rows:
        alias = str(row.get("Alias", ""))
        ip_text = str(row.get("IPv4", "")).strip()
        low = alias.lower()

        if not ip_text or any(word in low for word in BAD_ADAPTER_WORDS):
            continue

        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue

        if not isinstance(ip, ipaddress.IPv4Address):
            continue
        if not ip.is_private:
            continue
        if ip in ipaddress.ip_network("198.18.0.0/15"):
            continue

        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        entry = (network, alias, ip_text)

        if any(k in low for k in ("wlan", "wi-fi", "wifi", "wireless", "鏃犵嚎")):
            preferred.append(entry)
        else:
            fallback.append(entry)

    ordered = preferred + fallback
    seen = set()
    result = []

    for network, alias, ip_text in ordered:
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        print(f"[RCC] LAN adapter: {alias} / {ip_text} -> {network}")
        result.append(network)

    return result

def _scan_network(network: ipaddress.IPv4Network) -> str | None:
    hosts = [str(ip) for ip in network.hosts()]
    print(f"[RCC] Scanning {network} for Reachy Mini API...")

    def probe(host: str):
        return host if _is_reachy(host, timeout=0.28) else None

    with ThreadPoolExecutor(max_workers=48) as pool:
        futures = {pool.submit(probe, host): host for host in hosts}
        for fut in as_completed(futures):
            try:
                found = fut.result()
            except Exception:
                found = None
            if found:
                for f in futures:
                    f.cancel()
                return found
    return None

def discover_robot() -> str:
    print("[RCC] Searching for Reachy Mini...")

    candidates = []
    saved = _load_saved_ip()
    if saved:
        candidates.append(saved)
    candidates.extend(KNOWN_HOSTS)

    unique = []
    for host in candidates:
        if host and host not in unique:
            unique.append(host)

    print("[RCC] Trying saved/known robot addresses...")
    for host in unique:
        print(f"[RCC]   -> {host}")
        if _is_reachy(host, timeout=0.7):
            print(f"[RCC] Reachy Mini found: {host}")
            _save_ip(host)
            return host

    networks = _candidate_networks()
    if not networks:
        raise RuntimeError(
            "Reachy Mini was not found. No usable physical LAN/Wi-Fi adapter "
            "was detected. Check that the PC and robot are on the same Wi-Fi."
        )

    for network in networks:
        found = _scan_network(network)
        if found:
            print(f"[RCC] Reachy Mini found: {found}")
            _save_ip(found)
            return found

    raise RuntimeError(
        "Reachy Mini was not found on the current physical LAN/Wi-Fi. "
        "Check that the robot is powered on, its API/daemon is running, "
        "and it is connected to the same Wi-Fi as this PC."
    )

if __name__ == "__main__":
    host = discover_robot()
    print()
    print("=" * 40)
    print(" Reachy Mini detected")
    print("=" * 40)
    print(f" HOST : {host}")
    print(f" API  : http://{host}:{PORT}")
