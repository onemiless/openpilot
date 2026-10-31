# Generated from the hash-pinned, hardware-exercised SPI engine.
import time

CFG = (0xC8AD, 0xC8AE, 0xC8AF, 0xC8AA, 0xC8AC, 0xC8A1, 0xC8A2, 0xC8AB, 0xC8A3, 0xC8A4, 0xC8A6, 0xCA81)

READ_OPS = {3, 5, 0x35, 0x15, 0x9F, 0x4B}

WRITE_OPS = {4, 6, 0x50, 1, 2, 0x20}

class SPI:
  def __init__(self, transport):
    self.transport = transport
    self.enabled = False
    self.owned_wel = False
    self.saved = {}
    self.dirty_protection = False
    self.trigger_attempted = None
    self.persistent_attempts = []
    self.allowed_sectors = set()
    self.touched = False
    self.original_status = 0x1C

  def rd(self, address, length=1):
    registers = set(CFG) | {0xC8A9, 0xC8B6, 0xC8B8, 0xC8D6, 0xB450}
    if not ((address in registers and length == 1) or (0x7000 <= address and 1 <= length <= 255 and address + length <= 0x8000)):
      raise ValueError("E4 address outside install allowlist")
    return b"".join(self.transport.control(False, address+i, length=min(64,length-i)) for i in range(0,length,64))

  def wr(self, address, value):
    if not 0 <= value <= 255 or address not in set(CFG) | {0xC8A9, 0xCC33, 0xC805} and not 0x7000 <= address < 0x7080:
      raise ValueError("E5 address outside install allowlist")
    self.touched = True
    self.transport.control(True, address, value)

  def idle(self, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if not self.rd(0xC8A9)[0] & 1 and not self.rd(0xC8B6)[0] & 0x80 and not self.rd(0xC8B8)[0] & 1:
        self.trigger_attempted = None
        return
      time.sleep(0.001)
    raise RuntimeError("SPI engine unresolved; no new transaction/retry")

  def txn(self, op, address=0, length=0, mode=0):
    if op not in READ_OPS | WRITE_OPS or op in WRITE_OPS and not self.enabled:
      raise RuntimeError("SPI operation not authorized")
    if op == 3 and not (0 <= address < 0x40000 and 1 <= length <= 4096 and address + length <= 0x40000):
      raise ValueError("invalid Flash read span")
    if op in (2, 0x20) and (
      address // 4096 not in self.allowed_sectors
      or (op == 0x20 and (address % 4096 or length or mode))
      or (op == 2 and (address % 128 or length != 128 or mode != 1))
    ):
      raise ValueError("erase/program outside reviewed sector/page geometry")
    if op == 1 and (mode != 1 or length != 1):
      raise ValueError("invalid volatile protection write")
    if self.rd(0xC8D6)[0] & 8:
      raise RuntimeError("SPI DMA error; refuse transaction")
    self.idle()
    fields = (
      (0xC8AD, mode),
      (0xC8AE, 0),
      (0xC8AF, 0),
      (0xC8AA, op),
      (0xC8AC, 7 if op in (2, 3, 0x20) else 4),
      (0xC8A1, address & 255),
      (0xC8A2, address >> 8 & 255),
      (0xC8AB, address >> 16 & 255),
      (0xC8A3, length >> 8),
      (0xC8A4, length & 255),
    )
    for reg, value in fields:
      self.wr(reg, value)
      if self.rd(reg)[0] != value:
        raise RuntimeError("SPI setup readback mismatch; no trigger")
    if op in (1, 2, 0x20):
      self.persistent_attempts.append((op, address))
    if op == 6:
      self.owned_wel = True
    self.trigger_attempted = op
    self.wr(0xC8A9, 1)  # no automatic retry even if ACK is lost
    self.idle()
    if self.rd(0xC8D6)[0] & 8:
      raise RuntimeError("SPI DMA error after trigger")
    for _ in range(4):
      self.wr(0xC8AD, 0)
    if op in READ_OPS:
      return b"".join(self.rd(0x7000 + i, min(255, length - i)) for i in range(0, length, 255))
    return b""

  def statuses(self):
    return bytes(self.txn(op, length=1)[0] for op in (5, 0x35, 0x15))

  def wait_wip(self):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
      value = self.txn(5, length=1)[0]
      if not value & 1:
        if not value & 2:
          self.owned_wel = False
        return value
      time.sleep(0.002)
    raise RuntimeError("Flash WIP unresolved; do not resend writes")

  def read(self, address=0, length=0x40000):
    blocks = []
    for i in range(0, length, 4096):
      data = self.txn(3, address+i, min(4096,length-i))
      # Independent SPI transaction avoids accepting the measured first-byte=last-byte receive fault.
      if data[:1] != self.txn(3,address+i,1):
        raise RuntimeError(f"independent first-byte check failed at {address+i:#x}; no read retry")
      blocks.append(data)
    return b"".join(blocks)

  def uid(self):
    return self.txn(0x4B, length=20)[4:].hex()

  def snapshot(self):
    self.idle()
    self.saved = {r: self.rd(r)[0] for r in CFG}
    if self.saved[0xC8AD] or self.saved[0xC8A6] != 4:
      raise RuntimeError("unexpected live SPI mode/divider")

  def buffer(self, data):
    if not 1 <= len(data) <= 128:
      raise ValueError("invalid TX buffer size")
    for i, value in enumerate(data):
      self.wr(0x7000 + i, value)
    if self.rd(0x7000, len(data)) != data:
      raise RuntimeError("CPU page buffer readback failed; no Flash program trigger")

  def protection(self, value):
    if self.wait_wip() & 2:
      raise RuntimeError("WEL must be clear before volatile WRSR")
    self.buffer(bytes([value]))
    self.txn(0x50)
    self.txn(1, length=1, mode=1)  # never 06->01
    if self.wait_wip() != value:
      raise RuntimeError("volatile protection readback failed")

  def unlock(self, order):
    self.enabled = True
    self.allowed_sectors = set(order)
    self.wr(0xCC33, 4)
    self.wr(0xCA81, self.rd(0xCA81)[0] | 1)
    self.wr(0xC805, 2)
    self.wr(0xC8A6, 4)
    self.dirty_protection = True  # set before an ambiguous status operation
    self.protection(0)
    if self.statuses() != bytes.fromhex("000020"):
      raise RuntimeError("unexpected unlocked status profile")

  def wren(self):
    if self.wait_wip() != 0:
      raise RuntimeError("unexpected status before WREN")
    self.txn(6)
    if self.txn(5, length=1)[0] != 2:
      raise RuntimeError("WEL did not set")

  def erase(self, address):
    self.wren()
    self.txn(0x20, address)
    if self.wait_wip() != 0 or self.read(address, 4096) != b"\xff" * 4096:
      raise RuntimeError("erase readback failed")

  def program(self, address, data):
    self.transport.offroad()
    self.wren()
    self.buffer(data)  # all status reads are BEFORE loading the page
    self.txn(2, address, 128, 1)
    if self.wait_wip() != 0 or self.read(address, 128) != data:
      raise RuntimeError("page readback failed; no blind retry")

  def cleanup(self):
    if not self.touched:
      return
    self.idle(timeout=12)
    if self.enabled:
      status = self.wait_wip()
      if status & 2:
        if not self.owned_wel:
          raise RuntimeError("unknown WEL ownership; cannot restore")
        self.txn(4)
        if self.wait_wip() & 2:
          raise RuntimeError("WRDI failed")
    if self.dirty_protection:
      if self.statuses()[0] != self.original_status:
        self.protection(self.original_status)
      if self.statuses() != bytes([self.original_status,0,0x20]):
        raise RuntimeError("protection restoration not established")
      self.dirty_protection = False
    for reg in reversed(CFG):
      if reg in self.saved and self.rd(reg)[0] != self.saved[reg]:
        self.wr(reg, self.saved[reg])
    if any(self.rd(r)[0] != v for r, v in self.saved.items()):
      raise RuntimeError("volatile register restoration mismatch")
