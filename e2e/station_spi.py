"""Complete station -> real SPI algorithm -> persistent artifacts; model boundary simulated."""
import ast
import contextlib
import io
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import station
# Reuse the transport simulator without executing spi_flow's CLI.
tree=ast.parse((Path(__file__).with_name('spi_flow.py')).read_text())
namespace={'random':random}
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node,ast.ClassDef)],type_ignores=[]),__file__,'exec'),namespace)
Board=namespace['Board']
class Dock(Board):
  def __enter__(self):return self
  def __exit__(self,*args):pass
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
board=Dock();device={'path':'/mock/dock','token':'connection-1'}
station.Session=lambda path:board
station.devices=lambda:[device]
station.preflight=lambda:None
station.infer=lambda job:{'status':'PASS','seconds':60,'runs':100,'backend':'USB+AMD:LLVM'}
with contextlib.redirect_stdout(io.StringIO()):
 station.tick(out)
 state=json.loads((out/'state.json').read_text())
 assert state['stage']=='WAIT_POWER_CYCLE' and len(board.erases)==64
 station.tick(out);assert len(board.erases)==64
 station.devices=lambda:[];station.tick(out)
 station.devices=lambda:[device];station.tick(out)
 state=json.loads((out/'state.json').read_text())
 assert state['stage']=='DONE' and len(board.erases)==64
job=Path(state['job']);target=(job/'target-full.bin').read_bytes()
assert all((job/f'activated-full-{i}.bin').read_bytes()==target for i in range(3))
assert board.sr==0x1c
assert board.reg[0xca81]==14 and board.reg[0xc805]==2 and board.reg[0xcc33]==0
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'host station + real SPI algorithm + simulated inference; no hardware','job':str(job)},indent=2)+'\n')
print('PASS integrated station/SPI:',out)
