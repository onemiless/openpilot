"""Drive the real screen reader/renderer CLI with persisted lifecycle fixtures; never hardware."""
import hashlib,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
cases=[('waiting',None,'等待底座'),('preflight',{'stage':'PREFLIGHT'},'检查运行环境'),
 ('backup',{'stage':'WRITING'},'正在备份'),('write',{'stage':'WRITING'},'正在刷写'),
 ('readback',{'stage':'WRITING'},'写后校验'),('power',{'stage':'WAIT_POWER_CYCLE'},'断电重接'),
 ('verify',{'stage':'VERIFYING'},'重接后校验'),('load',{'stage':'INFERENCE'},'加载大模型'),
 ('running',{'stage':'INFERENCE'},'正在推理'),('closing',{'stage':'INFERENCE'},'正在收尾'),
 ('done',{'stage':'DONE','flash':'PASS','activation_readback':'PASS','inference':'PASS'},'全部完成'),
 ('false_done',{'stage':'DONE','flash':'PASS','inference':'NOT_RUN'},'状态异常'),
 ('failed',{'stage':'FAILED','error':'OSError(71, Protocol error)'},'测试失败'),
 ('inference_failed_pending',{'stage':'INFERENCE'},'推理失败'),
 ('failed_inference',{'stage':'FAILED','error':'CalledProcessError'},'测试失败'),
 ('corrupt',{},'状态异常')]
records=[]
for name,state,title in cases:
 case=out/name;case.mkdir();job=case/'job';job.mkdir();path=case/'state.json'
 if state is not None:
  state['job']=str(job);path.write_text(json.dumps(state))
 if name=='corrupt':path.write_text('{invalid')
 if name in ('failed_inference','inference_failed_pending'):(job/'inference.json').write_text(json.dumps({'status':'FAIL','error':'USB GPU error state'}))
 if name=='backup':(job/'events.jsonl').write_text(json.dumps({'message':'Full backup','read':2,'total':3})+'\n{partial')
 if name=='done':assert '准备下一块' not in info['detail']
 if name=='write':
  (job/'events.jsonl').write_text(json.dumps({'message':'SECTOR_VERIFIED','completed':19,'total':64})+'\n')
  (job/'result.json').write_text(json.dumps({'completed_sectors':list(range(1,20))}))
 if name=='readback':(job/'events.jsonl').write_text(json.dumps({'message':'Final full readback','read':2,'total':3})+'\n')
 if name in ('running','closing'):(job/'inference.json').write_text(json.dumps({'status':'RUNNING' if name=='running' else 'PASS','seconds':31.5 if name=='running' else 60.05,'runs':220,'hz':7.1}))
 if name=='done':(job/'inference.json').write_text(json.dumps({'status':'PASS','seconds':60.055,'runs':429,'hz':7.143}))
 subprocess.run([sys.executable,str(root/'status_screen.py'),'--state',str(path),'--snapshot',str(case/'screen.ppm')],check=True)
 info=json.loads((case/'screen.json').read_text());assert title in info['title'],(name,info)
 assert (case/'screen.ppm').read_bytes().startswith(b'P6\n2160 1080\n255\n')
 if name=='done':assert '准备下一块' not in info['detail']
 if name=='write':assert '19 / 64' in info['detail']
 if name=='running':assert '31.5 / 60' in info['detail']
 if name=='power':assert '12V' in info['detail'] and 'USB' in info['detail'] and '10' in info['detail']
 if name=='failed_inference':assert 'USB GPU error state' in info['detail']
 if name=='failed':assert 'Protocol error' in info['detail']
 records.append({'case':name,'status':'PASS','title':info['title']})
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'actual screen renderer + lifecycle files; no DRM or USB','cases':records},indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print('PASS',len(records),'screen lifecycle snapshots:',out)
