#!/usr/bin/env python3
"""Native tici layout on Mac; screenshots do not establish device acceptance."""
import os, uuid, json
from pathlib import Path
os.environ['BIG']='1';os.environ['SCALE']='1' if os.path.exists('/AGNOS') else '0.6'
os.environ['OPENPILOT_PREFIX']='sp-c3-ui-'+uuid.uuid4().hex[:8]
from openpilot.common.prefix import OpenpilotPrefix
prefix=OpenpilotPrefix(prefix=os.environ['OPENPILOT_PREFIX']);prefix.__enter__()
import pyray as rl
from openpilot.cereal import messaging
from opendbc.car import structs
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import multilang
from openpilot.selfdrive.ui.sunnypilot.layouts.home import HomeLayoutSP
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla import TeslaSettings
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla_control import TeslaControlSettingsLayout
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.tesla_planner import TeslaPlannerSettingsLayout
from openpilot.selfdrive.ui.layouts.settings.toggles import TogglesLayout
from openpilot.selfdrive.ui.sunnypilot.onroad.traffic_control import TrafficControlRenderer
from openpilot.system.ui.widgets.scroller_tici import Scroller
out=Path('artifacts/sp-tesla-migration/ui-c3');out.mkdir(parents=True,exist_ok=True)
multilang.change_language('zh-CHS');ui_state.started=False;ui_state.params.put_bool('IsOffroad',True,block=True)
gui_app.init_window('C3 tici migration E2E',fps=20)
assert (gui_app.width,gui_app.height)==(2160,1080)
home=HomeLayoutSP();tesla=TeslaSettings();settings=Scroller(tesla.items,line_separator=True,spacing=0)
control=TeslaControlSettingsLayout(lambda:None);planner=TeslaPlannerSettingsLayout(lambda:None);toggles=TogglesLayout()
traffic=TrafficControlRenderer();pm=messaging.PubMaster(['longitudinalPlanSP','deviceState'])
ui_state.CP=structs.CarParams.new_message();ui_state.CP.brand='tesla';ui_state.CP.openpilotLongitudinalControl=True
ui_state.params.remove('DriverMonitoringEnabled')
for page in (home,settings,control,planner,toggles):page.show_event()
views=[('home',home),('tesla-settings',settings),('tesla-controls',control),('longitudinal',planner),('dm-toggle',toggles),('traffic-red',traffic)]
for index,_ in enumerate(gui_app.render()):
 view=min(index//12,len(views)-1);name,widget=views[view]
 msg=messaging.new_message('longitudinalPlanSP');msg.valid=True
 p=msg.longitudinalPlanSP.teslaTrafficControl;p.mode=4;p.phase=2;p.rawDistance=25;p.quality=2;p.lightState=1
 pm.send('longitudinalPlanSP',msg);ui_state.sm.update(10)
 if name=='traffic-red':traffic.update()
 widget.render(rl.Rectangle(0,0,2160,1080))
 if index%12==10:
  rl.rl_draw_render_batch_active();rl.take_screenshot(str(out/(name+'.png')))
 if index==72:gui_app.request_close()
(out/'summary.json').write_text(json.dumps({'logical_viewport':[2160,1080],'render_scale':float(os.environ['SCALE']),'scope':'physical C3 offroad UI' if os.path.exists('/AGNOS') else 'Mac tici simulation','views':[x[0] for x in views]},indent=2)+'\n')
gui_app.close();prefix.__exit__(None,None,None)
