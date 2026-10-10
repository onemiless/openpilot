#!/usr/bin/env python3
"""Compile actual IFE scale/geometry paths locally; never opens camera hardware."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
cam = root/'openpilot/system/camerad/cameras'
assert (cam/'ife_scale.h').is_file(), 'IFE scaling implementation absent'
spectra = (cam/'spectra.cc').read_text()
start = spectra.index('  buf.out_img_width = sensor->frame_width / sensor->out_scale;')
geometry = spectra[start:spectra.index('  // size is driven',start)]
original = (root/'docs/tesla/ref/camera/ife-native-register-block.txt').read_text()
assert original in (cam/'ife.h').read_text(), 'Unscaled register block changed'
assert 'buf.out_img_height, ife_road_resize)' in spectra
common = (cam/'camera_common.cc').read_text()
assert 'b->ife_road_resize ? b->cur_yuv_buf->stride : b->out_img_width' in common
qcom = (cam/'camera_qcom2.cc').read_text()
assert 'fl_pix_y *= float(camera.buf.out_img_height) / camera.sensor->frame_height' in qcom
assert qcom.count('fl_pix_y / fl_ref') == 3
source = r'''
#include <iostream>
#include <string>
#include "openpilot/sunnypilot/hardware/profile.h"
#include "openpilot/system/camerad/cameras/ife_scale.h"
#include "openpilot/system/camerad/cameras/nv12_info.h"
#define LOGW(...) ((void)0)
namespace cereal { struct FrameData {enum class ImageSensor {OX03C10, OS04C10};}; }
const int ISP_IFE_PROCESSED = 0;
struct Sensor {unsigned frame_width=1928,frame_height=1208,out_scale=1;int hdr_offset=0;cereal::FrameData::ImageSensor image_sensor=cereal::FrameData::ImageSensor::OX03C10;};
int main(int argc,char** argv) {
 Sensor info;auto sensor=&info;info.image_sensor=std::stoi(argv[3])?cereal::FrameData::ImageSensor::OS04C10:cereal::FrameData::ImageSensor::OX03C10;
 info.frame_width=std::stoi(argv[4]);info.frame_height=std::stoi(argv[5]);info.out_scale=std::stoi(argv[6]);
 struct {int camera_num,output_type;} cc{std::stoi(argv[1]),std::stoi(argv[2])};
 struct {unsigned out_img_width,out_img_height;bool ife_road_resize;} buf;bool ife_road_resize=false;
'''+geometry+r'''
 auto [stride,yh,uvh,size]=get_nv12_info(buf.out_img_width,buf.out_img_height);
 std::cout << buf.out_img_width << " " << buf.out_img_height << " " << stride << " " << yh << " " << uvh << " " << size << " " << ife_road_resize << "\n";
 for (auto v:ife_scale_registers(1928,1208,1344,760)) std::cout<<v<<" ";std::cout<<"\n";
 for (auto v:ife_scale_registers(1928,1208,672,380)) std::cout<<v<<" ";std::cout<<"\n";
}
'''
results=[]
with tempfile.TemporaryDirectory() as tmp:
 tmp=Path(tmp);(tmp/'probe.cc').write_text(source)
 subprocess.run(['c++','-std=c++17','-I'+str(root),str(tmp/'probe.cc'),'-o',str(tmp/'probe')],check=True)
 cases=[('c3xl','1344x760',i,0,0,1928,1208,1,True) for i in (0,1)]
 cases += [(p,'1344x760',0,0,0,1928,1208,1,False) for p in ('standard','c3')]
 cases += [('c3xl',e,0,0,0,1928,1208,1,False) for e in ('','1928x1208','garbage')]
 cases += [('c3xl','1344x760',2,0,0,1928,1208,1,False),('c3xl','1344x760',0,1,0,1928,1208,1,False),('c3xl','1344x760',0,0,1,2688,1520,2,False),('c3xl','1344x760',0,0,0,1920,1208,1,False)]
 for profile,size,index,output,sensor,w,h,scale,resize in cases:
  env=os.environ.copy();env.update(SUNNYPILOT_HARDWARE_PROFILE=profile,C3XL_IFE_ROAD_SIZE=size)
  lines=subprocess.check_output([str(tmp/'probe'),*map(str,[index,output,sensor,w,h,scale])],env=env,text=True).splitlines()
  actual=list(map(int,lines[0].split()));assert actual[:2]==([1344,760] if resize else [w//scale,h//scale]) and bool(actual[-1])==resize,actual
  if resize:assert actual[2:5]==[1408,768,384]
  registers=[list(map(int,line.split())) for line in lines[1:]]
  for reg,ow,oh in zip(registers,(1344,672),(760,380)):
   assert reg==[3,((ow-1)<<16)|1927,(3<<28)+(1928<<17)//ow,0,0,1927,((oh-1)<<16)|1207,(3<<28)+(1208<<17)//oh,0,0,1207]
  results.append({'profile':profile,'size':size,'camera':index,'output_type':output,'sensor':sensor,'geometry':actual,'resize':resize})
print(json.dumps({'pass':True,'scope':'compiled geometry/register configuration only, no device acceptance','registers_y_uv':registers,'cases':results},indent=2))
