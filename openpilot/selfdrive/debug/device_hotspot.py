"""Control the local Wi-Fi hotspot and its Tesla-browser access address."""
import subprocess
from collections.abc import Callable


HOTSPOT_CONNECTION = "Hotspot"
LOCAL_HOTSPOT_URL = "http://192.168.43.1:8088"
TESLA_ACCESS_ADDRESS = "99.99.99.99"
TESLA_ACCESS_PREFIX = 32
TESLA_ACCESS_INTERFACE = "lo"
TESLA_HOTSPOT_URL = f"http://{TESLA_ACCESS_ADDRESS}:8088"
# Preserve the original API field for existing non-Tesla clients.
HOTSPOT_URL = LOCAL_HOTSPOT_URL


def _nmcli(*args: str, runner: Callable = subprocess.run) -> subprocess.CompletedProcess:
  return runner(["sudo", "-n", "nmcli", *args], check=False, capture_output=True, text=True)


def _ip(*args: str, runner: Callable = subprocess.run, privileged: bool = False) -> subprocess.CompletedProcess:
  command = ["ip", *args]
  if privileged:
    command = ["sudo", "-n", *command]
  return runner(command, check=False, capture_output=True, text=True)


def tesla_address_ready(runner: Callable = subprocess.run) -> bool:
  result = _ip("-o", "-4", "address", "show", "dev", TESLA_ACCESS_INTERFACE, runner=runner)
  if result.returncode != 0:
    return False
  expected = f"{TESLA_ACCESS_ADDRESS}/{TESLA_ACCESS_PREFIX}"
  return any(expected in line.split() for line in result.stdout.splitlines())


def set_tesla_address_enabled(enabled: bool, runner: Callable = subprocess.run) -> bool:
  """Idempotently expose or remove the public-shaped local Tesla address."""
  current = tesla_address_ready(runner)
  if current == enabled:
    return current

  operation = "replace" if enabled else "delete"
  result = _ip("address", operation, f"{TESLA_ACCESS_ADDRESS}/{TESLA_ACCESS_PREFIX}",
               "dev", TESLA_ACCESS_INTERFACE, runner=runner, privileged=True)
  if result.returncode != 0:
    message = (result.stderr or result.stdout or f"ip address {operation} failed").strip()
    raise RuntimeError(message)
  return enabled


def hotspot_status(runner: Callable = subprocess.run) -> dict:
  """Return the state without exposing the hotspot passphrase."""
  result = _nmcli("-t", "-f", "NAME,DEVICE", "connection", "show", "--active", runner=runner)
  active = any(line.split(":", 1)[0] == HOTSPOT_CONNECTION for line in result.stdout.splitlines())
  return {
    "available": result.returncode == 0,
    "active": active,
    "connection": HOTSPOT_CONNECTION,
    "url": HOTSPOT_URL,
    "tesla_url": TESLA_HOTSPOT_URL,
    "tesla_address_ready": tesla_address_ready(runner),
  }


def set_hotspot_enabled(enabled: bool, runner: Callable = subprocess.run) -> dict:
  command = ("connection", "up", "id", HOTSPOT_CONNECTION) if enabled else ("connection", "down", "id", HOTSPOT_CONNECTION)
  result = _nmcli(*command, runner=runner)
  if result.returncode != 0:
    message = (result.stderr or result.stdout or "NetworkManager 命令失败").strip()
    raise RuntimeError(message)
  return hotspot_status(runner=runner)
