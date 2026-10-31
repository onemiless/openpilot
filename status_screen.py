#!/usr/bin/env python3
"""Read-only status screen. Snapshot mode never opens DRM or USB."""
import argparse
import json
import os
from pathlib import Path
import signal
import time
import zlib
import numpy as np

ROOT=Path(__file__).resolve().parent

def document(path):
  try:
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('JSON must be an object')
    return value
  except FileNotFoundError:return {}

def describe(path):
  try:
    state=document(path);stage=state.get('stage','IDLE');job=Path(state['job']) if 'job' in state else None
    title,detail,progress,color='等待底座接入','仅连接一块待刷写底座\n接入后自动备份、刷入 R2 和校验',0,'blue'
    if stage=='PREFLIGHT':title,detail='检查运行环境','正在检查固件、模型与离线依赖\n请勿断电或拔出底座'
    elif stage=='WRITING':
      title,detail='正在备份','准备读取本板完整固件，请勿断电'
      events=[]
      if job and (job/'events.jsonl').exists():
        for line in (job/'events.jsonl').read_bytes()[-4096:].splitlines():
          try:events.append(json.loads(line))
          except (ValueError,UnicodeDecodeError):continue
      if events:
        event=events[-1];name=event['message']
        if name=='Full backup':detail=f"完整备份 {event['read']} / 3\n请勿断电或拔出底座"
        elif name=='Final full readback':title,detail,progress='写后校验',f"整片回读 {event['read']} / 3\n正在核对目标镜像，请勿断电",1
        elif name not in ('JEDEC three reads',):
          result=document(job/'result.json');completed=len(result.get('completed_sectors',[]))
          title,detail,progress='正在刷写 R2',f'已校验扇区 {completed} / 64\n正在完整擦写，请勿断电或拔出底座',completed/64
    elif stage=='WAIT_POWER_CYCLE':
      title,detail,progress,color='请断电重接底座','同时断开底座 12V 和 USB\n等待约 10 秒后重新连接\n重接后自动校验并运行大模型',1,'yellow'
    elif stage=='VERIFYING':title,detail,progress='重接后校验','正在核对底座身份与三次整片回读\n请保持连接，随后自动开始推理',1
    elif stage=='INFERENCE':
      result=document(job/'inference.json') if job else {}
      title,detail='加载大模型','正在加载和预热 LSMV2\n加载完成后再开始计时 60 秒'
      if result.get('status')=='RUNNING':
        seconds=result['seconds'];title,detail,progress='正在推理测试',f"已运行 {seconds:.1f} / 60 秒\n已完成 {result['runs']} 次推理\n请保持连接，测试结束后自动显示结果",min(seconds/60,1)
      elif result.get('status')=='FAIL':title,detail,color='推理失败',result.get('error','未知错误')+'\n正在收尾，请稍候','red'
      elif result.get('status')=='PASS':title,detail,progress='正在收尾','60 秒推理已完成\n等待 GPU 资源释放，请稍候',1
    elif stage=='DONE':
      if any(state.get(key)!='PASS' for key in ('flash','activation_readback','inference')):raise ValueError('DONE 缺少通过结果')
      result=document(job/'inference.json')
      title,detail,progress,color='全部完成',f"R2 刷写、回读校验、60 秒推理通过\n推理 {result['seconds']:.3f} 秒 / {result['runs']} 次 / {result['hz']:.2f} Hz\n可移除底座",1,'green'
    elif stage=='FAILED':
      error=(document(job/'inference.json').get('error') or document(job/'result.json').get('error')) if job else None
      title,detail,color='测试失败',(error or state.get('error','未知错误'))+'\n已停止本轮操作，不自动重试\n保留备份和日志，请检查错误原因','red'
    elif stage!='IDLE':raise ValueError(f'未知阶段 {stage}')
    return {'title':title,'detail':detail,'progress':progress,'color':color}
  except (ValueError,KeyError,TypeError) as error:
    return {'title':'状态异常','detail':str(error),'progress':0,'color':'red'}

def render(info):
  font=json.loads((ROOT/'assets/screen-font.json').read_text())
  masks=np.frombuffer(zlib.decompress((ROOT/'assets/screen-font.bin.z').read_bytes()),dtype=np.uint8).reshape(-1,88,72)
  colors={'blue':(60,160,255),'yellow':(255,190,60),'green':(50,210,135),'red':(255,85,85)}
  accent=colors[info['color']];frame=np.empty((1080,2160,4),dtype=np.uint8);frame[:]=(39,23,13,255)
  def text(value,x,y,scale=1,color=(240,245,250),bottom=1040):
    origin=x
    for char in value:
      if char=='\n':x=origin;y+=90*scale;continue
      entry=font.get(char,font['?']);advance=entry[1]*scale
      if x+advance>2060:x=origin;y+=90*scale
      if y+88*scale>bottom:break
      alpha=masks[entry[0]]
      if scale!=1:alpha=np.repeat(np.repeat(alpha,scale,axis=0),scale,axis=1)
      target=frame[y:y+alpha.shape[0],x:x+alpha.shape[1],:3]
      a=alpha[...,None].astype(np.uint16)
      target[:]=((target.astype(np.uint16)*(255-a)+np.array(color[::-1],dtype=np.uint16)*a)//255).astype(np.uint8)
      x+=advance
  frame[:,0:18,:3]=accent[::-1]
  text('SP FLASHER / R2',100,48,color=(160,180,200))
  text(info['title'],100,180,2,accent,bottom=380)
  text(info['detail'],100,400,bottom=840)
  frame[870:900,100:2060,:3]=(75,60,45)
  end=100+int(1960*info['progress']);frame[870:900,100:end,:3]=accent[::-1]
  text('仅用于底座刷写 / 不启动车辆控制',100,950,color=(135,155,175))
  return frame

def snapshot(path,frame,info):
  path.write_bytes(b'P6\n2160 1080\n255\n'+frame[...,2::-1].tobytes())
  path.with_suffix('.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')

def main():
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--state',type=Path,default=Path('/data/sp-flasher/state.json'))
  parser.add_argument('--snapshot',type=Path)
  parser.add_argument('--ready-fd',type=int)
  parser.add_argument('--capture',type=Path)
  args=parser.parse_args()
  if args.snapshot:
    info=describe(args.state);snapshot(args.snapshot,render(info),info);return
  from screen_drm import Screen
  running=True
  def stop(*_):
    nonlocal running
    running=False
  signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
  with Screen() as screen:
    previous=None
    while running:
      info=describe(args.state)
      if info!=previous:
        frame=render(info);screen.present(frame);previous=info
        if args.capture is not None:
          snapshot(args.capture,screen.capture(),info);args.capture=None
        if args.ready_fd is not None:
          os.write(args.ready_fd,b'1');os.close(args.ready_fd);args.ready_fd=None
      time.sleep(.25)

if __name__=='__main__':main()
