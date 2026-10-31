#!/usr/bin/env python3
"""C3 Linux USB R2 full-flash utility. No UID, serial or source-firmware binding."""
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from spi_core import SPI

SIZE = 0x40000
R2_SHA = '6c82e3add05b668f093dbe74282c92405b834989627c7af8201a81ccd23abcde'

def sha(data):
  return hashlib.sha256(data).hexdigest()

def save(path, data):
  if not isinstance(data, bytes):
    data = (json.dumps(data, indent=2, ensure_ascii=False)+'\n').encode()
  temporary=path.with_name(path.name+'.tmp')
  with temporary.open('wb') as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
  os.replace(temporary,path)
  directory=os.open(path.parent,os.O_DIRECTORY)
  try:os.fsync(directory)
  finally:os.close(directory)

class Control(C.Structure):
  _fields_ = [('bm',C.c_uint8),('req',C.c_uint8),('value',C.c_uint16),('index',C.c_uint16),('length',C.c_uint16),('timeout',C.c_uint32),('data',C.c_void_p)]

class Bulk(C.Structure):
  _fields_ = [('ep',C.c_uint),('length',C.c_uint),('timeout',C.c_uint),('data',C.c_void_p)]

class Session:
  def __init__(self, device=None):
    self.selected=device
    self.fd=None
    self.driver=None
    self.claimed=False
    self.tag=0

  def offroad(self):
    # The dedicated launcher never starts driving or vehicle communication processes.
    pass

  def __enter__(self):
    if sys.platform!='linux' or os.geteuid()!=0 or C.sizeof(Control)!=24:
      raise RuntimeError('Run with sudo python3 on C3 Linux')
    self.offroad()
    root=Path('/sys/bus/usb/devices')
    candidates=[]
    for p in root.iterdir():
      if (p/'idVendor').exists() and (p/'idProduct').exists():
        pair=(int((p/'idVendor').read_text(),16),int((p/'idProduct').read_text(),16))
        if pair in ((0x3801,1),(0xadd1,1),(0x174c,0x2463),(0x174c,0x2464)):
          candidates.append(p)
    if self.selected:
      p=self.selected.resolve()
      if p not in [x.resolve() for x in candidates]:
        raise RuntimeError('Selected path is not a supported USB bridge')
    else:
      if len(candidates)!=1:
        raise RuntimeError('Select exactly one dock with --device /sys/bus/usb/devices/<port>; candidates='+str(candidates))
      p=candidates[0]
    self.path=p
    interfaces=sorted(p.glob(p.name+':*'))
    if not interfaces:
      interfaces=sorted(root.glob(p.name+':*'))
    if not interfaces:
      raise RuntimeError('USB interface not found')
    self.interface=interfaces[0]
    if (self.interface/'bInterfaceNumber').read_text().strip()!='00':
      raise RuntimeError('Interface 0 required')
    self.bot=(self.interface/'bInterfaceClass').read_text().strip()=='08' and (self.interface/'bInterfaceProtocol').read_text().strip()=='50'
    node='/dev/bus/usb/%03d/%03d'%(int((p/'busnum').read_text()),int((p/'devnum').read_text()))
    busy=subprocess.run(['fuser',node],capture_output=True,text=True)
    if busy.returncode!=1 or busy.stdout.strip():
      raise RuntimeError('USB device is in use; stop its monitor/GPU process before maintenance')
    try:
      if (self.interface/'driver').exists():
        self.driver=(self.interface/'driver').resolve()
        if self.driver.name!='usb-storage':
          self.driver=None
          raise RuntimeError('Unexpected kernel USB driver')
        (self.driver/'unbind').write_text(self.interface.name)
      self.fd=os.open(node,os.O_RDWR)
      fcntl.ioctl(self.fd,0x8004550f,(0).to_bytes(4,sys.byteorder))
      self.claimed=True
      if self.bot:
        endpoints=[(int((e/'bEndpointAddress').read_text(),16),int((e/'bmAttributes').read_text(),16)) for e in self.interface.glob('ep_*')]
        self.ep_in=next(a for a,t in endpoints if t&3==2 and a&0x80)
        self.ep_out=next(a for a,t in endpoints if t&3==2 and not a&0x80)
      else:
        # R3 requires this volatile maintenance unlock. R2/R4 acknowledge unknown vendor OUT requests.
        self.request(0x40,0xc4,2464,0,0)
      return self
    except BaseException:
      self.__exit__(None,None,None)
      raise

  def request(self,bm,req,value,index,length):
    buf=C.create_string_buffer(max(1,length))
    actual=fcntl.ioctl(self.fd,0xc0185500,Control(bm,req,value,index,length,3000,C.addressof(buf)))
    if actual!=length:
      raise RuntimeError('USB control short transfer; no write retry')
    return buf.raw[:length]

  def bulk(self,ep,data):
    buf=C.create_string_buffer(data,len(data))
    count=fcntl.ioctl(self.fd,0xc0185502,Bulk(ep,len(data),3000,C.addressof(buf)))
    if count!=len(data):
      raise RuntimeError('BOT short transfer; no write retry')
    return buf.raw

  def control(self,write,address,value=0,length=1):
    if not self.bot:
      return self.request(0x40 if write else 0xc0,0xe5 if write else 0xe4,address,value if write else 0,0 if write else length)
    import struct
    n=0 if write else length
    cdb=struct.pack('>BBBHB',0xe5 if write else 0xe4,value if write else length,0x50,address,0)
    self.tag+=1
    self.bulk(self.ep_out,struct.pack('<IIIBBB16s',0x43425355,self.tag,n,0 if write else 0x80,0,6,cdb))
    data=self.bulk(self.ep_in,bytes(n)) if n else b''
    status=struct.unpack('<IIIB',self.bulk(self.ep_in,bytes(13)))
    if status!=(0x53425355,self.tag,0,0):
      raise RuntimeError('BOT status/tag/residue error; no write retry')
    return data

  def __exit__(self,*args):
    try:
      if self.fd is not None:
        try:
          if self.claimed:fcntl.ioctl(self.fd,0x80045510,(0).to_bytes(4,sys.byteorder))
        finally:os.close(self.fd)
    finally:
      if self.driver and self.interface.exists() and not (self.interface/'driver').exists():
        (self.driver/'bind').write_text(self.interface.name)

def execute(spi,out,write=False,restore=None):
  wrapper=(Path(__file__).resolve().parent/'firmware/SP8516-R2.bin').read_bytes()
  if len(wrapper)!=98016 or sha(wrapper)!=R2_SHA:
    raise ValueError('Bundled R2 firmware is damaged')
  if restore is not None and len(restore)!=SIZE:
    raise ValueError('Restore image must be a complete 256KiB file')
  result={'status':'STARTED','write_requested':write,'completed_sectors':[],'controller_restored':False,'protection_restored':False}
  extra={}
  def event(message,**fields):
    row={'time':time.time(),'message':message,**fields}
    with (out/'events.jsonl').open('ab') as f:
      f.write((json.dumps(row,ensure_ascii=False)+'\n').encode());f.flush();os.fsync(f.fileno())
    print(message,fields,flush=True)
  try:
    spi.transport.offroad();spi.snapshot()
    extra={a:spi.transport.control(False,a)[0] for a in (0xcc33,0xc805)}
    result['initial_registers']={hex(k):v for k,v in spi.saved.items()}
    result['initial_registers'].update({hex(k):v for k,v in extra.items()})
    spi.wr(0xcc33,4);spi.wr(0xca81,spi.rd(0xca81)[0]|1);spi.wr(0xc805,2);spi.wr(0xc8a6,4)
    ids=[spi.txn(0x9f,length=3).hex() for _ in range(3)];result['jedec_reads']=ids
    event('JEDEC three reads',values=ids)
    if ids!=['854012']*3:
      raise RuntimeError('JEDEC reads do not all match 854012; no Flash erase/program attempted')
    uids=[spi.uid() for _ in range(3)];result['uid_reads']=uids
    if len(set(uids))!=1:
      raise RuntimeError('UID reads are unstable')
    status=spi.statuses();result['status_before']=status.hex()
    if status not in (bytes.fromhex('1c0020'),bytes.fromhex('000020')):
      raise RuntimeError('Unsupported Flash status register semantics')
    spi.original_status=status[0]
    source=None
    for i in range(3):
      event('Full backup',read=i+1,total=3)
      data=spi.read();save(out/f'before-full-{i}.bin',data)
      if source is not None and data!=source:
        raise RuntimeError('Full backups differ; no Flash erase/program attempted')
      source=data
    target=restore if restore is not None else source[:256]+wrapper+source[0x17fe0:]
    save(out/'target-full.bin',target)
    result.update(source_sha256=sha(source),target_sha256=sha(target),firmware_sha256=R2_SHA,configuration_preserved=target[:256]==source[:256],tail_and_image1_preserved=target[0x17fe0:]==source[0x17fe0:])
    result['status']='BACKUP_AND_TARGET_READY_NO_FLASH_WRITES'
    save(out/'result.json',result)
    if write:
      order=list(range(1,64))+[0];result['write_order']=order
      event('Unlock volatile protection; full write follows',sectors=64)
      spi.unlock(order)
      for index,sector in enumerate(order):
        spi.transport.offroad();address=sector*4096;wanted=target[address:address+4096]
        event('ERASE_INTENT',sector=sector,completed=index,total=64);spi.erase(address)
        for offset in range(0,4096,128):
          page=wanted[offset:offset+128]
          if page!=b'\xff'*128:
            event('PROGRAM_INTENT',address=hex(address+offset),page=offset//128+1,total_pages=32)
            spi.program(address+offset,page)
        if spi.read(address,4096)!=wanted:
          raise RuntimeError('Sector readback mismatch; no write retry')
        result['completed_sectors'].append(sector);save(out/'result.json',result)
        event('SECTOR_VERIFIED',completed=index+1,total=64)
      for i in range(3):
        event('Final full readback',read=i+1,total=3)
        data=spi.read();save(out/f'post-full-{i}.bin',data)
        if data!=target:raise RuntimeError('Full readback mismatch; no write retry')
      result['status']='WRITTEN_TRIPLE_VERIFIED_PENDING_POWER_CYCLE'
  except BaseException as error:
    result.update(status='FAILED_NO_RETRY',error=repr(error))
    raise
  finally:
    try:
      spi.cleanup()
      for address,value in extra.items():
        if spi.transport.control(False,address)[0]!=value:spi.transport.control(True,address,value)
      if any(spi.transport.control(False,a)[0]!=v for a,v in extra.items()):raise RuntimeError('Extra register restoration failed')
      result['controller_restored']=True;result['protection_restored']=True
    except BaseException as error:
      result.update(status='CLEANUP_FAILED',cleanup_error=repr(error));raise
    finally:
      result['persistent_attempts']=spi.persistent_attempts
      event(result['status'])
      save(out/'result.json',result)
      save(out/'SHA256SUMS',''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file() and p.name!='SHA256SUMS').encode())
  if write:print('同时断开底座12V和USB约10秒，再重新连接；本次不自动断电，不代表GPU推理已验收。',flush=True)
  return result
