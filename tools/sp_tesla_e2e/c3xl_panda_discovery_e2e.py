#!/usr/bin/env python3
"""Real C3XL discovery: fail if SPI is absent, excluded, or cannot open.
Run offroad with pandad stopped; no reset or firmware write is performed.
"""
import argparse
import json
from pathlib import Path
import subprocess

from panda import Panda
from openpilot.common.hardware import HARDWARE
from openpilot.common.params import Params
from openpilot.sunnypilot.hardware.panda_startup import PandaStartupIO
from openpilot.sunnypilot.hardware.profile import HardwareProfile, get_hardware_profile

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert get_hardware_profile() == HardwareProfile.C3XL
assert Params().get_bool('IsOffroad') and not Params().get_bool('IsEngaged')
assert subprocess.run(['pgrep', '-f', '^./pandad( |$)'], stdout=subprocess.DEVNULL).returncode != 0
spi = Panda.spi_list()
discovered = PandaStartupIO().list_internal()
result = {'passed': bool(spi) and discovered == spi, 'device_type': HARDWARE.get_device_type(),
          'profile': get_hardware_profile().value, 'spi': spi, 'startup_discovered': discovered,
          'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
          'scope': 'real offroad SPI enumeration through production startup IO; no firmware write'}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
raise SystemExit(not result['passed'])
