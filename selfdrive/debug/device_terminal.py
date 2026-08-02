"""Opt-in, offroad-only command runner for the local device settings web UI."""
import hmac
import os
import secrets
import signal
import subprocess
from pathlib import Path

from openpilot.common.params import Params


BASE_DIR = Path(__file__).resolve().parents[2]
MAX_COMMAND_LENGTH = 4096
MAX_OUTPUT_LENGTH = 64 * 1024
COMMAND_TIMEOUT_S = 20


def terminal_status(params: Params | None = None) -> dict[str, bool]:
  params = params or Params()
  return {"enabled": params.get_bool("WebTerminalEnabled"), "onroad": params.get_bool("IsOnroad")}


def get_or_create_token(params: Params | None = None) -> str:
  params = params or Params()
  token = params.get("WebTerminalToken")
  if not token:
    token = secrets.token_urlsafe(32)
    params.put("WebTerminalToken", token, block=True)
  return token


def _authorize(token: str | None, params: Params) -> None:
  if not params.get_bool("WebTerminalEnabled"):
    raise PermissionError("网页终端未启用")
  expected = get_or_create_token(params)
  if not token or not hmac.compare_digest(token, expected):
    raise PermissionError("终端令牌无效")
  if params.get_bool("IsOnroad"):
    raise PermissionError("行驶中禁止运行网页终端命令")


def run_command(command: str, token: str | None, params: Params | None = None) -> dict[str, object]:
  params = params or Params()
  _authorize(token, params)
  if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_LENGTH:
    raise ValueError("命令必须为 1 到 4096 个字符")

  proc = subprocess.Popen(
    command,
    shell=True,
    cwd=BASE_DIR,
    env={**os.environ, "PYTHONUNBUFFERED": "1"},
    start_new_session=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
  )
  timed_out = False
  try:
    output, _ = proc.communicate(timeout=COMMAND_TIMEOUT_S)
  except subprocess.TimeoutExpired:
    timed_out = True
    os.killpg(proc.pid, signal.SIGTERM)
    try:
      output, _ = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
      os.killpg(proc.pid, signal.SIGKILL)
      output, _ = proc.communicate()
  output = output[-MAX_OUTPUT_LENGTH:]
  return {"exit_code": proc.returncode, "timed_out": timed_out, "output": output}
