"""Host ELF/ABI closure verification for the actual shipped ARM64 offline payload."""
import ast,hashlib,json,struct,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];runtime=root/'runtime'
base={'libc.so.6','libpthread.so.0','libdl.so.2','libutil.so.1','librt.so.1','libm.so.6','ld-linux-aarch64.so.1','libresolv.so.2'}
files=list(runtime.rglob('*'));names={p.name for p in files if p.is_file()};records=[];versions=set();llvm_symbols=set()
for path in files:
 if path.is_symlink():assert path.exists(),f'Broken symlink: {path}'
 if not path.is_file() or path.is_symlink():continue
 data=path.read_bytes()
 if not data.startswith(b'\x7fELF'):continue
 assert data[4:6]==b'\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,path
 offset=struct.unpack_from('<Q',data,40)[0];size,count=struct.unpack_from('<HH',data,58)
 sections=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
 needed=[];required=[]
 for section in sections:
  kind,start,length,link=section[1],section[4],section[5],section[6]
  if kind not in (6,0x6ffffffe,11):continue
  strings=sections[link];strings=data[strings[4]:strings[4]+strings[5]]
  if kind==6:
   for at in range(start,start+length,16):
    tag,value=struct.unpack_from('<qQ',data,at)
    if tag==1:needed.append(strings[value:].split(b'\0',1)[0].decode())
  elif kind==0x6ffffffe:
   at=start
   while True:
    _,cnt,_,aux,nxt=struct.unpack_from('<HHIII',data,at);entry=at+aux
    for _ in range(cnt):
     _,_,_,name,advance=struct.unpack_from('<IHHII',data,entry)
     version=strings[name:].split(b'\0',1)[0].decode()
     if version.startswith('GLIBC_'):
      parsed=tuple(map(int,version[6:].split('.')));versions.add(parsed);required.append(version)
      assert parsed<=(2,31),(path,version)
     entry+=advance
    if not nxt:break
    at+=nxt
  elif path.name=='libLLVM.so.19.1':
   for at in range(start,start+length,section[9]):
    index=struct.unpack_from('<I',data,at)[0]
    llvm_symbols.add(strings[index:strings.find(b'\0',index)].decode())
 for name in needed:
  if '/' in name:
   resolved=Path(name.replace('$ORIGIN',str(path.parent))).resolve()
   assert resolved.is_file() and resolved.is_relative_to(runtime.resolve()),(path,name)
  else:assert name in names|base,(path,name)
 records.append({'path':str(path.relative_to(root)),'needed':needed,'glibc_required':sorted(set(required)),
                 'sha256':hashlib.sha256(data).hexdigest()})
source=ast.parse((root/'tinygrad/runtime/support/compiler_llvm.py').read_text())
api_calls={n.func.attr for n in ast.walk(source) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
           and isinstance(n.func.value,ast.Name) and n.func.value.id=='llvm'}
api_calls={name for name in api_calls if not name.endswith('Ref') and name!='LLVMDiagnosticHandler'}
assert api_calls<=llvm_symbols,api_calls-llvm_symbols
assert records and 'libc.so.6' not in names and 'ld-linux-aarch64.so.1' not in names
output=Path(sys.argv[1]);output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'status':'PASS','scope':'real ARM64 ELF architecture, dependency closure and required ABI; not ARM64 execution',
                             'elf_count':len(records),'maximum_required_glibc':'.'.join(map(str,max(versions))),
                             'llvm_c_api_symbols_checked':len(api_calls),'files':records},indent=2)+'\n')
print('PASS',len(records),'ARM64 ELF payloads; max GLIBC',max(versions),':',output)
