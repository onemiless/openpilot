"""Minimal C3 DRM scanout, using magic.service's existing descriptor handoff."""
import array
import contextlib
import ctypes as C
import ctypes.util
import fcntl
import mmap
import os
from pathlib import Path
import socket
import numpy as np

U=C.c_uint32;P=C.POINTER
class Mode(C.Structure):
  _fields_=[('clock',U),*[(n,C.c_uint16) for n in ('hdisplay','hsync_start','hsync_end','htotal','hskew','vdisplay','vsync_start','vsync_end','vtotal','vscan')],('vrefresh',U),('flags',U),('type',U),('name',C.c_char*32)]
class Resources(C.Structure):
  _fields_=[('count_fbs',C.c_int),('fbs',P(U)),('count_crtcs',C.c_int),('crtcs',P(U)),('count_connectors',C.c_int),('connectors',P(U)),('count_encoders',C.c_int),('encoders',P(U)),('min_width',U),('max_width',U),('min_height',U),('max_height',U)]
class Connector(C.Structure):
  _fields_=[('connector_id',U),('encoder_id',U),('connector_type',U),('connector_type_id',U),('connection',C.c_int),('mmWidth',U),('mmHeight',U),('subpixel',C.c_int),('count_modes',C.c_int),('modes',P(Mode)),('count_props',C.c_int),('props',P(U)),('prop_values',P(C.c_uint64)),('count_encoders',C.c_int),('encoders',P(U))]
class Encoder(C.Structure):
  _fields_=[(n,U) for n in ('encoder_id','encoder_type','crtc_id','possible_crtcs','possible_clones')]
class Crtc(C.Structure):
  _fields_=[*[(n,U) for n in ('crtc_id','buffer_id','x','y','width','height')],('mode_valid',C.c_int),('mode',Mode),('gamma_size',C.c_int)]
class Dumb(C.Structure):
  _fields_=[*[(n,U) for n in ('height','width','bpp','flags','handle','pitch')],('size',C.c_uint64)]
class Map(C.Structure):
  _fields_=[('handle',U),('pad',U),('offset',C.c_uint64)]

class Screen:
  def __enter__(self):
    self.stack=contextlib.ExitStack()
    try:
      try:self.drm=C.CDLL(ctypes.util.find_library('drm') or 'libdrm.so.2',use_errno=True)
      except OSError:self.drm=C.CDLL(str(Path(__file__).parent/'runtime/display/libdrm.so.2'),use_errno=True)
      for name,restype,args in (
        ('drmModeGetResources',P(Resources),[C.c_int]),('drmModeGetConnector',P(Connector),[C.c_int,U]),
        ('drmModeGetEncoder',P(Encoder),[C.c_int,U]),('drmModeGetCrtc',P(Crtc),[C.c_int,U]),
        ('drmModeFreeResources',None,[P(Resources)]),('drmModeFreeConnector',None,[P(Connector)]),
        ('drmModeFreeEncoder',None,[P(Encoder)]),('drmModeFreeCrtc',None,[P(Crtc)]),
        ('drmModeAddFB',C.c_int,[C.c_int,U,U,C.c_uint8,C.c_uint8,U,U,P(U)]),
        ('drmModeRmFB',C.c_int,[C.c_int,U]),('drmModeSetCrtc',C.c_int,[C.c_int,U,U,U,U,P(U),C.c_int,P(Mode)]),
        ('drmSetMaster',C.c_int,[C.c_int])):
        fn=getattr(self.drm,name);fn.restype=restype;fn.argtypes=args
      if Path('/tmp/drmfd.sock').exists():
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.stack.callback(client.close)
        client.settimeout(5);client.connect('/tmp/drmfd.sock')
        _,ancillary,_,_=client.recvmsg(1,socket.CMSG_SPACE(array.array('i').itemsize))
        descriptors=array.array('i')
        for level,kind,data in ancillary:
          if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:descriptors.frombytes(data)
        if len(descriptors)!=1:raise RuntimeError('Invalid magic DRM descriptor handoff')
        self.fd=descriptors[0];self.stack.callback(os.close,self.fd)
      else:
        self.fd=os.open('/dev/dri/card0',os.O_RDWR|os.O_CLOEXEC);self.stack.callback(os.close,self.fd)
        if self.drm.drmSetMaster(self.fd):raise OSError(C.get_errno(),'Cannot acquire DRM master')
      resources=self.drm.drmModeGetResources(self.fd)
      if not resources:raise OSError(C.get_errno(),'DRM resources unavailable')
      self.stack.callback(self.drm.drmModeFreeResources,resources)
      for i in range(resources.contents.count_connectors):
        connector=self.drm.drmModeGetConnector(self.fd,resources.contents.connectors[i])
        if not connector:continue
        if connector.contents.connection==1 and connector.contents.connector_type==16 and connector.contents.count_modes:break
        self.drm.drmModeFreeConnector(connector)
      else:raise RuntimeError('Connected C3 DSI panel not found')
      self.stack.callback(self.drm.drmModeFreeConnector,connector);self.connector=U(connector.contents.connector_id)
      encoder=self.drm.drmModeGetEncoder(self.fd,connector.contents.encoder_id)
      if not encoder:raise OSError(C.get_errno(),'DSI encoder unavailable')
      self.stack.callback(self.drm.drmModeFreeEncoder,encoder)
      crtc=encoder.contents.crtc_id
      if not crtc:
        crtc=next(resources.contents.crtcs[i] for i in range(resources.contents.count_crtcs) if encoder.contents.possible_crtcs&(1<<i))
      previous=self.drm.drmModeGetCrtc(self.fd,crtc)
      if not previous:raise OSError(C.get_errno(),'DSI CRTC unavailable')
      self.stack.callback(self.drm.drmModeFreeCrtc,previous);self.previous=previous
      self.mode=Mode.from_buffer_copy(previous.contents.mode if previous.contents.mode_valid else connector.contents.modes[0])
      if (self.mode.hdisplay,self.mode.vdisplay)!=(1080,2160):raise RuntimeError('Unsupported C3 panel mode')
      self.dumb=Dumb(height=self.mode.vdisplay,width=self.mode.hdisplay,bpp=32)
      fcntl.ioctl(self.fd,0xc02064b2,self.dumb)
      self.stack.callback(fcntl.ioctl,self.fd,0xc00464b4,U(self.dumb.handle))
      mapping=Map(handle=self.dumb.handle);fcntl.ioctl(self.fd,0xc01064b3,mapping)
      self.memory=mmap.mmap(self.fd,self.dumb.size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=mapping.offset)
      self.stack.callback(self.memory.close)
      self.fb=U()
      if self.drm.drmModeAddFB(self.fd,self.dumb.width,self.dumb.height,24,32,self.dumb.pitch,self.dumb.handle,C.byref(self.fb)):
        raise OSError(C.get_errno(),'Cannot add screen framebuffer')
      self.stack.callback(self.drm.drmModeRmFB,self.fd,self.fb)
      self.started=False
      return self
    except BaseException:
      self.stack.close();raise

  def present(self,frame):
    pixels=np.ndarray((self.dumb.height,self.dumb.pitch),dtype=np.uint8,buffer=self.memory)
    pixels[:,:self.dumb.width*4]=np.rot90(frame,-1).reshape(self.dumb.height,self.dumb.width*4)
    if not self.started:
      old=self.previous.contents
      if self.drm.drmModeSetCrtc(self.fd,old.crtc_id,self.fb,0,0,C.byref(self.connector),1,C.byref(self.mode)):
        raise OSError(C.get_errno(),'Cannot present screen')
      self.stack.callback(self.drm.drmModeSetCrtc,self.fd,old.crtc_id,old.buffer_id,old.x,old.y,C.byref(self.connector),1,C.byref(self.previous.contents.mode))
      self.started=True
    backlight=Path('/sys/class/backlight/panel0-backlight')
    if backlight.exists():
      (backlight/'bl_power').write_text('0')
      if int((backlight/'brightness').read_text())==0:
        (backlight/'brightness').write_text(str(int((backlight/'max_brightness').read_text())*65//100))

  def capture(self):
    pixels=np.ndarray((self.dumb.height,self.dumb.pitch),dtype=np.uint8,buffer=self.memory)
    native=pixels[:,:self.dumb.width*4].reshape(self.dumb.height,self.dumb.width,4)
    return np.rot90(native,1).copy()

  def __exit__(self,*_):self.stack.close()
