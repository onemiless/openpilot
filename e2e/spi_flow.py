"""File + register/SPI full-flow E2E; never opens real USB."""
import contextlib,hashlib,io,json,random,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from spi_core import SPI
from flash import execute

class Board:
 def __init__(self,fault=''):
  self.reg=bytearray(65536);self.reg[0xc8a6]=4;self.reg[0xca81]=14;self.reg[0xc805]=2
  self.flash=bytearray(random.Random(30).randbytes(262144));self.sr=0x1c;self.fault=fault;self.erases=[];self.programs=[]
 def offroad(self):pass
 def control(self,write,address,value=0,length=1):
  if not write:
   assert length<=64,'USB2 E4 limit'
   return bytes(self.reg[address:address+length])
  self.reg[address]=value
  if address!=0xc8a9:return b''
  op=self.reg[0xc8aa];a=self.reg[0xc8a1]|self.reg[0xc8a2]<<8|self.reg[0xc8ab]<<16;n=self.reg[0xc8a3]<<8|self.reg[0xc8a4]
  data=None
  if op==0x9f:data=bytes.fromhex('124012' if self.fault=='jedec' else '854012')
  elif op==0x4b:data=bytes(range(20))
  elif op==5:data=bytes([self.sr])
  elif op==0x35:data=b'\0'
  elif op==0x15:data=b'\x20'
  elif op==3:
   data=bytes(self.flash[a:a+n])
   if self.fault=='first-last' and n>1:data=data[-1:]+data[1:]
  elif op==0x50:pass
  elif op==1:self.sr=self.reg[0x7000]
  elif op==6:self.sr|=2
  elif op==4:self.sr&=~2
  elif op==0x20:
   assert self.sr==2 and a%4096==0;self.erases.append(a);self.flash[a:a+4096]=b'\xff'*4096
   if self.fault=='erase-first':self.flash[a]=0
   self.sr=0
  elif op==2:
   assert self.sr==2 and n==128 and a%128==0;self.programs.append(a)
   self.flash[a:a+n]=bytes(x&y for x,y in zip(self.flash[a:a+n],self.reg[0x7000:0x7000+n]));self.sr=0
  else:raise AssertionError(op)
  if data is not None:self.reg[0x7000:0x7000+len(data)]=data
  self.reg[0xc8a9]=0
  if op==2 and self.fault=='lost-ack':raise OSError('program committed, ACK lost')
  return b''

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False);records=[]
for mode,fault in [('probe',''),('flash',''),('restore',''),('flash','first-last'),('flash','jedec'),('flash','erase-first'),('flash','lost-ack')]:
 board=Board(fault);before=bytes(board.flash);job=out/(mode+'-'+(fault or 'normal'));job.mkdir();restore=None
 if mode=='restore':restore=bytes(random.Random(61).randbytes(262144))
 failed=False
 with contextlib.redirect_stdout(io.StringIO()):
  try:result=execute(SPI(board),job,mode!='probe',restore)
  except (OSError,RuntimeError,ValueError):failed=True
 if fault:
  assert failed
  if fault in ('first-last','jedec'):assert not board.erases and not board.programs and bytes(board.flash)==before
  if fault=='lost-ack':assert len(board.programs)==1
 else:
  assert not failed and board.sr==0x1c and board.reg[0xca81]==14
  if mode=='probe':assert not board.erases and bytes(board.flash)==before
  else:
   assert len(board.erases)==64 and board.erases[-1]==0
   target=(job/'target-full.bin').read_bytes();assert bytes(board.flash)==target
   assert all((job/f'post-full-{i}.bin').read_bytes()==target for i in range(3))
   if restore is not None:assert target==restore
   else:assert target[:256]==before[:256] and target[0x17fe0:]==before[0x17fe0:]
 for line in (job/'SHA256SUMS').read_text().splitlines():
  digest,name=line.split('  ',1);assert hashlib.sha256((job/name).read_bytes()).hexdigest()==digest
 records.append({'mode':mode,'fault':fault,'expected_failure':bool(fault),'erase_count':len(board.erases),'program_count':len(board.programs),'status':'PASS'})
(out/'result.json').write_text(json.dumps({'status':'PASS','cases':records,'scope':'host register/SPI full-flow simulation; no real USB'},indent=2)+'\n')
print('PASS',len(records),'full-flow scenarios; artifacts:',out)
