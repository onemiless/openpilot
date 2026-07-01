#!/usr/bin/env python3
import argparse
import filecmp
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


BASE = Path("/data/mihomo")
BIN = BASE / "mihomo"
CONFIG = BASE / "config.yaml"
LOG = BASE / "mihomo.log"
PID = BASE / "mihomo.pid"
SUBSCRIPTION_URL = BASE / "subscription_url"
USER_AGENT = "clash-verge/v2.0.0"
PROXY_URL = "http://127.0.0.1:7890"
BUNDLED_DIR = Path(__file__).resolve().parents[1] / "third_party" / "mihomo" / "linux-arm64"
BUNDLED_FILES = ("mihomo", "Country.mmdb", "geoip.dat", "geoip.metadb", "geosite.dat")


def _read_pid() -> int | None:
  try:
    return int(PID.read_text().strip())
  except (OSError, ValueError):
    return None


def _is_running(pid: int | None = None) -> bool:
  if pid is None:
    pid = _read_pid()
  if pid is None:
    return False
  try:
    os.kill(pid, 0)
    return True
  except OSError:
    return False


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
  return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _print_result(result: subprocess.CompletedProcess) -> int:
  output = (result.stdout or "").strip()
  error = (result.stderr or "").strip()
  if output:
    print(output)
  if error:
    print(error, file=sys.stderr)
  return result.returncode


def _copy_if_changed(src: Path, dst: Path) -> bool:
  if not src.exists():
    print(f"bundled file not found: {src}", file=sys.stderr)
    raise FileNotFoundError(src)

  if dst.exists() and filecmp.cmp(src, dst, shallow=False):
    return False

  tmp = dst.with_suffix(dst.suffix + ".tmp")
  shutil.copy2(src, tmp)
  tmp.replace(dst)
  return True


def install(_args: argparse.Namespace) -> int:
  if not BUNDLED_DIR.exists():
    print(f"bundled mihomo directory not found: {BUNDLED_DIR}", file=sys.stderr)
    return 1

  BASE.mkdir(parents=True, exist_ok=True)
  installed = []
  try:
    for name in BUNDLED_FILES:
      if _copy_if_changed(BUNDLED_DIR / name, BASE / name):
        installed.append(name)
  except OSError as e:
    print(str(e), file=sys.stderr)
    return 1

  BIN.chmod(0o755)
  print("installed: " + ", ".join(installed) if installed else "already installed")
  return 0


def status(_args: argparse.Namespace) -> int:
  if _is_running():
    print("running")
  else:
    print("stopped")
  return 0


def start(_args: argparse.Namespace) -> int:
  if _is_running():
    print("mihomo already running")
    return 0
  install_result = install(_args)
  if install_result != 0:
    return install_result
  if not BIN.exists():
    print(f"mihomo binary not found: {BIN}", file=sys.stderr)
    return 1
  if not CONFIG.exists():
    print(f"config not found: {CONFIG}", file=sys.stderr)
    return 1

  BASE.mkdir(parents=True, exist_ok=True)
  log_file = LOG.open("ab")
  proc = subprocess.Popen([str(BIN), "-d", str(BASE)], stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
  PID.write_text(f"{proc.pid}\n")
  print(f"mihomo started, pid={proc.pid}")
  return 0


def stop(_args: argparse.Namespace) -> int:
  pid = _read_pid()
  if pid is not None and _is_running(pid):
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
      if not _is_running(pid):
        PID.unlink(missing_ok=True)
        print("mihomo stopped")
        return 0
      time.sleep(0.25)
    os.kill(pid, signal.SIGKILL)
    PID.unlink(missing_ok=True)
    print("mihomo killed")
    return 0

  result = _run(["pkill", "-f", f"{BIN} -d {BASE}"], timeout=5)
  PID.unlink(missing_ok=True)
  if result.returncode in (0, 1):
    print("mihomo stopped" if result.returncode == 0 else "mihomo is not running")
    return 0
  return _print_result(result)


def set_url(args: argparse.Namespace) -> int:
  return _save_url(args.url)


def set_url_stdin(_args: argparse.Namespace) -> int:
  return _save_url(sys.stdin.read())


def _save_url(url: str) -> int:
  BASE.mkdir(parents=True, exist_ok=True)
  SUBSCRIPTION_URL.write_text(url.strip() + "\n")
  os.chmod(SUBSCRIPTION_URL, 0o600)
  print(f"subscription URL saved: {SUBSCRIPTION_URL}")
  return 0


def url_status(_args: argparse.Namespace) -> int:
  if SUBSCRIPTION_URL.exists() and SUBSCRIPTION_URL.read_text().strip():
    print("saved")
  else:
    print("missing")
  return 0


def _sanitize_config(path: Path) -> None:
  lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
  out = []
  saw_allow_lan = False
  saw_bind_address = False
  for line in lines:
    if line.startswith("allow-lan:"):
      out.append("allow-lan: false")
      saw_allow_lan = True
    elif line.startswith("bind-address:"):
      out.append("bind-address: '127.0.0.1'")
      saw_bind_address = True
    else:
      out.append(line)

  if not saw_allow_lan:
    out.insert(1, "allow-lan: false")
  if not saw_bind_address:
    out.insert(2, "bind-address: '127.0.0.1'")
  path.write_text("\n".join(out) + "\n", encoding="utf-8")


def update(_args: argparse.Namespace) -> int:
  install_result = install(_args)
  if install_result != 0:
    return install_result

  if not SUBSCRIPTION_URL.exists():
    print(f"subscription URL not found: {SUBSCRIPTION_URL}", file=sys.stderr)
    return 1

  url = SUBSCRIPTION_URL.read_text().strip()
  if not url:
    print(f"subscription URL is empty: {SUBSCRIPTION_URL}", file=sys.stderr)
    return 1

  BASE.mkdir(parents=True, exist_ok=True)
  tmp = BASE / "config.yaml.tmp"
  result = _run(["curl", "-L", "--fail", "--connect-timeout", "20", "-A", USER_AGENT, url, "-o", str(tmp)], timeout=90)
  if result.returncode != 0:
    tmp.unlink(missing_ok=True)
    return _print_result(result)

  content = tmp.read_text(encoding="utf-8", errors="replace")
  if not any(key in content for key in ("mixed-port:", "proxies:", "proxy-providers:")):
    tmp.unlink(missing_ok=True)
    print("downloaded file does not look like a mihomo config", file=sys.stderr)
    return 1

  _sanitize_config(tmp)
  tmp.replace(CONFIG)
  print(f"config updated: {CONFIG}")
  return 0


def test_github(_args: argparse.Namespace) -> int:
  install_result = install(_args)
  if install_result != 0:
    return install_result

  result = _run(["curl", "-I", "--connect-timeout", "15", "-x", PROXY_URL, "https://github.com"], timeout=30)
  if result.returncode != 0:
    return _print_result(result)
  first_lines = "\n".join((result.stdout or "").splitlines()[:4])
  print(first_lines)
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Manage /data/mihomo for manual GitHub proxy access.")
  subparsers = parser.add_subparsers(dest="command", required=True)

  commands = {
    "status": status,
    "url-status": url_status,
    "install": install,
    "start": start,
    "stop": stop,
    "update": update,
    "test": test_github,
  }
  for name, func in commands.items():
    subparser = subparsers.add_parser(name)
    subparser.set_defaults(func=func)

  set_url_parser = subparsers.add_parser("set-url")
  set_url_parser.add_argument("url")
  set_url_parser.set_defaults(func=set_url)

  set_url_stdin_parser = subparsers.add_parser("set-url-stdin")
  set_url_stdin_parser.set_defaults(func=set_url_stdin)

  args = parser.parse_args()
  return args.func(args)


if __name__ == "__main__":
  raise SystemExit(main())
